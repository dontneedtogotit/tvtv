"""
tvtv-yt — yt-dlp microservice for the TV HTPC.

Endpoints
---------
POST /api/play       Launch MPV with the best stream for a YouTube URL
GET  /api/search     Search YouTube via yt-dlp (returns JSON results)
GET  /api/formats    List available formats for a URL
GET  /api/health     Health check
GET  /history         Watch history
POST /history         Append watch history
GET  /settings        Read settings
POST /settings        Save settings
GET  /metadata/media  Media metadata helper
GET  /apps/<id>/...   App/plugin backend APIs
GET  /apps-frontend/<id>/   App/plugin frontend entrypoints
GET  /               Main frontend shell
"""

from __future__ import annotations

import asyncio
import importlib.util
import json
import logging
import os
import re
import subprocess
import shutil
from contextlib import suppress
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from apps import AppRegistry
from history import router as history_router
from settings import router as settings_router
from metadata_providers import router as metadata_router
from subtitles import router as subtitles_router
from playback import router as playback_router
from system import router as system_router
from mpv import CHECKPOINT_INTERVAL_S, checkpoint, get_property, send_command
from profile import mpv_args, profile_summary
from player_manager import player
from queue_db import (
    QueueItem,
    list_queue,
    add_to_queue,
    pop_next_queue_item,
    remove_queue_item,
    clear_queue,
)
from auth import (
    verify_client_access,
    get_security_mode,
    get_active_pin,
    create_paired_token,
    is_token_valid,
    is_loopback,
)
from ai_assistant import (
    send_chat_message,
    get_history as get_ai_history,
    clear_conversation as clear_ai_conversation,
    parse_voice_command,
)

logging.basicConfig(
    level=os.environ.get('TVTV_LOG_LEVEL', 'INFO'),
    format='%(asctime)s %(levelname)s %(name)s: %(message)s',
)
log = logging.getLogger('tvtv')

app = FastAPI(title="tvtv-yt", version="0.1.0")

# ── Security & CORS (Phase 8) ────────────────────────────────────────────────
# Restrict CORS to loopback and private LAN addresses (RFC 1918)
LAN_ORIGIN_REGEX = r"^https?://(localhost|127\.0\.0\.1|192\.168\.\d{1,3}\.\d{1,3}|10\.\d{1,3}\.\d{1,3}\.\d{1,3}|172\.(1[6-9]|2\d|3[0-1])\.\d{1,3}\.\d{1,3})(:\d+)?$"

app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=LAN_ORIGIN_REGEX,
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)


@app.middleware("http")
async def add_security_headers(request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    # Allow iframe embedding for our own frontend shell mounting apps
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    response.headers["Referrer-Policy"] = "no-referrer-when-downgrade"
    return response

# ── Config ────────────────────────────────────────────────────────────────────

YT_DLP = shutil.which("yt-dlp") or "yt-dlp"
MPV = shutil.which("mpv") or "mpv"
CACHE_DIR = Path.home() / ".cache" / "tvtv-yt"
CACHE_DIR.mkdir(parents=True, exist_ok=True)
IPC_SOCKET = "/tmp/mpv-ipc.sock"

# ── Models ────────────────────────────────────────────────────────────────────

class PlayRequest(BaseModel):
    url: str = Field(..., description="YouTube video URL or stream")
    seek: Optional[float] = Field(None, description="Start time in seconds (resume)")
    fullscreen: bool = Field(True, description="Launch MPV fullscreen")
    sponsorblock: bool = Field(False, description="Skip sponsored segments via SponsorBlock")
    sponsorblock_categories: Optional[list[str]] = Field(None, description="List of categories to skip")
    title: Optional[str] = Field(None, description="Video title")
    channel: Optional[str] = Field(None, description="Uploader/channel name")
    duration: Optional[float] = Field(None, description="Duration in seconds")
    thumbnail: Optional[str] = Field(None, description="Thumbnail URL")
    subtitle_url: Optional[str] = Field(None, description="Subtitle track URL to load in MPV")
    subtitle_lang: str = Field("", description="Language of the loaded subtitle track")

class TrackSelectRequest(BaseModel):
    type: str = Field(..., description="'audio' or 'sub'")
    id: int = Field(..., description="Track ID number")

class ControlRequest(BaseModel):
    action: str = Field("", description="Playback command name")
    url: str = Field("", description="Deprecated: legacy action payload")

class PairRequest(BaseModel):
    pin: str = Field(..., description="4-digit pairing PIN displayed on TV Settings")
    client_name: str = Field("Remote Device", description="Friendly device name")

# ── Helpers ───────────────────────────────────────────────────────────────────

def _run_yt_dlp(args: list[str], timeout: int = 30) -> str:
    cmd = [YT_DLP] + args
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        return result.stdout.strip()
    except subprocess.TimeoutExpired:
        raise HTTPException(504, "yt-dlp timed out")
    except FileNotFoundError:
        raise HTTPException(500, "yt-dlp not found on PATH")

# ── Core Routes ───────────────────────────────────────────────────────────────

@app.get("/api/health")
def health() -> dict:
    return {
        "status": "ok",
        "yt_dlp": bool(shutil.which("yt-dlp")),
        "mpv": bool(shutil.which("mpv")),
        "tv_profile": profile_summary(),
        "apps": sorted(registry.apps.keys()),
        "app_load_errors": registry.load_errors,
        "security_mode": get_security_mode(),
    }


@app.get("/api/auth/status")
def auth_status(request: Request) -> dict:
    host = request.client.host if request.client else "127.0.0.1"
    loopback = is_loopback(host)
    token = (
        request.headers.get("X-Auth-Token")
        or request.query_params.get("token")
        or request.cookies.get("tvtv_session")
        or ""
    )
    return {
        "security_mode": get_security_mode(),
        "is_loopback": loopback,
        "is_authenticated": loopback or is_token_valid(token) or (get_security_mode() == "open"),
        "active_pin": get_active_pin() if loopback else None,
    }


@app.post("/api/auth/pair")
def auth_pair(req: PairRequest) -> dict:
    if req.pin.strip() != get_active_pin():
        raise HTTPException(400, "Invalid pairing PIN")
    token = create_paired_token(req.client_name)
    return {
        "status": "ok",
        "token": token,
        "client_name": req.client_name,
        "message": "Device paired successfully.",
    }

def _fmt_seconds(sec) -> str:
    try:
        sec = int(float(sec))
    except (TypeError, ValueError):
        return ""
    h, m, s = sec // 3600, (sec % 3600) // 60, sec % 60
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"

def _search_yt(q: str, limit: int = 20) -> list[dict]:
    limit = max(1, min(limit, 50))
    search_spec = f"ytsearch{limit}:{q}"
    stdout = _run_yt_dlp(
        ["--no-warnings", "--dump-json", "--flat-playlist", "--skip-download", search_spec],
        timeout=30,
    )
    items: list[dict] = []
    for line in stdout.splitlines():
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            continue
        thumbs = data.get("thumbnails") or []
        thumbnail = thumbs[0].get("url", "") if thumbs else data.get("thumbnail", "")
        dur = data.get("duration")
        if isinstance(dur, (int, float)):
            duration_str = _fmt_seconds(dur)
            duration_seconds = float(dur)
        else:
            duration_str = data.get("duration_string", "")
            duration_seconds = None
        items.append({
            "id": data.get("id", ""),
            "title": data.get("title", ""),
            "uploader": data.get("uploader") or data.get("channel") or "",
            "duration": duration_str,
            "duration_seconds": duration_seconds,
            "views": data.get("view_count", 0),
            "thumbnail": thumbnail,
            "url": data.get("url") or data.get("webpage_url", ""),
        })
    return items


@app.get("/api/search")
def search(q: str, limit: int = 20) -> JSONResponse:
    if not q.strip():
        raise HTTPException(400, "Empty query")
    items = _search_yt(q, limit)
    return JSONResponse({"query": q, "results": items})


@app.get("/api/trending")
def trending(limit: int = 20) -> JSONResponse:
    items = _search_yt("trending", limit)
    return JSONResponse({"query": "trending", "results": items})

@app.get("/api/formats")
def formats(url: str) -> JSONResponse:
    stdout = _run_yt_dlp(["-F", url], timeout=30)
    return JSONResponse({"formats": stdout.splitlines()})

@app.on_event("startup")
async def _start_position_checkpointer() -> None:
    """Persist playback position periodically while MPV is running.

    Nothing previously wrote a position after the initial seek, so Continue
    Watching and resume never advanced past the first play. Phase 9 replaces
    this polling loop with MPV property observation.
    """
    async def _loop() -> None:
        while True:
            try:
                await asyncio.sleep(CHECKPOINT_INTERVAL_S)
                await asyncio.to_thread(checkpoint)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                # Nothing is playing most of the time; that is not an error.
                log.debug('checkpoint skipped: %s', e)

    task = asyncio.create_task(_loop())
    app.state.checkpoint_task = task


@app.on_event("shutdown")
async def _stop_position_checkpointer() -> None:
    task = getattr(app.state, 'checkpoint_task', None)
    if task is None:
        return
    task.cancel()
    # Flush a final checkpoint so the last few seconds aren't lost.
    try:
        await asyncio.to_thread(checkpoint)
    except Exception:
        pass


def _stop_existing_player() -> None:
    """Ask a running MPV to quit before launching a replacement."""
    with suppress(Exception):
        send_command('quit')


def _subtitle_url(req: PlayRequest) -> str:
    """Resolve the subtitle track to hand MPV via --sub-file.

    The frontend can pass a URL it already fetched from /subtitles; if it
    didn't, look the track up here so subtitle selection works from the
    phone remote too.
    """
    if req.subtitle_url and req.subtitle_url.strip():
        return req.subtitle_url.strip()
    if not req.subtitle_lang.strip():
        return ''
    try:
        import httpx
        r = httpx.get(
            f'http://127.0.0.1:{os.environ.get("TVTV_PORT", "8000")}/subtitles',
            params={'url': req.url, 'lang': req.subtitle_lang},
            timeout=20.0,
        )
        return str(r.json().get('subtitle_url') or '')
    except Exception as e:
        log.warning('subtitle lookup failed for %s: %s', req.url, e)
        return ''


@app.post("/api/play")
def play(req: PlayRequest, request: Request) -> JSONResponse:
    verify_client_access(request)
    url = req.url.strip()
    if not url:
        raise HTTPException(400, "No URL provided")

    subtitle_url = _subtitle_url(req)
    try:
        res = player.launch(
            url=url,
            title=req.title,
            channel=req.channel,
            duration=req.duration,
            thumbnail=req.thumbnail,
            seek=req.seek,
            fullscreen=req.fullscreen,
            sponsorblock=req.sponsorblock,
            sponsorblock_categories=req.sponsorblock_categories,
            subtitle_url=subtitle_url,
        )
    except Exception as e:
        raise HTTPException(500, f"Failed to start playback: {e}")

    return JSONResponse({
        **res,
        "sponsorblock": req.sponsorblock,
        "profile_args": mpv_args(),
    })

@app.post("/api/control")
def control(req: ControlRequest, request: Request) -> JSONResponse:
    verify_client_access(request)
    # Accept both the new `{action: "pause"}` shape and the legacy
    # `{url: "pause"}` shape used by older remotes.
    action = (req.action or req.url or "").strip()
    if not action:
        raise HTTPException(400, "No action provided")

    # Typing action: type:<text>
    if action.startswith("type:"):
        text_to_type = action[5:]
        try:
            subprocess.run(
                ["ydotool", "type", text_to_type],
                capture_output=True, text=True, timeout=4, check=False,
                env={**os.environ, "YDOTOOL_SOCKET": "/run/ydotoold/socket"},
            )
            return JSONResponse({"status": "ok", "action": "type", "text": text_to_type})
        except Exception as e:
            return JSONResponse({"status": "warn", "detail": f"Typing failed: {e}"})

    # Virtual Navigation Keys
    nav_keys = {
        "up": 103,
        "down": 108,
        "left": 105,
        "right": 106,
        "enter": 28,
        "select": 28,
        "back": 1,
        "esc": 1,
        "home": 102,
    }
    if action in nav_keys:
        code = nav_keys[action]
        try:
            subprocess.run(
                ["ydotool", "key", f"{code}:1", f"{code}:0"],
                capture_output=True, text=True, timeout=2, check=False,
                env={**os.environ, "YDOTOOL_SOCKET": "/run/ydotoold/socket"},
            )
            return JSONResponse({"status": "ok", "action": action, "key_code": code})
        except Exception as e:
            return JSONResponse({"status": "warn", "detail": f"Key send failed: {e}"})

    if action == "stop":
        player.stop()
        return JSONResponse({"status": "ok", "action": "stop", "command": "quit"})

    # MPV Playback Commands
    mpv_commands = {
        "pause": "cycle pause",
        "stop": "quit",
        "fullscreen": "cycle fullscreen",
        "seek+10": "seek 10",
        "seek-10": "seek -10",
        "seek+30": "seek 30",
        "seek-30": "seek -30",
        "speed+": "add speed 0.25",
        "speed-": "add speed -0.25",
        "speed1": "set speed 1.0",
        "vol+": "add volume 5",
        "vol-": "add volume -5",
        "mute": "cycle mute",
    }
    cmd_str = mpv_commands.get(action)
    if not cmd_str:
        raise HTTPException(400, f"Unknown action: {action}")
    try:
        send_command(cmd_str, IPC_SOCKET)
        return JSONResponse({"status": "ok", "action": action, "command": cmd_str})
    except Exception as e:
        # MPV not running is the normal case when nothing is playing.
        return JSONResponse(
            {"status": "warn", "action": action, "detail": f"MPV not reachable: {e}"},
            status_code=200,
        )


# ── Track Selection & Queue (Phase 9) ────────────────────────────────────────

@app.get("/api/player/tracks")
def player_tracks(request: Request) -> dict:
    verify_client_access(request)
    return player.get_tracks()


@app.post("/api/player/track")
def select_player_track(req: TrackSelectRequest, request: Request) -> dict:
    verify_client_access(request)
    ok = player.set_track(req.type, req.id)
    return {"status": "ok" if ok else "failed", "type": req.type, "id": req.id}


@app.get("/api/queue")
def get_queue(request: Request) -> dict:
    verify_client_access(request)
    return {"queue": list_queue()}


@app.post("/api/queue")
def enqueue_item(item: QueueItem, request: Request) -> dict:
    verify_client_access(request)
    created = add_to_queue(item)
    return {"status": "ok", "item": created}


@app.delete("/api/queue/{item_id}")
def delete_queue_item(item_id: int, request: Request) -> dict:
    verify_client_access(request)
    ok = remove_queue_item(item_id)
    return {"status": "ok", "removed": ok}


@app.delete("/api/queue")
def delete_entire_queue(request: Request) -> dict:
    verify_client_access(request)
    clear_queue()
    return {"status": "ok"}


@app.post("/api/queue/next")
def play_next_in_queue(request: Request) -> dict:
    verify_client_access(request)
    item = pop_next_queue_item()
    if not item:
        return {"status": "empty", "message": "Queue is empty"}
    res = player.launch(
        url=item["url"],
        title=item.get("title"),
        channel=item.get("channel"),
        duration=item.get("duration"),
        thumbnail=item.get("thumbnail"),
    )
    return {"status": "playing", "item": item, "player": res}

def _extract_video_id(url: str) -> str | None:
    m = re.search(r'(?:v=|/)([A-Za-z0-9_-]{11})(?:[?&/]|$)', url)
    return m.group(1) if m else None

# ── Agentic AI Assistant ──────────────────────────────────────────────────────

class AIChatRequest(BaseModel):
    message: str = Field(..., description="User's text or voice-transcribed message")
    conversation_id: str = Field("default", description="Conversation session id")

@app.post("/api/ai/chat")
def ai_chat(req: AIChatRequest) -> JSONResponse:
    """Send a message to the tvtv agentic AI (Kilo Gateway free models)."""
    try:
        result = send_chat_message(req.conversation_id, req.message)
        return JSONResponse(result)
    except Exception as e:
        return JSONResponse({"error": str(e), "reply": "Sorry, I couldn't process that."}, status_code=500)

@app.post("/api/ai/chat/stream")
async def ai_chat_stream(req: AIChatRequest) -> StreamingResponse:
    """Stream the tvtv assistant reply token-by-token from Kilo Gateway."""
    async def _stream():
        try:
            result = send_chat_message(req.conversation_id, req.message)
            reply = result.get("reply", "")
            model = result.get("model_used", "unknown")
            if not reply:
                yield "data: {\"token\": \"\"}\n\n"
            else:
                for ch in reply:
                    escaped = ch.replace("\\", "\\\\").replace('"', '\\"')
                    yield "data: {\"token\": \"" + escaped + "\"}\n\n"
            model_escaped = str(model).replace("\\", "\\\\").replace('"', '\\"')
            yield "data: {\"done\": true, \"model\": \"" + model_escaped + "\"}\n\n"
        except Exception as e:
            msg = str(e).replace("\\", "\\\\").replace('"', '\\"')
            yield "data: {\"token\": \"Error: " + msg + "\"}\n\n"
            yield "data: {\"done\": true, \"model\": \"error\"}\n\n"

    return StreamingResponse(_stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

@app.get("/api/ai/history/{conversation_id}")
def ai_history(conversation_id: str) -> JSONResponse:
    return JSONResponse({"conversation_id": conversation_id, "messages": get_ai_history(conversation_id)})

@app.post("/api/ai/clear/{conversation_id}")
def ai_clear(conversation_id: str) -> JSONResponse:
    clear_ai_conversation(conversation_id)
    return JSONResponse({"status": "ok", "conversation_id": conversation_id})

class AIVoiceRequest(BaseModel):
    text: str

@app.post("/api/ai/voice")
def ai_voice_parse(req: AIVoiceRequest) -> JSONResponse:
    """Fast local parse of a voice command without LLM round-trip."""
    return JSONResponse(parse_voice_command(req.text))

@app.get("/api/position")
async def position() -> JSONResponse:
    """Query MPV for live playback position/duration (via IPC)."""
    # Blocking socket I/O runs in a worker thread rather than shelling out to
    # a python3 subprocess per poll — the UI hits this every 3 seconds.
    t, d, paused = await asyncio.gather(
        asyncio.to_thread(get_property, "time-pos"),
        asyncio.to_thread(get_property, "duration"),
        asyncio.to_thread(get_property, "pause"),
    )
    time_pos = float(t) if isinstance(t, (int, float)) else None
    duration = float(d) if isinstance(d, (int, float)) else None

    if time_pos is None and duration is None:
        return JSONResponse({"playing": False})
    return JSONResponse({
        "playing": True,
        "time": time_pos,
        "duration": duration,
        "paused": bool(paused),
    })


@app.post("/api/checkpoint")
async def force_checkpoint() -> JSONResponse:
    """Persist the current position to history now.

    The background loop does this every CHECKPOINT_INTERVAL_S; this endpoint
    exists so the UI can flush on stop/quit and tests can verify the path.
    """
    try:
        written = await asyncio.to_thread(checkpoint)
    except Exception as e:
        log.warning('manual checkpoint failed: %s', e)
        return JSONResponse({'status': 'warn', 'detail': str(e)}, status_code=200)
    return JSONResponse({'status': 'ok', 'written': written})

def _quality_height() -> int:
    """Resolve the user's default_quality setting to a max height (px)."""
    try:
        cfg = Path(__file__).resolve().parent.parent.parent / 'config' / 'settings.json'
        q = json.loads(cfg.read_text()).get('default_quality', '1080p')
    except Exception:
        q = '1080p'
    return {'720p': 720, '1080p': 1080, '4k': 2160, '2160p': 2160}.get(str(q).lower(), 1080)

def _mpv_format_string() -> str:
    h = _quality_height()
    return (
        f"bestvideo[height<={h}][vcodec^=avc1]+bestaudio[acodec^=mp4a]/"
        f"bestvideo[height<={h}][vcodec^=vp9]+bestaudio[acodec^=opus]/"
        f"best[height<={h}]"
    )

# ── App / Plugin mounting ─────────────────────────────────────────────────────

registry = AppRegistry()
registry.load_plugins()
registry.load_apps()

app.mount(
    "/shared",
    StaticFiles(directory=str(Path(__file__).resolve().parent.parent.parent / "shared"), html=False),
    name="shared-root",
)
app.include_router(history_router)
app.include_router(settings_router)
app.include_router(metadata_router)
app.include_router(subtitles_router)
app.include_router(playback_router)
app.include_router(system_router)

# Explicit routes for the phone remote and now-playing overlay. These must be
# declared before the static mount at "/" so they aren't shadowed.
_FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"

@app.get("/remote", include_in_schema=False)
def remote_page() -> HTMLResponse:
    return HTMLResponse((_FRONTEND_DIR / "remote.html").read_text())

@app.get("/now-playing", include_in_schema=False)
def now_playing_page() -> HTMLResponse:
    return HTMLResponse((_FRONTEND_DIR / "now-playing.html").read_text())

for app_id, manifest in registry.apps.items():
    frontend_path = Path(__file__).parent.parent.parent / "apps" / app_id / manifest["entry"]["frontend"]
    if frontend_path.exists():
        app.mount("/apps-frontend/" + app_id, StaticFiles(directory=str(frontend_path.parent), html=True), name="app-frontend-" + app_id)
    router = registry.app_router(app_id)
    if router is not None:
        app.include_router(router, prefix="/apps/" + app_id, tags=["app-" + app_id])

app.mount(
    "/",
    StaticFiles(directory=str(Path(__file__).resolve().parent.parent / "frontend"), html=True),
    name="main-frontend",
)

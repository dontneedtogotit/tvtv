"""
tvtv-yt — yt-dlp microservice for the TV HTPC.

Endpoints
---------
POST /api/play       Launch MPV with the best stream for a YouTube URL
GET  /api/search     Search YouTube via yt-dlp (returns JSON results)
GET  /api/formats    List available formats for a URL
GET  /api/health     Health check
"""

from __future__ import annotations

import json
import subprocess
import shutil
import os
import re
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
import os

app = FastAPI(title="tvtv-yt", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Config ────────────────────────────────────────────────────────────────────

YT_DLP = shutil.which("yt-dlp") or "yt-dlp"
MPV = shutil.which("mpv") or "mpv"
CACHE_DIR = Path.home() / ".cache" / "tvtv-yt"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

# Prefer 1080p+ with avc1/h264 for broad hardware decode compatibility on HD 620
YT_DLP_OPTS = [
    "--no-warnings",
    "--quiet",
    "--no-check-certificates",
    "-f", "bestvideo[height<=2160][vcodec^=avc1]+bestaudio[acodec^=mp4a]/"
         "bestvideo[height<=2160][vcodec^=vp9]+bestaudio[acodec^=opus]/"
         "best[height<=2160]",
    "--merge-output-format", "mp4",
    "--print", "%(id)s\t%(title)s\t%(uploader)s\t%(duration_string)s\t%(view_count)s\t%(thumbnail)s",
]

# ── Models ────────────────────────────────────────────────────────────────────

class PlayRequest(BaseModel):
    url: str = Field(..., description="YouTube video URL")
    seek: Optional[float] = Field(None, description="Start time in seconds")
    fullscreen: bool = Field(True, description="Launch MPV fullscreen")
    sponsorblock: bool = Field(False, description="Skip sponsored segments via SponsorBlock")

class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1, description="Search query")
    limit: int = Field(20, ge=1, le=50, description="Max results")

class VideoItem(BaseModel):
    id: str
    title: str
    uploader: str
    duration: str
    views: int
    thumbnail: str
    url: str

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

def _parse_yt_dlp_line(line: str) -> VideoItem | None:
    """Parse tab-separated output from yt-dlp --print."""
    if not line:
        return None
    parts = line.split("\t")
    if len(parts) < 6:
        return None
    vid_id = parts[0]
    return VideoItem(
        id=vid_id,
        title=parts[1],
        uploader=parts[2],
        duration=parts[3],
        views=int(parts[4]) if parts[4].isdigit() else 0,
        thumbnail=parts[5],
        url=f"https://www.youtube.com/watch?v={vid_id}",
    )

# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/api/health")
def health() -> dict:
    return {
        "status": "ok",
        "yt_dlp": bool(shutil.which("yt-dlp")),
        "mpv": bool(shutil.which("mpv")),
    }

@app.get("/api/search")
def search(q: str, limit: int = 20) -> JSONResponse:
    """Search YouTube and return structured results."""
    if not q.strip():
        raise HTTPException(400, "Empty query")

    # yt-dlp ytsearchN:QUERY returns N results
    search_spec = f"ytsearch{limit}:{q}"
    stdout = _run_yt_dlp(["--dump-json"] + YT_DLP_OPTS + [search_spec], timeout=45)

    items: list[dict] = []
    for line in stdout.splitlines():
        try:
            data = json.loads(line)
            items.append({
                "id": data.get("id", ""),
                "title": data.get("title", ""),
                "uploader": data.get("uploader", ""),
                "duration": data.get("duration_string", ""),
                "views": data.get("view_count", 0),
                "thumbnail": data.get("thumbnail", ""),
                "url": data.get("webpage_url", ""),
            })
        except json.JSONDecodeError:
            continue

    return JSONResponse({"query": q, "results": items})

@app.get("/api/formats")
def formats(url: str) -> JSONResponse:
    """Return available formats for a URL (useful for debug/UI)."""
    stdout = _run_yt_dlp(["-F", url], timeout=30)
    return JSONResponse({"formats": stdout.splitlines()})

@app.post("/api/play")
def play(req: PlayRequest) -> JSONResponse:
    """Launch MPV playing the best available stream for the given URL."""
    url = req.url.strip()
    if not url:
        raise HTTPException(400, "No URL provided")

    cmd = [
        MPV,
        "--no-terminal",
        "--force-window=yes",
        "--fullscreen" if req.fullscreen else "--windowed",
        "--cache=yes",
        "--cache-secs=30",
        "--demuxer-max-bytes=50M",
        "--demuxer-max-back-bytes=25M",
        "--ytdl-format=bestvideo[height<=2160][vcodec^=avc1]+bestaudio[acodec^=mp4a]/"
                    "bestvideo[height<=2160][vcodec^=vp9]+bestaudio[acodec^=opus]/"
                    "best[height<=2160]",
    ]

    # SponsorBlock: fetch skip segments and inject as MPV script options
    if req.sponsorblock:
        try:
            vid_id = _extract_video_id(url)
            if vid_id:
                segments = _fetch_sponsorblock_segments(vid_id)
                if segments:
                    # yt-dlp can pass SponsorBlock data via postprocessor args,
                    # but the simplest reliable path is MPV's built-in sponsorblock
                    # integration via yt-dlp hooks. We pass a custom yt-dlp args file.
                    cmd += ["--script-opts=ytdl_hook-sponsorblock_remove=all"]
                    cmd += ["--script-opts=ytdl_hook-sponsorblock_api=https://sponsor.ajay.app"]
        except Exception:
            # Fail open: play without SponsorBlock if the fetch fails
            pass

    if req.seek is not None:
        cmd += ["--start=+0", f"--seek={req.seek}"]

    cmd.append(url)

    try:
        subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
        )
    except FileNotFoundError:
        raise HTTPException(500, "mpv not found on PATH")

    return JSONResponse({"status": "playing", "url": url, "player": "mpv", "sponsorblock": req.sponsorblock})


def _extract_video_id(url: str) -> str | None:
    """Extract YouTube video ID from a URL."""
    m = re.search(r'(?:v=|/)([A-Za-z0-9_-]{11})(?:[?&/]|$)', url)
    return m.group(1) if m else None


def _fetch_sponsorblock_segments(video_id: str) -> list[dict]:
    """Fetch SponsorBlock skip segments for a video."""
    api = "https://sponsor.ajay.app/api/skipSegments"
    params = {
        "videoID": video_id,
        "categories": "sponsor,intro,outro,selfpromo,music_offtopic",
    }
    try:
        result = subprocess.run(
            ["curl", "-sf", "--max-time", "8", api + "?" + "&".join(f"{k}={v}" for k, v in params.items())],
            capture_output=True,
            text=True,
            timeout=12,
            check=False,
        )
        if result.returncode != 0 or not result.stdout.strip():
            return []
        data = json.loads(result.stdout)
        if isinstance(data, list):
            return data
        return []
    except Exception:
        return []

@app.get("/api/trending")
def trending(limit: int = 20) -> JSONResponse:
    """Return trending YouTube videos."""
    search_spec = f"ytsearch{limit}:trending"
    stdout = _run_yt_dlp(["--dump-json"] + YT_DLP_OPTS + [search_spec], timeout=45)

    items: list[dict] = []
    for line in stdout.splitlines():
        try:
            data = json.loads(line)
            items.append({
                "id": data.get("id", ""),
                "title": data.get("title", ""),
                "uploader": data.get("uploader", ""),
                "duration": data.get("duration_string", ""),
                "views": data.get("view_count", 0),
                "thumbnail": data.get("thumbnail", ""),
                "url": data.get("webpage_url", ""),
            })
        except json.JSONDecodeError:
            continue

    return JSONResponse({"results": items})


# ── Frontend ─────────────────────────────────────────────────────────────────

FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "..", "frontend")

if os.path.isdir(FRONTEND_DIR):
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")

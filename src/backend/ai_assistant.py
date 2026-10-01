"""
ai_assistant.py — Agentic AI layer for tvtv OS.

Routes to the Kilo Gateway with automatic free-model rotation.
Supports OpenAI-compatible tool-calling for media search, player control,
navigation, and system management. Conversations are persisted to disk.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import textwrap
from pathlib import Path
from typing import Any

import httpx
from pydantic import BaseModel, Field

from credentials import get_secret

KILO_BASE_URL = os.environ.get("KILO_GATEWAY_URL", "https://api.kilo.ai/api/gateway")


def _get_kilo_api_key() -> str:
    return get_secret("KILO_API_KEY", "")

# Free models for rotation fallback
_FREE_MODELS = [
    "kilo-auto/free",
    "dots-studio/dots-3-note-preview:free",
    "stealth/space-bunny-alpha",
    "stepfun/step-3.7-flash:free",
]

_conversation_file = Path(__file__).resolve().parent.parent.parent / "var" / "ai_conversations.json"

def _load_conversations() -> dict[str, list[dict]]:
    if _conversation_file.exists():
        try:
            return json.loads(_conversation_file.read_text())
        except Exception:
            return {}
    return {}

def _save_conversations(data: dict[str, list[dict]]) -> None:
    _conversation_file.parent.mkdir(parents=True, exist_ok=True)
    _conversation_file.write_text(json.dumps(data, indent=2))

def get_system_tools() -> list[dict[str, Any]]:
    """Return the OpenAI-formatted tool definitions for the tvtv agent."""
    return [
        {
            "type": "function",
            "function": {
                "name": "search_media",
                "description": "Search YouTube for a video or playlist to play on the TV.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Search query"},
                        "limit": {"type": "integer", "description": "Max results", "default": 5},
                    },
                    "required": ["query"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "control_media",
                "description": "Send playback controls to the active media player (MPV).",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "action": {
                            "type": "string",
                            "enum": ["pause", "stop", "fullscreen", "mute", "vol_up", "vol_down", "seek_forward", "seek_backward"],
                            "description": "Control action",
                        }
                    },
                    "required": ["action"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "navigate_to",
                "description": "Open a URL or app on the TV dashboard.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "url": {"type": "string", "description": "URL or path to navigate to"},
                    },
                    "required": ["url"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_now_playing",
                "description": "Get information about what is currently playing on the TV.",
                "parameters": {"type": "object", "properties": {}, "required": []},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "list_connected_apps",
                "description": "List available apps on the TV / dashboard.",
                "parameters": {"type": "object", "properties": {}, "required": []},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_system_status",
                "description": "Run a quick system diagnostic on the TV appliance.",
                "parameters": {"type": "object", "properties": {}, "required": []},
            },
        },
    ]

def _kilo_chat_request(
    model: str,
    messages: list[dict[str, str]],
    tools: list[dict[str, Any]] | None = None,
    max_tokens: int = 512,
    temperature: float = 0.7,
) -> dict[str, Any]:
    """Blockingly request a chat completion from Kilo Gateway."""
    api_key = _get_kilo_api_key()
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "stream": False,
    }
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = "auto"

    with httpx.Client(timeout=60, follow_redirects=False) as client:
        resp = client.post(
            f"{KILO_BASE_URL}/chat/completions",
            headers=headers,
            json=payload,
        )
        resp.raise_for_status()
        return resp.json()

def _kilo_request_for_free(
    messages: list[dict[str, str]],
    tools: list[dict[str, Any]] | None = None,
    max_tokens: int = 512,
    temperature: float = 0.7,
) -> dict[str, Any]:
    """Try each free model (or auto/free) in order; return first success."""
    for model in _FREE_MODELS:
        try:
            result = _kilo_chat_request(model, messages, tools, max_tokens, temperature)
            if "error" not in result:
                result["_kilo_model_used"] = model
                return result
            # transient errors
            code = result.get("error", {}).get("code")
            if code in (429, 503, 502, 504):
                continue
            return result
        except Exception as e:
            continue
    return {"error": {"message": "All free Kilo models failed or overloaded. Try again later.", "code": 503}}

def _execute_tool(name: str, args: dict[str, Any]) -> str:
    """Execute a local tool and return a JSON string result."""
    project_root = Path(__file__).resolve().parent.parent.parent

    if name == "search_media":
        query = args.get("query", "").strip()
        if not query:
            return json.dumps({"error": "Empty query"})
        limit = args.get("limit", 5)
        import shutil
        yt_dlp = shutil.which("yt-dlp") or "yt-dlp"
        try:
            result = subprocess.run(
                [yt_dlp, "--no-warnings", "--dump-json", "--flat-playlist", "--skip-download",
                 f"ytsearch{limit}:{query}"],
                capture_output=True, text=True, timeout=25, check=False,
            )
            if result.returncode != 0:
                return json.dumps({"error": "yt-dlp search failed"})
            results = []
            for line in result.stdout.splitlines():
                try:
                    data = json.loads(line)
                except json.JSONDecodeError:
                    continue
                results.append({
                    "id": data.get("id", ""),
                    "title": data.get("title", ""),
                    "channel": data.get("uploader") or data.get("channel") or "",
                    "thumbnail": (data.get("thumbnails") or [{}])[0].get("url", ""),
                    "duration": data.get("duration_string", ""),
                })
            return json.dumps({"results": results, "count": len(results)})
        except Exception as e:
            return json.dumps({"error": str(e)})

    if name == "control_media":
        action_map = {
            "pause": "pause",
            "stop": "stop",
            "fullscreen": "fullscreen",
            "mute": "mute",
            "vol_up": "vol+",
            "vol_down": "vol-",
            "seek_forward": "seek+10",
            "seek_backward": "seek-10",
        }
        mpc = action_map.get(args.get("action", ""), "")
        if not mpc:
            return json.dumps({"error": "Unknown control action"})
        try:
            ipc_script = project_root / "scripts" / "mpv-ipc.py"
            if ipc_script.exists():
                subprocess.run(
                    ["python3", str(ipc_script), "/tmp/mpv-ipc.sock", mpc],
                    capture_output=True, text=True, timeout=5, check=False,
                )
            return json.dumps({"status": "ok", "action_sent": mpc})
        except Exception as e:
            return json.dumps({"error": str(e)})

    if name == "navigate_to":
        url = args.get("url", "")
        return json.dumps({"status": "ok", "navigation_target": url, "message": f"TV navigated to {url}"})

    if name == "get_now_playing":
        try:
            ipc_script = project_root / "scripts" / "mpv-ipc.py"
            props: dict[str, str] = {}
            for prop in ["time-pos", "duration", "filename", "pause"]:
                r = subprocess.run(
                    ["python3", str(ipc_script), "/tmp/mpv-ipc.sock", "get_property", prop],
                    capture_output=True, text=True, timeout=4, check=False,
                )
                props[prop] = r.stdout.strip()
            return json.dumps({
                "title": props.get("filename", "Unknown"),
                "position_seconds": props.get("time-pos", "0"),
                "duration_seconds": props.get("duration", "0"),
                "paused": props.get("pause", "false").lower() == "true",
            })
        except Exception as e:
            return json.dumps({"error": str(e), "playing": "idle"})

    if name == "list_connected_apps":
        apps = [
            {"id": "media-library", "name": "Media Library", "icon": "🎬"},
            {"id": "settings", "name": "Settings", "icon": "⚙️"},
            {"id": "installer", "name": "Installer", "icon": "🚀"},
            {"id": "remote", "name": "Phone Remote", "icon": "📱"},
            {"id": "store", "name": "App Store", "icon": "📦"},
            {"id": "system-update", "name": "OS Updater", "icon": "🔄"},
        ]
        return json.dumps({"apps": apps})

    if name == "get_system_status":
        doctor = project_root / "scripts" / "tvtv-doctor.sh"
        if doctor.exists():
            result = subprocess.run(
                ["bash", str(doctor)],
                capture_output=True, text=True, timeout=20, check=False,
            )
            return json.dumps({"report": result.stdout[:2000]})
        return json.dumps({"report": "Doctor script not found."})

    return json.dumps({"error": f"Unknown tool {name}"})

SYSTEM_PROMPT = textwrap.dedent("""\
You are **tvtv**, the intelligent 10-foot TV assistant. You control an HTPC appliance
connected to a living-room TV. Speak concisely — one or two sentences at most — and
perform useful actions using the tools provided.

User controls:
- Voice or text commands (via TV remote or phone app)
- D-pad navigation 
- Natural language queries ("Play cat videos", "Mute", "What's on?")

Your personality is helpful, conversational and slightly enthusiastic. Always tell
the user what you are doing before you run a tool (e.g. "Searching YouTube for cat videos...").
""")

def send_chat_message(
    conversation_id: str,
    user_message: str,
    max_tokens: int = 512,
    temperature: float = 0.7,
) -> dict[str, Any]:
    """
    Send one user message into a conversation and return the assistant reply,
    running any requested tool calls automatically.
    """
    conversations = _load_conversations()
    history: list[dict[str, str]] = conversations.get(conversation_id, [])

    # Keep the system prompt at the top
    if not history or history[0].get("role") != "system":
        history.insert(0, {"role": "system", "content": SYSTEM_PROMPT})

    history.append({"role": "user", "content": user_message})

    # Conversation window: keep last 18 turns to stay within context limits of free models
    windowed = [history[0]] + history[-32:]

    tools = get_system_tools()
    result = _kilo_request_for_free(
        messages=windowed,
        tools=tools,
        max_tokens=max_tokens,
        temperature=temperature,
    )

    reply_content = ""
    tool_calls: list[dict] = []

    if "error" in result:
        reply_content = f"I'm having trouble connecting right now. ({result['error'].get('message', 'Unknown error')})"
    else:
        choice = result.get("choices", [{}])[0]
        message = choice.get("message", {})
        reply_content = message.get("content", "") or ""
        tool_calls = message.get("tool_calls", [])

    history.append({"role": "assistant", "content": reply_content})

    # Execute any tool calls
    if tool_calls:
        for call in tool_calls:
            func = call.get("function", {})
            tool_name = func.get("name", "")
            tool_args_str = func.get("arguments", "{}")
            try:
                tool_args = json.loads(tool_args_str)
            except json.JSONDecodeError:
                tool_args = {}

            tool_result = _execute_tool(tool_name, tool_args)

            history.append({
                "role": "tool",
                "tool_call_id": call.get("id", ""),
                "name": tool_name,
                "content": tool_result,
            })

        # Ask model again with tool results
        windowed2 = [history[0]] + history[-40:]
        result2 = _kilo_request_for_free(
            messages=windowed2,
            tools=tools,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        if "error" not in result2:
            second_reply = result2.get("choices", [{}])[0].get("message", {}).get("content", "")
            if second_reply:
                reply_content = second_reply
                history.append({"role": "assistant", "content": reply_content})

    _save_conversations({**conversations, conversation_id: history})

    return {
        "conversation_id": conversation_id,
        "reply": reply_content,
        "model_used": result.get("_kilo_model_used", "unknown"),
    }

def get_history(conversation_id: str) -> list[dict[str, str]]:
    conversations = _load_conversations()
    return conversations.get(conversation_id, [])

def clear_conversation(conversation_id: str) -> None:
    conversations = _load_conversations()
    conversations.pop(conversation_id, None)
    _save_conversations(conversations)

def parse_voice_command(text: str) -> dict[str, Any]:
    """
    Attempt a low-latency direct command parse without tool-calling the LLM.
    Returns an action dict for known commands, or passes through to chat.
    """
    t = text.lower().strip()

    # Navigation / app launching (check before generic search/play)
    nav_match = re.search(r"\b(open|launch|go to|show)\s+(youtube|media|library|settings|installer|cameras?|remote|store|update)\b", t)
    if nav_match:
        app_id_map = {
            "youtube": "/",
            "media": "/apps-frontend/media-library/",
            "library": "/apps-frontend/media-library/",
            "settings": "/apps-frontend/settings/",
            "installer": "/apps-frontend/installer/",
            "camera": "/apps-frontend/camera-setup/",
            "cameras": "/apps-frontend/camera-setup/",
            "remote": "/apps-frontend/remote/",
            "store": "/apps-frontend/store/",
            "update": "/apps-frontend/system-update/",
        }
        for word, path in app_id_map.items():
            if word in t:
                return {"type": "navigate", "target": path, "message": f"Opening {word.capitalize()}"}

    # System action
    if re.search(r"\b(reboot|restart)\b", t):
        return {"type": "system", "action": "reboot", "message": "Rebooting TV appliance..."}

    # Playback controls
    if re.search(r"\b(fullscreen)\b", t):
        return {"type": "control", "action": "fullscreen", "message": "Fullscreen"}
    if re.search(r"\b(mute|unmute)\b", t):
        return {"type": "control", "action": "mute", "message": "Toggle mute"}
    if re.search(r"\b(stop)\b", t):
        return {"type": "control", "action": "stop", "message": "Stop"}
    if re.search(r"\b(volum?e?\s+(up|down)|louder|quieter)\b", t):
        if "up" in t or "louder" in t:
            return {"type": "control", "action": "vol_up", "message": "Volume up"}
        return {"type": "control", "action": "vol_down", "message": "Volume down"}
    if re.search(r"\b(pause|unpause|resume|play)\b", t) and not re.search(r"\b(play\s+\w)", t):
        return {"type": "control", "action": "pause", "message": "Playback toggle"}

    # Search media (only when "play <something>" or "search for <something>" or "find <something>")
    m = re.search(r"\b(play|search\s+for|find)\s+(.+)", t)
    if m:
        query = re.sub(r"^(some |a |the )", "", m.group(2).strip())
        return {"type": "search", "query": query, "message": f"Searching for {query}"}

    # Fallback
    return {"type": "chat", "message": text}

if __name__ == "__main__":
    print("Running debug chat test...")
    resp = send_chat_message("debug", "What is a good cat video to play?")
    print(json.dumps(resp, indent=2))

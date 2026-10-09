"""Chromium native web browser app backend."""
from __future__ import annotations

import logging
import os
import shutil
import subprocess
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(tags=["chromium"])
log = logging.getLogger("tvtv.app.chromium")

DEFAULT_BOOKMARKS = [
    {"id": "youtube", "name": "YouTube", "url": "https://www.youtube.com", "icon": "▶️", "category": "Video"},
    {"id": "netflix", "name": "Netflix", "url": "https://www.netflix.com", "icon": "🎬", "category": "Streaming"},
    {"id": "prime", "name": "Prime Video", "url": "https://www.primevideo.com", "icon": "🍿", "category": "Streaming"},
    {"id": "disney", "name": "Disney+", "url": "https://www.disneyplus.com", "icon": "✨", "category": "Streaming"},
    {"id": "twitch", "name": "Twitch TV", "url": "https://www.twitch.tv", "icon": "🎮", "category": "Live Streams"},
    {"id": "spotify", "name": "Spotify Web", "url": "https://open.spotify.com", "icon": "🎵", "category": "Music"},
    {"id": "plex", "name": "Plex Web", "url": "https://app.plex.tv", "icon": "📺", "category": "Media"},
    {"id": "reddit", "name": "Reddit", "url": "https://www.reddit.com", "icon": "💬", "category": "Social"},
    {"id": "wikipedia", "name": "Wikipedia", "url": "https://www.wikipedia.org", "icon": "📚", "category": "Knowledge"},
    {"id": "duckduckgo", "name": "DuckDuckGo Search", "url": "https://duckduckgo.com", "icon": "🔍", "category": "Search"},
]


def _find_browser_binary() -> tuple[str, str]:
    for b in ("chromium", "chromium-browser", "google-chrome-stable", "google-chrome", "brave-browser", "firefox"):
        p = shutil.which(b)
        if p:
            return b, p
    return "", ""


@router.get("/status")
def status() -> dict:
    name, path = _find_browser_binary()
    version = "unknown"
    if path:
        try:
            res = subprocess.run([path, "--version"], capture_output=True, text=True, timeout=3)
            if res.returncode == 0:
                version = res.stdout.strip()
        except Exception:
            pass
    return {
        "installed": bool(path),
        "binary_name": name,
        "binary_path": path,
        "version": version,
    }


@router.get("/bookmarks")
def bookmarks() -> dict:
    return {"bookmarks": DEFAULT_BOOKMARKS}


class LaunchBrowserRequest(BaseModel):
    url: str = Field("https://duckduckgo.com", description="Target website URL")
    kiosk: bool = Field(False, description="Launch in fullscreen kiosk mode")
    windowed: bool = Field(True, description="Launch as window")


@router.post("/launch")
def launch_browser(req: LaunchBrowserRequest) -> dict:
    name, path = _find_browser_binary()
    if not path:
        raise HTTPException(404, "No browser binary (chromium/chrome) found on system PATH. Install via App Store.")

    target_url = req.url.strip()
    if not target_url:
        target_url = "https://duckduckgo.com"
    if not (target_url.startswith("http://") or target_url.startswith("https://") or target_url.startswith("file://")):
        if "." in target_url and not " " in target_url:
            target_url = f"https://{target_url}"
        else:
            import urllib.parse
            target_url = f"https://duckduckgo.com/?q={urllib.parse.quote(target_url)}"

    cmd = [path]
    if req.kiosk:
        cmd.append("--kiosk")
    cmd += [
        "--noerrdialogs",
        "--disable-infobars",
        "--enable-features=VaapiVideoDecodeLinuxGL,VaapiVideoDecoder",
        "--ignore-gpu-blocklist",
        "--enable-zero-copy",
        "--ozone-platform=x11",
        target_url,
    ]

    env = os.environ.copy()
    if "WAYLAND_DISPLAY" not in env:
        env["WAYLAND_DISPLAY"] = "wayland-0"
    if "DISPLAY" not in env:
        env["DISPLAY"] = ":0"

    try:
        proc = subprocess.Popen(
            cmd,
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        return {
            "status": "ok",
            "pid": proc.pid,
            "url": target_url,
            "browser": name,
            "message": f"Launched {name} -> {target_url}",
        }
    except Exception as e:
        raise HTTPException(500, f"Failed to launch browser: {e}")

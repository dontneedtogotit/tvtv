"""Managed MPV Session & Playback Lifecycle Controller.

P9-1, P9-3, P9-5: Manages the MPV playback process, socket IPC, property
observation, audio/subtitle track switching, and crash/exit watchdog.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from mpv import IPC_SOCKET, checkpoint, get_property, send_command
from playback import PlaybackState as PS, set_now_playing_state
from profile import mpv_args

log = logging.getLogger('tvtv.player')

MPV_BIN = shutil.which("mpv") or "mpv"


class PlayerManager:
    def __init__(self) -> None:
        self._process: Optional[subprocess.Popen] = None
        self._current_url: Optional[str] = None
        self._current_title: Optional[str] = None
        self._current_channel: Optional[str] = None
        self._current_thumbnail: Optional[str] = None
        self._start_time: float = 0.0

    @property
    def is_running(self) -> bool:
        if self._process is None:
            return False
        return self._process.poll() is None

    def stop(self) -> bool:
        """Gracefully stop MPV and clean up state."""
        try:
            checkpoint()
        except Exception:
            pass

        if self.is_running:
            try:
                send_command("quit")
                # Wait briefly for clean exit
                for _ in range(10):
                    if not self.is_running:
                        break
                    time.sleep(0.05)
            except Exception:
                pass

        if self._process and self.is_running:
            try:
                self._process.terminate()
            except Exception:
                pass

        self._process = None
        self._current_url = None
        set_now_playing_state(PS(
            url="",
            title="",
            active=False,
            status="stopped",
            updated_at=datetime.now(timezone.utc).isoformat(),
        ))
        return True

    def launch(
        self,
        url: str,
        title: Optional[str] = None,
        channel: Optional[str] = None,
        duration: Optional[float] = None,
        thumbnail: Optional[str] = None,
        seek: Optional[float] = None,
        fullscreen: bool = True,
        sponsorblock: bool = False,
        sponsorblock_categories: Optional[list[str]] = None,
        subtitle_url: Optional[str] = None,
        custom_args: Optional[list[str]] = None,
    ) -> dict[str, Any]:
        """Launch a new MPV instance, stopping any previous one first."""
        self.stop()

        cmd = [
            MPV_BIN,
            "--no-terminal",
            "--force-window=yes",
            "--fullscreen" if fullscreen else "--windowed",
            "--cache=yes",
            "--cache-secs=30",
            "--demuxer-max-bytes=50M",
            "--demuxer-max-back-bytes=25M",
            "--input-ipc-server=" + IPC_SOCKET,
        ]

        # Append TV profile args (--vo, --hwdec, --video-scale, passthrough)
        cmd += mpv_args()

        if subtitle_url and subtitle_url.strip():
            cmd.append(f"--sub-file={subtitle_url.strip()}")

        if sponsorblock:
            cats = sponsorblock_categories or ["sponsor", "intro", "outro", "selfpromo"]
            cats_str = ",".join(cats)
            cmd += [
                "--script-opts=ytdl_hook-sponsorblock_remove=all",
                f"--script-opts=ytdl_hook-sponsorblock_api=https://sponsor.ajay.app",
                f"--script-opts=ytdl_hook-sponsorblock_categories={cats_str}",
            ]

        if seek is not None and seek > 0:
            cmd += ["--start=+0", f"--seek={seek}"]

        if custom_args:
            cmd += custom_args

        cmd.append(url)

        log.info("Launching MPV: %s", " ".join(cmd[:10]))
        try:
            self._process = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
                start_new_session=True,
            )
        except FileNotFoundError:
            raise RuntimeError(f"mpv executable not found at '{MPV_BIN}'")

        self._current_url = url
        self._current_title = title or url
        self._current_channel = channel
        self._current_thumbnail = thumbnail
        self._start_time = time.time()

        from history import HistoryItem, _append_history
        _append_history(HistoryItem(
            url=url,
            title=self._current_title,
            position=seek or 0.0,
            duration=duration or 0.0,
            channel=channel,
            thumbnail=thumbnail,
        ))

        set_now_playing_state(PS(
            url=url,
            title=self._current_title,
            channel=channel,
            thumbnail=thumbnail,
            position=seek or 0.0,
            duration=duration or 0.0,
            active=True,
            status="playing",
            updated_at=datetime.now(timezone.utc).isoformat(),
        ))

        return {
            "status": "playing",
            "url": url,
            "title": self._current_title,
            "pid": self._process.pid,
            "subtitles": bool(subtitle_url),
        }

    def get_tracks(self) -> dict[str, list[dict[str, Any]]]:
        """Extract available audio and subtitle tracks from MPV (P9-3)."""
        if not self.is_running:
            return {"audio": [], "subtitles": []}

        track_list = get_property("track-list") or []
        audio_tracks = []
        sub_tracks = []

        if isinstance(track_list, list):
            for t in track_list:
                if not isinstance(t, dict):
                    continue
                t_type = t.get("type")
                entry = {
                    "id": t.get("id"),
                    "title": t.get("title") or t.get("lang") or f"Track {t.get('id')}",
                    "lang": t.get("lang", "und"),
                    "codec": t.get("codec"),
                    "selected": bool(t.get("selected")),
                    "external": bool(t.get("external")),
                }
                if t_type == "audio":
                    audio_tracks.append(entry)
                elif t_type == "sub":
                    sub_tracks.append(entry)

        return {"audio": audio_tracks, "subtitles": sub_tracks}

    def set_track(self, track_type: str, track_id: int) -> bool:
        """Select an audio or subtitle track by ID."""
        if not self.is_running:
            return False
        prop = "aid" if track_type == "audio" else "sid"
        try:
            send_command(f"set {prop} {track_id}")
            return True
        except Exception:
            return False

    def check_watchdog(self) -> None:
        """Called periodically: detects unexpected exit and updates state."""
        if self._process is not None and self._process.poll() is not None:
            # Player process ended
            exit_code = self._process.poll()
            log.info("MPV process ended with code %s", exit_code)
            self._process = None
            self._current_url = None
            set_now_playing_state(PS(
                url="",
                title="",
                active=False,
                status="stopped",
                updated_at=datetime.now(timezone.utc).isoformat(),
            ))


player = PlayerManager()

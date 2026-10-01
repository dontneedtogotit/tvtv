"""MPV IPC client and playback position checkpointing.

Two jobs:

1. Talk to MPV over its Unix socket directly from the backend. Every
   `/api/position` call previously shelled out to `python3 scripts/mpv-ipc.py`,
   which spawns an interpreter per query — the UI polls that every 3 seconds.

2. Persist the live playback position into history and now-playing state so
   Continue Watching and resume actually work. Previously nothing ever wrote
   a position after the initial seek, so a resumed video never appeared as
   "in progress".

Phase 9 replaces this polling loop with a single managed MPV session with
property observation. Until then this keeps one connection open instead of
spawning a process per query, and fails silently when MPV is not running.
"""

from __future__ import annotations

import json
import logging
import socket
from typing import Any, Optional

log = logging.getLogger('tvtv.mpv')

IPC_SOCKET = '/tmp/mpv-ipc.sock'

# How often to persist position. Short enough that a crash loses little,
# long enough not to thrash the history file.
CHECKPOINT_INTERVAL_S = 15.0

# Below this, a "position" is just the start of the video — not worth marking
# as in-progress, and it must never trigger a resume prompt.
MIN_RESUME_POSITION_S = 10.0

# A video this close to finished counts as watched.
COMPLETED_RATIO = 0.97


class MpvIPCError(RuntimeError):
    pass


def send_command(command: str, socket_path: str = IPC_SOCKET) -> str:
    """Send a raw text command. Raises MpvIPCError if MPV is unreachable."""
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        sock.settimeout(3.0)
        sock.connect(socket_path)
        sock.sendall((command + '\n').encode())
        return command
    except OSError as e:
        raise MpvIPCError(f'mpv IPC {socket_path}: {e}') from e
    finally:
        sock.close()


def get_property(prop: str, socket_path: str = IPC_SOCKET) -> Any:
    """Read one MPV property. Returns None when unavailable."""
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        sock.settimeout(3.0)
        sock.connect(socket_path)
        sock.sendall((json.dumps({'command': ['get_property', prop]}) + '\n').encode())
        raw = b''
        while b'\n' not in raw:
            chunk = sock.recv(65536)
            if not chunk:
                break
            raw += chunk
        if not raw:
            return None
        reply = json.loads(raw.split(b'\n', 1)[0].decode())
    except (OSError, json.JSONDecodeError) as e:
        log.debug('mpv property %s failed: %s', prop, e)
        return None
    finally:
        sock.close()
    if reply.get('error') != 'success':
        return None
    return reply.get('data')


def snapshot() -> Optional[dict[str, Any]]:
    """Current playback state from MPV, or None when nothing is playing."""
    path = get_property('path')
    if not path:
        return None
    time_pos = get_property('time-pos')
    duration = get_property('duration')
    paused = get_property('pause')
    media_title = get_property('media-title')
    return {
        'path': path,
        'time': float(time_pos) if isinstance(time_pos, (int, float)) else 0.0,
        'duration': float(duration) if isinstance(duration, (int, float)) else 0.0,
        'paused': bool(paused),
        'media_title': media_title or None,
    }


def checkpoint() -> bool:
    """Persist the live position into history + now-playing.

    Returns True when a checkpoint was written. Safe to call when MPV is not
    running: it just reports False.
    """
    state = snapshot()
    if state is None:
        return False

    from datetime import datetime, timezone
    from history import HistoryItem, _append_history, get_history
    from playback import PlaybackState as PS, set_now_playing_state

    url = state['path']
    position = state['time']
    duration = state['duration']

    # Preserve the human-readable title across restarts: MPV only knows the
    # path, so look up what we recorded when playback started.
    title = state['media_title'] or url
    channel = None
    thumbnail = None
    for item in get_history().get('items', []):
        if item.get('url') == url:
            title = item.get('title') or title
            channel = item.get('channel')
            thumbnail = item.get('thumbnail')
            break

    if position >= MIN_RESUME_POSITION_S and (
        duration <= 0 or position < duration * COMPLETED_RATIO
    ):
        _append_history(HistoryItem(
            url=url, title=title, position=position, duration=duration,
            channel=channel, thumbnail=thumbnail,
        ))
    else:
        # Finished (or barely started): keep the record but zero the
        # position so Continue Watching and the resume prompt drop it.
        _append_history(HistoryItem(
            url=url, title=title, position=0.0, duration=duration,
            channel=channel, thumbnail=thumbnail,
        ))

    set_now_playing_state(PS(
        url=url,
        title=title,
        channel=channel,
        thumbnail=thumbnail,
        position=position,
        duration=duration,
        active=True,
        status='paused' if state['paused'] else 'playing',
        updated_at=datetime.now(timezone.utc).isoformat(),
    ))
    return True


def mpv_running(socket_path: str = IPC_SOCKET) -> bool:
    try:
        send_command('get_property path', socket_path)
        return True
    except MpvIPCError:
        return False

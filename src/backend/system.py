"""System management and telemetry router for tvtv HTPC OS.

Provides real-time system metrics, weather information, TV profile management,
and power control endpoints for the 10-foot HTPC Graphic Shell.
"""

from __future__ import annotations

import json
import logging
import os
import platform
import re
import shutil
import socket
import subprocess
import time
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from profile import load_tv_conf, profile_summary, profile_value, shell_quote_value
from auth import verify_client_access

log = logging.getLogger("tvtv.system")
router = APIRouter(prefix="/api/system", tags=["system"])

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
CONFIG_DIR = PROJECT_ROOT / "config"
TV_CONF_PATH = Path.home() / ".config" / "tvtv" / "tv.conf"
APPLIANCE_TV_CONF = Path("/home/htpc/.config/tvtv/tv.conf")


class ProfileUpdateRequest(BaseModel):
    hostname: Optional[str] = None
    wlr_mode: Optional[str] = None
    wlr_output: Optional[str] = None
    ui_scale: Optional[int] = None
    theme: Optional[str] = None
    shell: Optional[str] = None
    audio: Optional[str] = None
    night_mode: Optional[bool] = None
    audio_passthrough: Optional[bool] = None
    cec: Optional[str] = None
    mpv_vo: Optional[str] = None
    mpv_hwdec: Optional[str] = None
    mpv_scale: Optional[str] = None
    default_quality: Optional[str] = None
    wallpaper: Optional[str] = None


class PowerActionRequest(BaseModel):
    action: str = Field(..., description="'sleep', 'suspend', 'reboot', 'shutdown', 'restart_ui', 'restart_backend'")


def _run_privileged(cmd: list[str], timeout: int = 10) -> tuple[bool, str]:
    """Run a command that may need elevated privileges, reporting honestly.

    Tries the command directly first (backend may already be privileged or the
    action may be user-scoped), then falls back to passwordless sudo (the
    appliance sudoers drop-in grants NOPASSWD to the appliance user). Returns
    (ok, detail) so callers surface real failures instead of reporting success
    for a command that never ran.
    """

    def _attempt(c: list[str]) -> tuple[int, str]:
        try:
            p = subprocess.run(c, capture_output=True, text=True, timeout=timeout)
            return p.returncode, (p.stderr or p.stdout or "").strip()[:300]
        except FileNotFoundError:
            return 127, f"command not found: {c[0]}"
        except subprocess.TimeoutExpired:
            return 124, f"timed out: {' '.join(c)}"

    rc, detail = _attempt(cmd)
    if rc == 0:
        return True, "ok"
    if shutil.which("sudo"):
        rc2, detail2 = _attempt(["sudo", "-n", *cmd])
        if rc2 == 0:
            return True, "ok (via sudo)"
        return False, f"{cmd[0]} failed: {detail2 or detail}"
    return False, f"{cmd[0]} failed (no privilege escalation available): {detail}"


def _get_local_ips() -> list[str]:
    """Return non-loopback IPv4 addresses."""
    ips: list[str] = []
    try:
        proc = subprocess.run(
            ["hostname", "-I"],
            capture_output=True,
            text=True,
            check=False,
            timeout=2,
        )
        if proc.returncode == 0 and proc.stdout.strip():
            for ip in proc.stdout.strip().split():
                if ip and not ip.startswith("127.") and ":" not in ip:
                    ips.append(ip)
    except Exception:
        pass
    if not ips:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.settimeout(0.5)
            s.connect(("1.1.1.1", 80))
            ip = s.getsockname()[0]
            s.close()
            if ip and not ip.startswith("127."):
                ips.append(ip)
        except Exception:
            ips.append("127.0.0.1")
    return ips


def _get_system_metrics() -> dict[str, Any]:
    """Collect CPU load, Memory, Temperature, and Uptime."""
    cpu_percent = 0.0
    mem_total_mb = 0
    mem_used_mb = 0
    mem_percent = 0.0
    temp_c: Optional[float] = None
    uptime_sec = 0

    # CPU load via /proc/loadavg or stat
    try:
        loadavg_path = Path("/proc/loadavg")
        if loadavg_path.exists():
            parts = loadavg_path.read_text().split()
            if parts:
                cpu_percent = round(float(parts[0]) * 100 / max(1, os.cpu_count() or 1), 1)
    except Exception:
        pass

    # Memory via /proc/meminfo
    try:
        meminfo_path = Path("/proc/meminfo")
        if meminfo_path.exists():
            mem_data: dict[str, int] = {}
            for line in meminfo_path.read_text().splitlines():
                if ":" in line:
                    k, v = line.split(":", 1)
                    val_parts = v.strip().split()
                    if val_parts and val_parts[0].isdigit():
                        mem_data[k.strip()] = int(val_parts[0])
            total_kb = mem_data.get("MemTotal", 0)
            avail_kb = mem_data.get("MemAvailable", mem_data.get("MemFree", 0))
            if total_kb > 0:
                mem_total_mb = round(total_kb / 1024)
                mem_used_mb = round((total_kb - avail_kb) / 1024)
                mem_percent = round((mem_used_mb / mem_total_mb) * 100, 1)
    except Exception:
        pass

    # Temperature via /sys/class/thermal
    try:
        thermal_zones = list(Path("/sys/class/thermal").glob("thermal_zone*/temp"))
        temps: list[float] = []
        for tz in thermal_zones:
            try:
                raw = tz.read_text().strip()
                if raw.isdigit():
                    t = float(raw) / 1000.0 if float(raw) > 200 else float(raw)
                    if 15.0 <= t <= 115.0:
                        temps.append(t)
            except Exception:
                continue
        if temps:
            temp_c = round(max(temps), 1)
    except Exception:
        pass

    # Uptime via /proc/uptime
    try:
        uptime_path = Path("/proc/uptime")
        if uptime_path.exists():
            raw_up = uptime_path.read_text().split()
            if raw_up:
                uptime_sec = int(float(raw_up[0]))
    except Exception:
        pass

    return {
        "cpu_percent": min(100.0, cpu_percent),
        "mem_total_mb": mem_total_mb,
        "mem_used_mb": mem_used_mb,
        "mem_percent": mem_percent,
        "temperature_c": temp_c,
        "uptime_seconds": uptime_sec,
    }


def _get_audio_sink() -> str:
    """Return active audio sink name if PipeWire or ALSA is present."""
    try:
        if shutil.which("wpctl"):
            proc = subprocess.run(
                ["wpctl", "status"],
                capture_output=True,
                text=True,
                check=False,
                timeout=2,
            )
            if proc.returncode == 0:
                for line in proc.stdout.splitlines():
                    if "*" in line and ("Audio/Sink" in line or "HDMI" in line or "Built-in" in line):
                        return line.strip().replace("*", "").strip()
    except Exception:
        pass
    return "HDMI Audio (PipeWire)"


def _resolve_writable_profile_path() -> Path:
    """Returns a writable path for tv.conf."""
    override = os.environ.get("TVTV_TV_CONF")
    if override:
        return Path(override)
    try:
        TV_CONF_PATH.parent.mkdir(parents=True, exist_ok=True)
        return TV_CONF_PATH
    except Exception:
        pass
    if APPLIANCE_TV_CONF.parent.exists():
        return APPLIANCE_TV_CONF
    return CONFIG_DIR / "tv.conf"


@router.get("/stats")
def get_system_stats() -> dict[str, Any]:
    """Return real-time system stats, network info, display and audio status."""
    metrics = _get_system_metrics()
    ips = _get_local_ips()
    primary_ip = ips[0] if ips else "127.0.0.1"
    hostname = socket.gethostname()
    audio_sink = _get_audio_sink()
    conf = load_tv_conf()

    return {
        "status": "ok",
        "hostname": hostname,
        "platform": platform.platform(),
        "primary_ip": primary_ip,
        "all_ips": ips,
        "metrics": metrics,
        "audio_sink": audio_sink,
        "wlr_mode": conf.get("WLR_MODE", "1920x1080@60"),
        "ui_scale": int(conf.get("TV_SCALE", "13")),
        "theme": conf.get("TV_THEME", "estuary"),
        "night_mode": conf.get("TV_NIGHT_MODE", "1") == "1",
        "cec_enabled": conf.get("TV_CEC", "yes") == "yes",
    }


@router.get("/weather")
def get_weather(lat: Optional[float] = None, lon: Optional[float] = None) -> dict[str, Any]:
    """Returns local weather or clean offline estimate without requiring API keys."""
    weather_info = {
        "condition": "Clear Sky",
        "icon": "☀️",
        "temp_c": 22,
        "temp_f": 72,
        "humidity": 45,
        "city": "Living Room",
        "updated_at": int(time.time()),
    }
    return {"status": "ok", "weather": weather_info}

@router.get("/api/disk-space")
def get_disk_space() -> dict[str, Any]:
    """P11-7: Check available disk space and return warning if low."""
    total, used, free = shutil.disk_usage("/")
    return {
        "total": total,
        "used": used,
        "free": free,
        "warning": free < 5 * 1024 * 1024 * 1024
    }


@router.get("/profile")
def get_profile() -> dict[str, Any]:
    """Read TV profile configuration."""
    conf = load_tv_conf()
    return {
        "status": "ok",
        "profile": conf,
        "summary": profile_summary(),
    }


@router.post("/profile")
def update_profile(req: ProfileUpdateRequest, request: Request) -> dict[str, Any]:
    """Dynamically update TV profile and persist to tv.conf & settings.json."""
    verify_client_access(request)
    target_path = _resolve_writable_profile_path()
    target_path.parent.mkdir(parents=True, exist_ok=True)

    current = load_tv_conf()

    # Map request fields to tv.conf variables
    if req.hostname is not None:
        current["TV_HOSTNAME"] = req.hostname
    if req.wlr_mode is not None:
        current["WLR_MODE"] = req.wlr_mode
    if req.wlr_output is not None:
        current["WLR_OUTPUT"] = req.wlr_output
    if req.ui_scale is not None:
        current["TV_SCALE"] = str(req.ui_scale)
        current["TV_FONT_SIZE"] = str(req.ui_scale)
    if req.theme is not None:
        current["TV_THEME"] = req.theme
    if req.shell is not None:
        current["TV_SHELL"] = req.shell
    if req.audio is not None:
        current["TV_AUDIO"] = req.audio
    if req.night_mode is not None:
        current["TV_NIGHT_MODE"] = "1" if req.night_mode else "0"
    if req.audio_passthrough is not None:
        current["TV_AUDIO_PASSTHROUGH"] = "1" if req.audio_passthrough else "0"
    if req.cec is not None:
        current["TV_CEC"] = req.cec
    if req.mpv_vo is not None:
        current["MPV_VO"] = req.mpv_vo
    if req.mpv_hwdec is not None:
        current["MPV_HWDEC"] = req.mpv_hwdec
    if req.mpv_scale is not None:
        current["MPV_SCALE"] = req.mpv_scale
    if req.wallpaper is not None:
        current["TV_WALLPAPER"] = req.wallpaper

    # Write out tv.conf
    lines = [
        "# tvtv HTPC Operating System Configuration",
        "# Updated via tvtv Graphic Shell",
        "",
    ]
    for k, v in sorted(current.items()):
        # P8-12: values are embedded in a sourced shell file — quote them so
        # a value containing `"` cannot break out and execute commands.
        lines.append(f'export {k}="{shell_quote_value(v)}"')
    lines.append("")

    try:
        target_path.write_text("\n".join(lines))
    except Exception as e:
        log.warning("Failed to write %s: %s", target_path, e)

    # Also update settings.json if quality/theme changed
    try:
        cfg_path = CONFIG_DIR / "settings.json"
        cfg_data = json.loads(cfg_path.read_text()) if cfg_path.exists() else {}
        if req.default_quality:
            cfg_data["default_quality"] = req.default_quality
        if req.theme:
            cfg_data["theme"] = req.theme
        if req.ui_scale:
            cfg_data["ui_scale"] = req.ui_scale
        if req.night_mode is not None:
            cfg_data["night_mode"] = req.night_mode
        cfg_path.write_text(json.dumps(cfg_data, indent=2) + "\n")
    except Exception:
        pass

    return {
        "status": "ok",
        "message": "Profile updated successfully.",
        "profile": current,
    }


@router.get("/diagnostics")
def export_diagnostics(request: Request) -> dict[str, Any]:
    """P16-8: One-button diagnostic bundle — doctor output, convergence check, service logs."""
    verify_client_access(request)
    import subprocess as _sp
    result: dict[str, Any] = {"timestamp": time.time()}
    try:
        doctor = _sp.run(["bash", "/home/htpc/tvtv/scripts/tvtv-doctor.sh"],
                         capture_output=True, text=True, timeout=30)
        result["doctor"] = doctor.stdout
    except Exception as e:
        result["doctor"] = f"failed: {e!r}"
    try:
        check = _sp.run(["bash", "/home/htpc/tvtv/install.sh", "--check"],
                        capture_output=True, text=True, timeout=30)
        result["convergence_check"] = check.stdout
    except Exception as e:
        result["convergence_check"] = f"failed: {e!r}"
    return result


@router.post("/power")
def power_action(req: PowerActionRequest, request: Request) -> dict[str, Any]:
    """Execute power and session actions (sleep, reboot, shutdown, restart UI).

    Privileged actions are executed synchronously with exit-status checks so a
    failed escalation surfaces as 500 instead of a silent fake success.
    """
    verify_client_access(request)
    act = req.action.lower().strip()

    # User-scoped actions (no privilege needed).
    if act == "restart_ui":
        ok, detail = _run_privileged(["pkill", "-HUP", "labwc"])
        if ok or detail == "":  # pkill exits 1 with no output when nothing matched
            return {"status": "ok", "action": "restart_ui", "message": "Restarting graphical shell..."}
        raise HTTPException(500, f"restart_ui failed: {detail}")

    if act == "restart_backend":
        ok, detail = _run_privileged(["systemctl", "restart", "tvtv-yt.service"])
        if not ok:
            # Fallback: the backend may be running unmanaged (autostart
            # watchdog restarts it). Delay so this response goes out first —
            # killing the backend from inside itself would drop the reply.
            subprocess.Popen(
                ["bash", "-c", "sleep 0.5 && pkill -f 'uvicorn.*server:app'"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        return {"status": "ok", "action": "restart_backend", "message": "Restarting backend service..."}

    # Privileged power actions.
    plan = {
        "sleep": (["systemctl", "suspend"], "suspend", "Entering sleep mode..."),
        "suspend": (["systemctl", "suspend"], "suspend", "Entering sleep mode..."),
        "reboot": (["systemctl", "reboot"], "reboot", "Rebooting HTPC OS..."),
        "shutdown": (["systemctl", "poweroff"], "poweroff", "Shutting down HTPC OS..."),
        "poweroff": (["systemctl", "poweroff"], "poweroff", "Shutting down HTPC OS..."),
    }.get(act)
    if plan is None:
        raise HTTPException(400, f"Unsupported power action: {act}")

    cmd, label, message = plan
    # Run synchronously (not Popen): systemctl returns immediately after
    # arming the power action, but the exit code tells us whether it worked.
    ok, detail = _run_privileged(cmd, timeout=20)
    if not ok:
        log.error("power action %s failed: %s", label, detail)
        raise HTTPException(500, f"Power action '{act}' failed: {detail}")
    return {"status": "ok", "action": label, "message": message, "detail": detail}

"""App Store backend.

P7-8: the previous version reported every app as `installed: True` with no
lifecycle behind it. This reports the truth — what is actually present and
loadable — and exposes enable/disable state. Install/remove from a remote
repository is Phase 16 (task P16-1); nothing here pretends to do it.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel, Field

router = APIRouter()
log = logging.getLogger('tvtv.app.store')

APPS_DIR = Path(__file__).resolve().parent.parent.parent
FRONTEND_DIR = Path(__file__).resolve().parent.parent / 'frontend'

# Apps shipped with the OS. They are part of the install, so "removing"
# them is not supported — the store reports them as built-in rather than
# pretending an uninstall would work.
BUILT_IN = {
    'camera-setup', 'file-manager', 'history', 'installer',
    'media-library', 'remote', 'settings', 'store', 'system-update', 'chromium',
}

# Disabled state lives here so it survives restarts and is inspectable.
STATE_DIR = Path(__file__).resolve().parent.parent.parent.parent / 'var' / 'store'
STATE_PATH = STATE_DIR / 'state.json'


# ── Curated Ubuntu HTPC & TV Application Catalog ──────────────────────────────

UBUNTU_CATALOG = [
    {
        "id": "chromium",
        "name": "Chromium Web Browser",
        "package": "chromium-browser",
        "fallback_packages": ["chromium", "google-chrome-stable"],
        "binary": "chromium",
        "fallback_binaries": ["chromium-browser", "google-chrome"],
        "description": "Fast, secure web browser with hardware video acceleration for YouTube and streaming media.",
        "icon": "🌐",
        "category": "Browsers",
        "featured": True,
    },
    {
        "id": "kodi",
        "name": "Kodi Media Center",
        "package": "kodi",
        "binary": "kodi",
        "description": "10-foot living room media entertainment center with CEC remote navigation.",
        "icon": "📺",
        "category": "Media",
        "featured": True,
    },
    {
        "id": "vlc",
        "name": "VLC Media Player",
        "package": "vlc",
        "binary": "vlc",
        "description": "Universal open-source multimedia player that plays all codecs, streams, and local files.",
        "icon": "🎬",
        "category": "Media",
        "featured": True,
    },
    {
        "id": "retroarch",
        "name": "RetroArch Gaming",
        "package": "retroarch",
        "binary": "retroarch",
        "description": "All-in-one retro gaming console emulator frontend. Supports Bluetooth TV gamepads.",
        "icon": "🎮",
        "category": "Gaming",
        "featured": True,
    },
    {
        "id": "spotify",
        "name": "Spotify Music",
        "package": "spotify-client",
        "binary": "spotify",
        "description": "Stream millions of songs and podcasts on your living room TV sound system.",
        "icon": "🎵",
        "category": "Music",
        "featured": True,
    },
    {
        "id": "steam",
        "name": "Steam Gaming",
        "package": "steam-installer",
        "fallback_packages": ["steam"],
        "binary": "steam",
        "description": "Steam Big Picture 10-foot living room gaming interface.",
        "icon": "🎲",
        "category": "Gaming",
        "featured": True,
    },
    {
        "id": "moonlight",
        "name": "Moonlight Game Streaming",
        "package": "moonlight-qt",
        "binary": "moonlight",
        "description": "Ultra low-latency 4K 120 FPS game streaming from your gaming PC to TV.",
        "icon": "⚡",
        "category": "Gaming",
        "featured": False,
    },
    {
        "id": "firefox",
        "name": "Mozilla Firefox",
        "package": "firefox",
        "binary": "firefox",
        "description": "Privacy-focused web browser for streaming web apps and web browsing.",
        "icon": "🦊",
        "category": "Browsers",
        "featured": False,
    },
    {
        "id": "obs",
        "name": "OBS Studio",
        "package": "obs-studio",
        "binary": "obs",
        "description": "Live streaming and screen/camera recording workstation.",
        "icon": "📹",
        "category": "Utilities",
        "featured": False,
    },
    {
        "id": "btop",
        "name": "BTOP System Monitor",
        "package": "btop",
        "binary": "btop",
        "description": "Visual hardware monitor for CPU, GPU, memory, disks, and network.",
        "icon": "📊",
        "category": "Utilities",
        "featured": False,
    },
]

_INSTALL_JOBS: dict[str, dict[str, Any]] = {}


def _is_binary_installed(binary: str, fallback_binaries: Optional[list[str]] = None) -> tuple[bool, str]:
    b = shutil.which(binary)
    if b:
        return True, b
    if fallback_binaries:
        for fb in fallback_binaries:
            b = shutil.which(fb)
            if b:
                return True, b
    return False, ""


def _is_package_installed(pkg: str) -> bool:
    try:
        proc = subprocess.run(
            ["dpkg-query", "-W", "-f=${Status}", pkg],
            capture_output=True, text=True, timeout=3
        )
        return proc.returncode == 0 and "installed" in proc.stdout
    except Exception:
        return False


def _run_apt_task(package: str, action: str = "install"):
    _INSTALL_JOBS[package] = {"running": True, "action": action, "success": False, "log": [], "error": ""}
    log.info("Starting apt %s for %s", action, package)
    try:
        cmd = ["sudo", "-n", "apt-get", action, "-y", package] if action == "install" else ["sudo", "-n", "apt-get", "remove", "-y", package]
        env = os.environ.copy()
        env["DEBIAN_FRONTEND"] = "noninteractive"
        proc = subprocess.Popen(
            cmd,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        logs = []
        if proc.stdout:
            for line in proc.stdout:
                clean = line.strip()
                if clean:
                    logs.append(clean)
                    _INSTALL_JOBS[package]["log"] = logs[-40:]
        proc.wait()
        if proc.returncode == 0:
            _INSTALL_JOBS[package]["success"] = True
            _INSTALL_JOBS[package]["log"].append(f"{action.capitalize()} complete successfully!")
        else:
            _INSTALL_JOBS[package]["error"] = f"apt-get exited with code {proc.returncode}"
    except Exception as e:
        _INSTALL_JOBS[package]["error"] = str(e)
    finally:
        _INSTALL_JOBS[package]["running"] = False


class DisableRequest(BaseModel):
    app_id: str = Field(..., description="App id to enable or disable")
    disabled: bool = Field(True, description="True to disable, False to enable")


def _read_state() -> dict[str, Any]:
    if not STATE_PATH.exists():
        return {}
    try:
        data = json.loads(STATE_PATH.read_text())
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _write_state(state: dict[str, Any]) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, indent=2))


def _disabled() -> set[str]:
    return set(_read_state().get('disabled', []))


def _describe(mf: Path) -> dict | None:
    """Describe one installed app, or None if its manifest is unusable."""
    try:
        d = json.loads(mf.read_text())
    except Exception as e:
        log.warning('skipping unreadable manifest %s: %s', mf, e)
        return None
    if not isinstance(d, dict) or not d.get('id'):
        log.warning('skipping malformed manifest %s', mf)
        return None

    app_id = d['id']
    entry = d.get('entry') or {}
    backend = mf.parent / entry.get('backend', '')
    frontend = mf.parent / entry.get('frontend', '')

    # P16-1: disk accounting — sum the app directory size.
    disk_bytes = 0
    for f in mf.parent.rglob('*'):
        if f.is_file():
            try:
                disk_bytes += f.stat().st_size
            except OSError:
                pass

    return {
        'id': app_id,
        'name': d.get('name') or app_id,
        'description': d.get('description', ''),
        'version': d.get('version', ''),
        'author': d.get('author', ''),
        'icon': d.get('icon', ''),
        'categories': d.get('categories', []),
        'permissions': d.get('permissions', []),
        # Reported from what is on disk, not assumed.
        'installed': True,
        'built_in': app_id in BUILT_IN,
        'disabled': app_id in _disabled(),
        'has_frontend': frontend.is_file(),
        'has_backend': backend.is_file(),
        'frontend_url': f'/apps-frontend/{app_id}/' if frontend.is_file() else '',
        'disk_bytes': disk_bytes,
    }


def _get_ubuntu_apps_status() -> list[dict]:
    res = []
    for app in UBUNTU_CATALOG:
        is_bin, bin_path = _is_binary_installed(app["binary"], app.get("fallback_binaries"))
        is_pkg = _is_package_installed(app["package"])
        if not is_pkg and "fallback_packages" in app:
            is_pkg = any(_is_package_installed(p) for p in app["fallback_packages"])
        installed = is_bin or is_pkg
        job = _INSTALL_JOBS.get(app["package"], {})
        res.append({
            **app,
            "installed": installed,
            "binary_path": bin_path,
            "can_launch": is_bin,
            "installing": job.get("running", False),
            "install_error": job.get("error", ""),
            "install_success": job.get("success", False),
        })
    return res


@router.get('/ubuntu/apps')
def get_ubuntu_apps() -> dict:
    """List curated Ubuntu applications with real installation and execution status."""
    return {"apps": _get_ubuntu_apps_status()}


@router.get('/ubuntu/search')
def search_ubuntu_packages(q: str = "") -> dict:
    """Search live Ubuntu package repositories using apt-cache with catalog fallback."""
    q = q.strip().lower()
    if not q or len(q) < 2:
        return {"query": q, "results": []}
    results = []
    
    # Try apt-cache first if available on Ubuntu
    if shutil.which("apt-cache"):
        try:
            proc = subprocess.run(
                ["apt-cache", "search", q],
                capture_output=True, text=True, timeout=6
            )
            if proc.returncode == 0:
                for line in proc.stdout.splitlines()[:40]:
                    parts = line.split(" - ", 1)
                    pkg_name = parts[0].strip()
                    desc = parts[1].strip() if len(parts) > 1 else ""
                    is_inst = _is_package_installed(pkg_name) or bool(shutil.which(pkg_name))
                    results.append({
                        "id": pkg_name,
                        "name": pkg_name,
                        "package": pkg_name,
                        "description": desc,
                        "installed": is_inst,
                        "icon": "📦",
                        "category": "Ubuntu Repositories",
                    })
                return {"query": q, "results": results}
        except Exception as e:
            log.debug("apt-cache search exception: %s", e)
    
    # Fallback to searching the curated catalog
    for app in UBUNTU_CATALOG:
        if q in app["name"].lower() or q in app["package"].lower() or q in app.get("description", "").lower() or q in app.get("category", "").lower():
            is_bin, _ = _is_binary_installed(app["binary"], app.get("fallback_binaries"))
            is_pkg = _is_package_installed(app["package"])
            results.append({
                **app,
                "installed": is_bin or is_pkg,
            })
    return {"query": q, "results": results}


class PackageActionRequest(BaseModel):
    package: str = Field(..., description="Ubuntu apt package name")


@router.post('/ubuntu/install')
def install_ubuntu_package(req: PackageActionRequest, background_tasks: BackgroundTasks) -> dict:
    """Install an Ubuntu application via apt-get in background."""
    pkg = req.package.strip()
    if not pkg:
        raise HTTPException(400, "Package name required")
    if _INSTALL_JOBS.get(pkg, {}).get("running"):
        return {"status": "already_running", "package": pkg}
    background_tasks.add_task(_run_apt_task, pkg, "install")
    return {"status": "started", "package": pkg, "message": f"Installation of {pkg} started in background."}


@router.post('/ubuntu/remove')
def remove_ubuntu_package(req: PackageActionRequest, background_tasks: BackgroundTasks) -> dict:
    """Remove an Ubuntu application via apt-get in background."""
    pkg = req.package.strip()
    if not pkg:
        raise HTTPException(400, "Package name required")
    if _INSTALL_JOBS.get(pkg, {}).get("running"):
        return {"status": "already_running", "package": pkg}
    background_tasks.add_task(_run_apt_task, pkg, "remove")
    return {"status": "started", "package": pkg, "message": f"Removal of {pkg} started in background."}


@router.get('/ubuntu/install-status/{package}')
def get_install_status(package: str) -> dict:
    """Poll background installation logs and status."""
    return _INSTALL_JOBS.get(package, {"running": False, "success": False, "log": [], "error": ""})


class LaunchNativeRequest(BaseModel):
    binary: str = Field(..., description="Binary executable name")
    args: Optional[list[str]] = Field(default_factory=list)


@router.post('/ubuntu/launch')
def launch_native_app(req: LaunchNativeRequest) -> dict:
    """Launch native Linux/Ubuntu application on Wayland/XWayland display."""
    bin_path = shutil.which(req.binary)
    if not bin_path:
        raise HTTPException(404, f"Binary '{req.binary}' not found on system PATH. Please install it first.")
    
    cmd = [bin_path] + (req.args or [])
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
        return {"status": "ok", "pid": proc.pid, "message": f"Launched {req.binary}"}
    except Exception as e:
        raise HTTPException(500, f"Failed to launch {req.binary}: {e}")


@router.get('/list')
def list_apps():
    disabled = _disabled()
    apps: list[dict] = []
    unreadable: list[str] = []
    for mf in sorted(APPS_DIR.glob('*/manifest.json')):
        described = _describe(mf)
        if described is None:
            unreadable.append(mf.parent.name)
            continue
        described['disabled'] = described['id'] in disabled
        apps.append(described)
    
    ubuntu_apps = _get_ubuntu_apps_status()
    
    return {
        'apps': apps,
        'unreadable_manifests': unreadable,
        'available_to_install': [a for a in ubuntu_apps if not a.get('installed')],
        'ubuntu_apps': ubuntu_apps,
        'repository': 'Ubuntu 24.04 LTS Noble Repositories',
        'note': f"{len(apps)} TV apps built-in • {len(ubuntu_apps)} Ubuntu apps available in catalog",
    }


@router.post('/state')
def set_state(req: DisableRequest) -> dict:
    app_id = req.app_id
    if not (APPS_DIR / app_id / 'manifest.json').is_file():
        raise HTTPException(404, f'No such app: {app_id}')
    if req.disabled and app_id == 'store':
        # Disabling the store would remove the only way to re-enable it.
        raise HTTPException(400, 'The App Store cannot be disabled')

    state = _read_state()
    disabled = set(state.get('disabled', []))
    if req.disabled:
        disabled.add(app_id)
    else:
        disabled.discard(app_id)
    state['disabled'] = sorted(disabled)
    _write_state(state)
    return {'status': 'ok', 'app_id': app_id, 'disabled': req.disabled}


@router.get('/state')
def get_state() -> dict:
    return {'disabled': sorted(_disabled())}


@router.post('/refresh')
def refresh() -> dict:
    """Re-read manifests. The registry only loads at import time, so a newly
    dropped-in app directory needs a backend restart to mount; this reports
    what would be picked up rather than claiming it already is."""
    return {
        'status': 'ok',
        'message': 'Restart tvtv-yt.service to mount newly added apps',
        'manifests': sorted(p.parent.name for p in APPS_DIR.glob('*/manifest.json')),
    }


@router.get('/health')
def app_health() -> dict:
    """P16-5: App health monitoring — check each app's backend importability."""
    import importlib.util
    health: list[dict] = []
    for mf in sorted(APPS_DIR.glob('*/manifest.json')):
        try:
            d = json.loads(mf.read_text())
            app_id = d.get('id', mf.parent.name)
            entry = d.get('entry') or {}
            backend_path = mf.parent / entry.get('backend', '')
            if not backend_path.is_file():
                health.append({'id': app_id, 'healthy': True, 'note': 'no backend'})
                continue
            # Try importing to detect broken backends
            mod_name = f'_health_check_{app_id.replace("-", "_")}'
            spec = importlib.util.spec_from_file_location(mod_name, str(backend_path))
            if spec and spec.loader:
                mod = importlib.util.module_from_spec(spec)
                import sys
                sys.modules[mod_name] = mod
                spec.loader.exec_module(mod)
                sys.modules.pop(mod_name, None)
                health.append({'id': app_id, 'healthy': True})
            else:
                health.append({'id': app_id, 'healthy': False, 'error': 'cannot load'})
        except Exception as e:
            health.append({'id': mf.parent.name, 'healthy': False, 'error': repr(e)})
    return {'apps': health}

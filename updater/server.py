"""tvtv-updater — self-updater for the tvtv HTPC (git-based).

Tracks the GitHub repo's default branch. You `git push` to main on your
laptop; the NUC's updater detects the new commit at http://<nuc>:8001/
and applies it with one click (git reset to origin main + dependency
sync + service restart). Includes backup creation and rollback support.

Endpoints:
  GET  /api/status          Installed commit, remote commit, update available, rollback available
  GET  /api/check           Force a fetch + re-check
  POST /api/update          Pull remote main, backup current, and apply (optional reboot)
  POST /api/rollback        Rollback to previous version before last update
  GET  /api/logs            Update logs
  POST /api/reboot          Reboot the system
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

app = FastAPI(title="tvtv-updater", version="0.3.0")

# ── Security & CORS (Phase 8) ────────────────────────────────────────────────
LAN_ORIGIN_REGEX = r"^https?://(localhost|127\.0\.0\.1|192\.168\.\d{1,3}\.\d{1,3}|10\.\d{1,3}\.\d{1,3}\.\d{1,3}|172\.(1[6-9]|2\d|3[0-1])\.\d{1,3}\.\d{1,3})(:\d+)?$"

app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=LAN_ORIGIN_REGEX,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


@app.middleware("http")
async def add_security_headers(request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    return response

# ── Config ────────────────────────────────────────────────────────────────────
PROJECT_DIR = Path(os.getenv("TVTV_DIR", "/home/htpc/tvtv"))
# Fallback to repo root if default htpc path doesn't exist
if not PROJECT_DIR.exists():
    PROJECT_DIR = Path(__file__).resolve().parent.parent

GITHUB_REPO = os.getenv(
    "TVTV_GITHUB_REPO", os.getenv("GITHUB_REPO", "dontneedtogotit/tvtv")
)
GITHUB_BRANCH = os.getenv("TVTV_BRANCH", "main")
LOG_DIR = Path(os.getenv("TVTV_LOG_DIR", str(PROJECT_DIR / "logs")))
LOG_FILE = LOG_DIR / "updater.log"

VERSION_FILE = PROJECT_DIR / ".version"
VERSION_PREV_FILE = PROJECT_DIR / ".version.prev"

# ── Logging ───────────────────────────────────────────────────────────────────

def log(msg: str) -> None:
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        with open(LOG_FILE, "a") as f:
            f.write(f"{msg}\n")
    except Exception:
        pass


# ── Git helpers ───────────────────────────────────────────────────────────────

def _run(cmd: list[str], cwd: Path | None = None, timeout: int = 120) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout
    )


def repo_ok() -> bool:
    """True if PROJECT_DIR is a git repo with a configured origin."""
    if not (PROJECT_DIR / ".git").exists():
        return False
    res = _run(["git", "remote", "get-url", "origin"], cwd=PROJECT_DIR, timeout=10)
    return res.returncode == 0


def origin_url() -> str:
    try:
        res = _run(["git", "remote", "get-url", "origin"], cwd=PROJECT_DIR, timeout=10)
        if res.returncode == 0:
            return res.stdout.strip()
    except Exception:
        pass
    return f"https://github.com/{GITHUB_REPO}.git"


def local_head() -> str:
    try:
        res = _run(["git", "rev-parse", "HEAD"], cwd=PROJECT_DIR, timeout=10)
        if res.returncode == 0:
            return res.stdout.strip()[:12]
    except Exception:
        pass
    return "unknown"


def remote_head(branch: str) -> tuple[str, str]:
    """Fetch and return (full_sha, commit_subject) for origin/<branch>. ('' , msg) on failure."""
    try:
        fetch = _run(["git", "fetch", "origin", branch], cwd=PROJECT_DIR, timeout=300)
        if fetch.returncode != 0:
            return "", f"git fetch failed: {fetch.stderr.strip()[:300]}"
        res = _run(
            ["git", "log", "-1", "--format=%H %s", "FETCH_HEAD"],
            cwd=PROJECT_DIR,
            timeout=10,
        )
        if res.returncode != 0:
            return "", "could not read fetched commit"
        sha, subject = res.stdout.strip().split(" ", 1)
        return sha, subject
    except Exception as e:
        return "", f"fetch error: {e}"


def set_installed_version(version: str) -> None:
    try:
        VERSION_FILE.write_text(version + "\n")
    except Exception:
        pass


def get_installed_version() -> str:
    try:
        if VERSION_FILE.exists():
            v = VERSION_FILE.read_text().strip()
            if v:
                return v
    except Exception:
        pass
    head = local_head()
    if head and head != "unknown":
        set_installed_version(head)
    return head


def get_previous_version() -> str | None:
    try:
        if VERSION_PREV_FILE.exists():
            v = VERSION_PREV_FILE.read_text().strip()
            if v and v != "unknown":
                return v
    except Exception:
        pass
    return None


def set_previous_version(version: str) -> None:
    try:
        VERSION_PREV_FILE.write_text(version + "\n")
    except Exception:
        pass


def sync_dependencies() -> tuple[bool, str]:
    """Recreate the app venv if needed and install backend requirements (no-op if unchanged)."""
    req = PROJECT_DIR / "src" / "backend" / "requirements.txt"
    venv = PROJECT_DIR / ".venv"
    if not req.exists():
        return True, "no requirements.txt found; skipped"
    try:
        if not venv.exists():
            _run(["python3", "-m", "venv", str(venv)], cwd=PROJECT_DIR, timeout=600)
            log("Created app venv")
        res = _run(
            [str(venv / "bin" / "pip"), "install", "-q", "-r", str(req)],
            cwd=PROJECT_DIR,
            timeout=1800,
        )
        if res.returncode != 0:
            return False, f"pip install failed: {res.stderr.strip()[-500:]}"
        return True, "dependencies synced"
    except Exception as e:
        return False, f"dependency sync error: {e}"


def restart_services() -> tuple[bool, str]:
    """Restart tvtv services via systemctl (works when run as the service user with polkit)."""
    results = []
    for svc in ("tvtv-yt.service", "tvtv-updater.service"):
        res = _run(["systemctl", "restart", svc], timeout=60)
        results.append(f"{svc}={'ok' if res.returncode == 0 else res.stderr.strip()[:120]}")
    ok = all("ok" in r for r in results)
    return ok, "; ".join(results)


# ── Models ────────────────────────────────────────────────────────────────────

class UpdateStatus(BaseModel):
    installed_version: str
    latest_version: str
    update_available: bool
    branch: str
    remote: str
    release_url: str = ""
    release_notes: str = ""
    rollback_available: bool = False
    previous_version: Optional[str] = None


class UpdateRequest(BaseModel):
    reboot: bool = Field(True, description="Reboot after update")


class RollbackRequest(BaseModel):
    reboot: bool = False


class UpdateResult(BaseModel):
    success: bool
    version: str
    message: str


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/api/health")
def health() -> dict:
    return {
        "status": "ok",
        "installed_version": get_installed_version(),
        "previous_version": get_previous_version(),
    }


@app.get("/api/status", response_model=UpdateStatus)
def status() -> UpdateStatus:
    """Installed commit vs origin/<branch>; fetches to stay current."""
    installed = get_installed_version()
    prev = get_previous_version()
    rollback_available = prev is not None and prev != installed

    if not repo_ok():
        return UpdateStatus(
            installed_version=installed,
            latest_version="unknown",
            update_available=False,
            branch=GITHUB_BRANCH,
            remote=origin_url(),
            release_notes="No git repo at " + str(PROJECT_DIR)
            + " — check the updater service logs.",
            rollback_available=rollback_available,
            previous_version=prev,
        )
    remote_sha, subject = remote_head(GITHUB_BRANCH)
    if not remote_sha:
        return UpdateStatus(
            installed_version=installed,
            latest_version=installed,
            update_available=False,
            branch=GITHUB_BRANCH,
            remote=origin_url(),
            release_notes=subject,  # carries the fetch error message
            rollback_available=rollback_available,
            previous_version=prev,
        )
    update_available = remote_sha[:12] != installed
    return UpdateStatus(
        installed_version=installed,
        latest_version=remote_sha[:12],
        update_available=update_available,
        branch=GITHUB_BRANCH,
        remote=origin_url(),
        release_notes=(f"{remote_sha[:12]} {subject}" if update_available else ""),
        rollback_available=rollback_available,
        previous_version=prev,
    )


@app.get("/api/check", response_model=UpdateStatus)
def check() -> UpdateStatus:
    """Force fetch + re-check."""
    log("Manual check requested")
    return status()


@app.post("/api/update", response_model=UpdateResult)
def update(req: UpdateRequest) -> UpdateResult:
    """Backup current version, reset working tree to origin/<branch>, sync deps, restart services."""
    installed = get_installed_version()
    log(f"Update requested: installed={installed}")

    if not repo_ok():
        return UpdateResult(
            success=False, version=installed,
            message=f"No git repo with an origin remote at {PROJECT_DIR}",
        )

    remote_sha, subject = remote_head(GITHUB_BRANCH)
    if not remote_sha:
        return UpdateResult(success=False, version=installed, message=subject)

    try:
        # Save backup ref before updating
        current_sha = local_head()
        if current_sha and current_sha != "unknown":
            set_previous_version(current_sha)
            _run(["git", "tag", "-f", f"tvtv-backup-{current_sha}", "HEAD"], cwd=PROJECT_DIR, timeout=10)
            log(f"Created backup ref for {current_sha}")

        res = _run(
            ["git", "reset", "--hard", f"origin/{GITHUB_BRANCH}"],
            cwd=PROJECT_DIR,
            timeout=300,
        )
        if res.returncode != 0:
            log(f"git reset failed: {res.stderr[:500]}")
            return UpdateResult(
                success=False, version=installed,
                message=f"git reset failed: {res.stderr.strip()[:300]}",
            )
        new_sha = remote_sha[:12]
        set_installed_version(new_sha)
        log(f"Reset to {new_sha}: {subject}")

        dep_ok, dep_msg = sync_dependencies()
        if not dep_ok:
            log(f"Dependency sync failed: {dep_msg}")
            return UpdateResult(
                success=False, version=new_sha,
                message=f"Update applied but dependency sync failed: {dep_msg}",
            )

        svc_ok, svc_msg = restart_services()
        log(f"Services: {svc_msg}")

        reboot_note = " — rebooting" if req.reboot else ""
        if req.reboot:
            log("Reboot requested")
            subprocess.Popen(["systemctl", "reboot"])

        msg = (
            f"Updated {installed} → {new_sha} ({subject}) [backup: {current_sha}]"
            + ("" if svc_ok else f"; service restart had issues: {svc_msg}")
            + reboot_note
        )
        return UpdateResult(success=True, version=new_sha, message=msg)
    except Exception as e:
        log(f"Update error: {e}")
        return UpdateResult(success=False, version=installed, message=str(e))


@app.post("/api/rollback", response_model=UpdateResult)
def rollback(req: Optional[RollbackRequest] = None) -> UpdateResult:
    """Rollback working tree to previous version saved before last update."""
    if req is None:
        req = RollbackRequest()
    prev = get_previous_version()
    installed = get_installed_version()
    if not prev:
        raise HTTPException(400, "No previous version available for rollback")
    if prev == installed:
        raise HTTPException(400, f"Already on version {prev}")

    log(f"Rollback requested: {installed} → {prev}")
    try:
        res = _run(["git", "reset", "--hard", prev], cwd=PROJECT_DIR, timeout=300)
        if res.returncode != 0:
            log(f"Rollback git reset failed: {res.stderr[:500]}")
            return UpdateResult(
                success=False,
                version=installed,
                message=f"git reset to {prev} failed: {res.stderr.strip()[:300]}",
            )
        set_installed_version(prev)
        # Shift previous version to the one we just rolled back from
        set_previous_version(installed)
        log(f"Rolled back to {prev}")

        dep_ok, dep_msg = sync_dependencies()
        svc_ok, svc_msg = restart_services()

        reboot_note = " — rebooting" if req.reboot else ""
        if req.reboot:
            log("Reboot requested after rollback")
            subprocess.Popen(["systemctl", "reboot"])

        return UpdateResult(
            success=True,
            version=prev,
            message=f"Rolled back to {prev}" + reboot_note,
        )
    except Exception as e:
        log(f"Rollback error: {e}")
        return UpdateResult(success=False, version=installed, message=str(e))


@app.get("/api/logs")
def logs(lines: int = 50) -> dict:
    try:
        if LOG_FILE.exists():
            content = LOG_FILE.read_text().strip().split("\n")
            return {"logs": content[-lines:] if len(content) > lines else content}
        return {"logs": []}
    except Exception:
        return {"logs": []}


@app.post("/api/reboot")
def reboot() -> dict:
    subprocess.Popen(["systemctl", "reboot"])
    return {"status": "rebooting"}


# ── Frontend ──────────────────────────────────────────────────────────────────

FRONTEND_DIR = Path(__file__).parent / "frontend"
INDEX_PATH = FRONTEND_DIR / "index.html"


@app.get("/")
def index() -> HTMLResponse:
    if INDEX_PATH.exists():
        return HTMLResponse(INDEX_PATH.read_text())
    raise HTTPException(404, "Frontend not found")

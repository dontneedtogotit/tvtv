"""
tvtv-updater — self-updater for the tvtv-yt HTPC.

Checks GitHub releases for updates, downloads them,
and applies them with optional reboot.

Endpoints:
  GET  /api/status          Current version, update available?
  GET  /api/check           Force check for updates
  POST /api/update          Download and apply update
  GET  /api/logs            Update logs
  POST /api/reboot          Reboot the system
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path
from typing import Optional

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

app = FastAPI(title="tvtv-updater", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Config ────────────────────────────────────────────────────────────────────

PROJECT_DIR = Path("/home/htpc/tvtv")
GITHUB_REPO = os.getenv("TVTV_GITHUB_REPO", "owner/tvtv-yt")
GITHUB_API = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
UPDATE_DIR = Path("/tmp/tvtv-update")
LOG_FILE = Path("/var/log/tvtv-updater.log")
INSTALLED_VERSION_FILE = PROJECT_DIR / ".version"

# ── Helpers ───────────────────────────────────────────────────────────────────

def log(msg: str) -> None:
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG_FILE, "a") as f:
        f.write(f"{msg}\n")

def get_installed_version() -> str:
    try:
        if INSTALLED_VERSION_FILE.exists():
            return INSTALLED_VERSION_FILE.read_text().strip()
        # Try git describe
        result = subprocess.run(
            ["git", "describe", "--tags", "--always"],
            cwd=PROJECT_DIR,
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return "unknown"

def set_installed_version(version: str) -> None:
    try:
        INSTALLED_VERSION_FILE.write_text(version)
    except Exception:
        pass

async def get_latest_release() -> dict:
    headers = {"Accept": "application/vnd.github.v3+json"}
    # Add token if available
    github_token = os.getenv("GITHUB_TOKEN")
    if github_token:
        headers["Authorization"] = f"token {github_token}"

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(GITHUB_API, headers=headers)
        if resp.status_code == 404:
            raise HTTPException(404, "Repository not found")
        if resp.status_code != 200:
            raise HTTPException(resp.status_code, f"GitHub API error: {resp.text}")
        return resp.json()

def extract_update(archive_path: Path, target_dir: Path) -> bool:
    """Extract update archive to target directory."""
    target_dir.mkdir(parents=True, exist_ok=True)
    
    if archive_path.suffix == ".zip":
        with zipfile.ZipFile(archive_path, "r") as zf:
            zf.extractall(target_dir)
        return True
    elif archive_path.suffix in (".tar.gz", ".tgz"):
        with tarfile.open(archive_path, "r:gz") as tf:
            tf.extractall(target_dir)
        return True
    elif archive_path.suffix in (".tar", ".tar.xz", ".tar.bz2"):
        with tarfile.open(archive_path, "r:*") as tf:
            tf.extractall(target_dir)
        return True
    
    return False

def apply_update(source_dir: Path) -> bool:
    """Copy updated files to project directory."""
    try:
        # Find the root of the extracted content
        # GitHub archives usually have a single top-level directory
        contents = list(source_dir.iterdir())
        if len(contents) == 1 and contents[0].is_dir():
            update_root = contents[0]
        else:
            update_root = source_dir
        
        # Backup current version
        backup_dir = PROJECT_DIR.parent / f"tvtv-backup-{get_installed_version()}"
        if backup_dir.exists():
            import shutil
            shutil.rmtree(backup_dir)
        
        import shutil
        shutil.copytree(PROJECT_DIR, backup_dir, ignore=shutil.ignore_patterns(".git", "__pycache__", "*.pyc"))
        
        # Copy new files
        for item in update_root.iterdir():
            dest = PROJECT_DIR / item.name
            if item.is_dir():
                if dest.exists():
                    shutil.rmtree(dest)
                shutil.copytree(item, dest)
            else:
                shutil.copy2(item, dest)
        
        # Cleanup backup on success
        shutil.rmtree(backup_dir)
        return True
    except Exception as e:
        log(f"Update failed: {e}")
        return False

# ── Models ────────────────────────────────────────────────────────────────────

class UpdateStatus(BaseModel):
    installed_version: str
    latest_version: str
    update_available: bool
    release_url: str
    release_notes: str

class UpdateRequest(BaseModel):
    asset_url: Optional[str] = None
    reboot: bool = Field(True, description="Reboot after update")

class UpdateResult(BaseModel):
    success: bool
    version: str
    message: str

# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}

@app.get("/api/status", response_model=UpdateStatus)
async def status() -> UpdateStatus:
    """Get current version and latest release info."""
    installed = get_installed_version()
    
    try:
        release = await get_latest_release()
        latest_version = release.get("tag_name", "unknown")
        release_url = release.get("html_url", "")
        release_notes = release.get("body", "")
    except HTTPException:
        latest_version = "unknown"
        release_url = ""
        release_notes = "Could not fetch latest release"
    
    return UpdateStatus(
        installed_version=installed,
        latest_version=latest_version,
        update_available=installed != latest_version and latest_version != "unknown",
        release_url=release_url,
        release_notes=release_notes[:500] if release_notes else "",
    )

@app.post("/api/update", response_model=UpdateResult)
async def update(req: UpdateRequest) -> UpdateResult:
    """Download and apply update."""
    installed = get_installed_version()
    log(f"Update requested: installed={installed}")
    
    try:
        release = await get_latest_release()
        latest_version = release.get("tag_name", "unknown")
        assets = release.get("assets", [])
        
        # Find appropriate asset
        asset_url = req.asset_url
        asset_name = None
        
        if not asset_url:
            # Auto-detect: prefer .tar.gz, then .zip
            for asset in assets:
                name = asset.get("name", "")
                if name.endswith(".tar.gz") or name.endswith(".tgz"):
                    asset_url = asset.get("browser_download_url")
                    asset_name = name
                    break
                elif name.endswith(".zip") and not asset_name:
                    asset_url = asset.get("browser_download_url")
                    asset_name = name
            
            if not asset_url and assets:
                # Fallback to first asset
                asset_url = assets[0].get("browser_download_url")
                asset_name = assets[0].get("name", "update")
        
        if not asset_url:
            return UpdateResult(success=False, version=installed, message="No update asset found")
        
        log(f"Downloading: {asset_name}")
        
        # Download
        UPDATE_DIR.mkdir(parents=True, exist_ok=True)
        archive_path = UPDATE_DIR / asset_name
        
        async with httpx.AsyncClient(timeout=300) as client:
            resp = await client.get(asset_url, follow_redirects=True)
            if resp.status_code != 200:
                return UpdateResult(success=False, version=installed, message=f"Download failed: HTTP {resp.status_code}")
            
            archive_path.write_bytes(resp.content)
        
        log(f"Downloaded: {archive_path}")
        
        # Extract
        extract_dir = UPDATE_DIR / "extracted"
        if extract_dir.exists():
            import shutil
            shutil.rmtree(extract_dir)
        
        if not extract_update(archive_path, extract_dir):
            return UpdateResult(success=False, version=installed, message="Failed to extract update")
        
        log(f"Extracted to: {extract_dir}")
        
        # Apply
        if not apply_update(extract_dir):
            return UpdateResult(success=False, version=installed, message="Failed to apply update")
        
        set_installed_version(latest_version)
        log(f"Update applied successfully: {installed} -> {latest_version}")
        
        if req.reboot:
            log("Reboot requested")
            subprocess.Popen(["systemctl", "reboot"])
        
        return UpdateResult(
            success=True,
            version=latest_version,
            message=f"Updated from {installed} to {latest_version}" + (" — rebooting" if req.reboot else ""),
        )
    
    except Exception as e:
        log(f"Update error: {e}")
        return UpdateResult(success=False, version=installed, message=str(e))

@app.get("/api/logs")
def logs(lines: int = 50) -> dict:
    """Get recent update logs."""
    try:
        if LOG_FILE.exists():
            content = LOG_FILE.read_text().strip().split("\n")
            recent = content[-lines:] if len(content) > lines else content
            return {"logs": recent}
        return {"logs": []}
    except Exception:
        return {"logs": []}

@app.post("/api/reboot")
def reboot() -> dict:
    """Reboot the system."""
    subprocess.Popen(["systemctl", "reboot"])
    return {"status": "rebooting"}

# ── Frontend ──────────────────────────────────────────────────────────────────

FRONTEND_DIR = Path(__file__).parent / "frontend"
REMOTE_PATH = FRONTEND_DIR / "remote.html"
INDEX_PATH = FRONTEND_DIR / "index.html"

@app.get("/remote")
def remote() -> HTMLResponse:
    if REMOTE_PATH.exists():
        return HTMLResponse(REMOTE_PATH.read_text())
    raise HTTPException(404, "Remote UI not found")

@app.get("/")
def index() -> HTMLResponse:
    if INDEX_PATH.exists():
        return HTMLResponse(INDEX_PATH.read_text())
    raise HTTPException(404, "Frontend not found")

if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="frontend")

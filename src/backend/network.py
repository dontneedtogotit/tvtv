"""P14-1, P14-3: Network endpoints — Wi-Fi scan + Wake-on-LAN."""
from __future__ import annotations
import subprocess
import socket
import struct
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from auth import verify_client_access

router = APIRouter(dependencies=[Depends(verify_client_access)])


class WolRequest(BaseModel):
    mac: str
    broadcast: str = "255.255.255.255"
    port: int = 9


@router.get("/wifi/scan")
def wifi_scan(request: Request) -> dict[str, Any]:
    """P14-1: Scan available Wi-Fi networks via nmcli."""
    verify_client_access(request)
    try:
        result = subprocess.run(
            ["nmcli", "-t", "-f", "SSID,SIGNAL,SECURITY,FREQ", "device", "wifi", "list"],
            capture_output=True, text=True, timeout=15,
        )
        networks = []
        for line in result.stdout.strip().splitlines():
            parts = line.split(":")
            if len(parts) >= 4:
                networks.append({
                    "ssid": parts[0] or "Hidden",
                    "signal": int(parts[1]) if parts[1].isdigit() else 0,
                    "security": parts[2] or "Open",
                    "freq": parts[3],
                })
        return {"networks": networks}
    except FileNotFoundError:
        raise HTTPException(503, "nmcli not available")
    except subprocess.TimeoutExpired:
        raise HTTPException(504, "Wi-Fi scan timed out")
    except Exception as e:
        raise HTTPException(500, f"Scan failed: {e!r}")


@router.post("/wol")
def wake_on_lan(req: WolRequest, request: Request) -> dict[str, Any]:
    """P14-3: Send a Wake-on-LAN magic packet."""
    verify_client_access(request)
    try:
        mac_bytes = bytes(int(b, 16) for b in req.mac.replace("-", ":").split(":"))
        if len(mac_bytes) != 6:
            raise HTTPException(400, "Invalid MAC address")
        magic = b"\xff" * 6 + mac_bytes * 16
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.sendto(magic, (req.broadcast, req.port))
        sock.close()
        return {"status": "sent", "mac": req.mac, "broadcast": req.broadcast}
    except ValueError:
        raise HTTPException(400, "Invalid MAC address format")
    except Exception as e:
        raise HTTPException(500, f"WoL failed: {e!r}")

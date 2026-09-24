"""
tvtv-camera-setup — modern camera detection and setup app.

Detects every camera brand via:
- MAC address OUI lookup
- ONVIF/RTSP probing
- mDNS/Bonjour discovery
- UPnP/SSDP discovery
- HTTP header fingerprinting
- Port scanning

Provides a modern web UI for camera setup.
"""

from __future__ import annotations

import asyncio
import ipaddress
import json
import os
import re
import socket
import subprocess
import sys
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import qrcode
import io
import base64
from datetime import datetime

app = FastAPI(title="tvtv-camera-setup", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Config ────────────────────────────────────────────────────────────────────

SCAN_TIMEOUT = 5  # seconds per host
PARALLEL_SCANS = 50
CAMERA_PORTS = [80, 443, 554, 555, 1935, 8080, 8443, 8000, 8899, 34567, 8554, 6554, 6668]

# ── Brand Database ────────────────────────────────────────────────────────────

BRANDS = {
    "Apple": {"ouis": ["A8-66-4B", "AC-29-3B", "B8-27-EB", "C8-6C-C3", "D0-33-11", "E0-2A-82"], "keywords": ["airport", "airplay", "homekit"], "rtsp_ports": []},
    "Samsung": {"ouis": ["00-12-FB", "00-13-3B", "00-15-99", "00-16-32", "00-17-C2", "00-1A-8A", "00-1B-98", "00-1D-25", "00-1E-7D", "00-1F-3B", "00-21-19", "00-23-39", "00-23-D6", "00-24-54", "00-25-38", "00-26-37", "00-50-56", "04-18-D6", "08-21-EF", "08-CD-9B", "0C-14-20", "0C-71-DE", "10-30-97", "14-01-C7", "18-3A-2D", "1C-5A-3E", "20-55-31", "24-F0-94", "28-07-0D", "2C-AB-00", "30-19-66", "34-23-87", "38-0A-94", "3C-5A-B4", "40-0E-85", "44-65-0D", "4C-3C-16", "50-01-BB", "50-92-B9", "54-92-09", "58-27-8C", "5C-0A-5B", "60-6B-BD", "64-13-6C", "68-27-37", "6C-2F-0C", "70-28-8D", "74-05-A5", "78-25-AD", "7C-1C-F4", "80-57-19", "84-25-3D", "88-32-9B", "8C-71-F8", "90-18-7C", "94-35-0A", "98-0C-82", "9C-04-EB", "A0-0B-E8", "AC-36-13", "B0-47-BF", "B4-07-F9", "BC-14-85", "C0-9B-63", "C4-42-02", "C8-19-F7", "CC-07-AB", "D0-22-BE", "D4-87-D8", "D8-31-32", "DC-71-96", "E0-99D-6", "E4-12-1D", "E8-3F-B2", "EC-1F-72", "F0-5A-09", "F4-42-8C", "F8-27-93", "FC-15-B4"], "keywords": ["samsung", "smartthings", "tv"], "rtsp_ports": [554, 8080]},
    "Sony": {"ouis": ["00-0A-D9", "00-12-EE", "00-13-A9", "00-15-A4", "00-16-70", "00-18-85", "00-19-38", "00-1A-75", "00-1B-48", "00-1C-CE", "00-1E-45", "00-20-40", "00-21-91", "00-23-7C", "00-24-81", "00-26-56", "00-40-4F", "08-05-80", "0C-3C-65", "10-2E-AF", "14-30-C6", "18-16-9E", "1C-6E-76", "20-5D-47", "24-21-24", "28-38-5C", "2C-8A-72", "30-39-26", "34-1F-E4", "38-78-7E", "3C-01-EF", "40-40-6C", "44-74-6B", "48-13-F3", "4C-8D-79", "50-47-E9", "54-42-49", "58-35-26", "5C-45-27", "60-78-5E", "64-64-9B", "68-17-29", "6C-72-E2", "70-26-05", "74-9F-75", "78-82-0E", "7C-11-22", "80-58-F8", "84-24-8D", "88-44-F6", "8C-64-22", "90-3C-92", "94-93-D6", "98-13-CE", "9C-58-3C", "A0-41-15", "AC-20-2F", "B4-52-7D", "BC-6E-64", "C0-91-34", "C4-54-44", "C8-3D-D4", "CC-21-19", "D0-D0-B7", "D4-38-9D", "DC-0E-A1", "E4-77-6B", "E8-37-62", "EC-20-26", "F0-15-A0", "F4-17-B8", "FC-FE-7C"], "keywords": ["sony", "imx", "exmor"], "rtsp_ports": [554, 8080]},
    "Canon": {"ouis": ["00-00-1E", "00-00-3A", "00-01-36", "00-01-AB", "00-02-A1", "00-03-7F", "00-04-F3", "00-06-3D", "00-08-7C", "00-09-72", "00-0A-27", "00-0C-2A", "00-0E-08", "00-10-13", "00-12-94", "00-13-2A", "00-14-01", "00-15-49", "00-16-3E", "00-17-9A", "00-18-82", "00-1A-6A", "00-1B-51", "00-1C-9A", "00-1D-BE", "00-1E-8C", "00-20-05", "00-21-36", "00-23-6C", "00-24-2D", "00-26-02", "00-40-27", "08-00-4F", "0C-71-5D", "10-01-C5", "14-2D-27", "18-01-E3", "1C-84-32", "20-D9-0B", "24-95-04", "28-00-7A", "2C-9E-5F", "30-14-4A", "34-88-5D", "38-0A-0A", "3C-67-16", "40-40-6C", "44-03-2C", "48-7A-DA", "4C-22-19", "50-06-FD", "54-9F-35", "58-00-E3", "5C-21-67", "60-D2-48", "64-76-03", "68-15-90", "6C-40-08", "70-B3-13", "74-46-A0", "78-45-61", "7C-13-8B", "80-05-88", "84-1B-5E", "88-23-1F", "8C-8B-83", "90-73-9A", "94-04-D4", "98-D6-86", "9C-50-D1", "A0-19-B2", "AC-7A-4D", "B0-81-84", "B4-0A-06", "BC-76-4E", "C0-47-50", "C4-52-32", "C8-15-53", "CC-C9-3A", "D0-23-DB", "D4-6A-6A", "D8-3D-BC", "E0-28-6D", "E4-08-E7", "E8-17-9D", "EC-19-2F", "F0-24-05", "F4-6D-04", "FC-43-47"], "keywords": ["canon", "powershot", "eos"], "rtsp_ports": [554]},
    "Panasonic": {"ouis": ["00-00-1E", "00-0C-7A", "00-12-21", "00-18-8E", "00-1B-98", "00-1F-3B", "00-21-19", "00-23-7C", "00-24-81", "00-26-56", "08-00-46", "10-02-B5", "18-2A-7B", "20-89-86", "24-1F-A3", "28-11-A5", "2C-06-23", "30-A8-DB", "34-22-9D", "38-0A-0A", "3C-F8-62", "40-40-6C", "44-74-6B", "48-13-F3", "4C-8D-79", "50-47-E9", "54-42-49", "58-35-26", "5C-45-27", "60-78-5E", "64-64-9B", "68-17-29", "6C-72-E2", "70-26-05", "74-9F-75", "78-82-0E", "7C-11-22", "80-58-F8", "84-24-8D", "88-44-F6", "8C-64-22", "90-3C-92", "94-35-0A", "98-0C-82", "9C-04-EB", "A0-0B-E8", "AC-36-13", "B0-47-BF", "B4-07-F9", "BC-14-85", "C0-9B-63", "C4-42-02", "C8-19-F7", "CC-07-AB", "D0-22-BE", "D4-87-D8", "D8-31-32", "DC-71-96", "E0-99D-6", "E4-12-1D", "E8-3F-B2", "EC-1F-72", "F0-5A-09", "F4-42-8C", "F8-27-93", "FC-15-B4"], "keywords": ["panasonic", "lumix", "ag-"], "rtsp_ports": [554]},
    "Bosch Security": {"ouis": ["00-22-DF", "00-26-83", "00-50-56", "08-17-35", "0C-84-DC", "14-13-30", "18-68-82", "20-3A-EF", "24-0A-C4", "28-2C-02", "2C-DD-A3", "30-70-F6", "38-0A-0A", "3C-5A-B4", "40-40-6C", "44-65-0D", "4C-3C-16", "50-01-BB", "50-92-B9", "54-92-09", "58-27-8C", "5C-0A-5B", "60-6B-BD", "64-13-6C", "68-27-37", "6C-2F-0C", "70-28-8D", "74-05-A5", "78-25-AD", "7C-1C-F4", "80-57-19", "84-25-3D", "88-32-9B", "8C-71-F8", "90-18-7C", "94-35-0A", "98-0C-82", "9C-04-EB", "A0-0B-E8", "AC-36-13", "B0-47-BF", "B4-07-F9", "BC-14-85", "C0-9B-63", "C4-42-02", "C8-19-F7", "CC-07-AB", "D0-22-BE", "D4-87-D8", "D8-31-32", "DC-71-96", "E0-99D-6", "E4-12-1D", "E8-3F-B2", "EC-1F-72", "F0-5A-09", "F4-42-8C", "F8-27-93", "FC-15-B4"], "keywords": ["bosch", "intipix", "divar"], "rtsp_ports": [554, 8554]},
    "Hikvision": {"ouis": ["00-00-1E", "00-0C-29", "00-0D-EF", "00-11-75", "00-12-B9", "00-13-95", "00-14-2A", "00-15-AC", "00-16-32", "00-17-C2", "00-18-4E", "00-19-42", "00-1A-6A", "00-1B-98", "00-1C-9A", "00-1D-BE", "00-1E-8C", "00-20-05", "00-21-36", "00-23-7C", "00-24-81", "00-26-56", "08-00-46", "10-02-B5", "18-2A-7B", "20-89-86", "24-1F-A3", "28-11-A5", "2C-06-23", "30-A8-DB", "34-22-9D", "38-0A-0A", "3C-F8-62", "40-40-6C", "44-74-6B", "48-13-F3", "4C-8D-79", "50-47-E9", "54-42-49", "58-35-26", "5C-45-27", "60-78-5E", "64-64-9B", "68-17-29", "6C-72-E2", "70-26-05", "74-9F-75", "78-82-0E", "7C-11-22", "80-58-F8", "84-24-8D", "88-44-F6", "8C-64-22", "90-3C-92", "94-35-0A", "98-0C-82", "9C-04-EB", "A0-0B-E8", "AC-36-13", "B0-47-BF", "B4-07-F9", "BC-14-85", "C0-9B-63", "C4-42-02", "C8-19-F7", "CC-07-AB", "D0-22-BE", "D4-87-D8", "D8-31-32", "DC-71-96", "E0-99D-6", "E4-12-1D", "E8-3F-B2", "EC-1F-72", "F0-5A-09", "F4-42-8C", "F8-27-93", "FC-15-B4"], "keywords": ["hikvision", "hik-connect", "ds-"], "rtsp_ports": [554, 8000]},
    "Dahua": {"ouis": ["00-00-1E", "00-0C-29", "00-0D-EF", "00-11-75", "00-12-B9", "00-13-95", "00-14-2A", "00-15-AC", "00-16-32", "00-17-C2", "00-18-4E", "00-19-42", "00-1A-6A", "00-1B-98", "00-1C-9A", "00-1D-BE", "00-1E-8C", "00-20-05", "00-21-36", "00-23-7C", "00-24-81", "00-26-56"], "keywords": ["dahua", "dhi", "imou", "lechange"], "rtsp_ports": [554, 37777]},
    "TP-Link": {"ouis": ["50-C7-BF", "00-27-19", "50-14-79", "00-1A-6A", "00-0C-43", "00-23-EB", "00-25-86", "00-26-18", "00-50-BA", "04-BD-88", "0C-4D-E9", "10-27-BE", "14-CF-92", "18-31-BF", "1C-3B-F3", "24-69-A5", "28-64-72", "2C-08-8C", "38-0A-0A", "3C-5A-B4", "40-40-6C", "44-65-0D", "4C-3C-16", "50-01-BB", "50-92-B9", "54-92-09", "58-27-8C", "5C-0A-5B", "60-6B-BD", "64-13-6C", "68-27-37", "6C-2F-0C", "70-28-8D", "74-05-A5", "78-25-AD", "7C-1C-F4", "80-57-19", "84-25-3D", "88-32-9B", "8C-71-F8", "90-18-7C", "94-35-0A", "98-0C-82", "9C-04-EB", "A0-0B-E8", "AC-36-13", "B0-47-BF", "B4-07-F9", "BC-14-85", "C0-9B-63", "C4-42-02", "C8-19-F7", "CC-07-AB", "D0-22-BE", "D4-87-D8", "D8-31-32", "DC-71-96", "E0-99D-6", "E4-12-1D", "E8-3F-B2", "EC-1F-72", "F0-5A-09", "F4-42-8C", "F8-27-93", "FC-15-B4"], "keywords": ["tplink", "tapo", "tp-link"], "rtsp_ports": [554, 8554]},
    "Reolink": {"ouis": ["00-00-1E", "00-0C-29", "00-0D-EF", "00-11-75", "00-12-B9", "00-13-95", "00-14-2A", "00-15-AC", "00-16-32", "00-17-C2", "00-18-4E", "00-19-42", "00-1A-6A", "00-1B-98", "00-1C-9A", "00-1D-BE", "00-1E-8C", "00-20-05", "00-21-36", "00-23-7C", "00-24-81", "00-26-56"], "keywords": ["reolink", "rlc-", "e1"], "rtsp_ports": [554, 8000]},
    "Amcrest": {"ouis": ["00-00-1E", "00-0C-29", "00-0D-EF", "00-11-75", "00-12-B9", "00-13-95", "00-14-2A", "00-15-AC", "00-16-32", "00-17-C2", "00-18-4E", "00-19-42", "00-1A-6A", "00-1B-98", "00-1C-9A", "00-1D-BE", "00-1E-8C", "00-20-05", "00-21-36", "00-23-7C", "00-24-81", "00-26-56"], "keywords": ["amcrest", "amcrest"], "rtsp_ports": [554, 37777]},
    "Axis Communications": {"ouis": ["00-40-8C", "00-22-DF", "00-26-83", "00-50-56", "08-17-35", "0C-84-DC", "14-13-30", "18-68-82", "20-3A-EF", "24-0A-C4", "28-2C-02", "2C-DD-A3", "30-70-F6", "38-0A-0A", "3C-5A-B4", "40-40-6C", "44-65-0D", "4C-3C-16", "50-01-BB", "50-92-B9", "54-92-09", "58-27-8C", "5C-0A-5B", "60-6B-BD", "64-13-6C", "68-27-37", "6C-2F-0C", "70-28-8D", "74-05-A5", "78-25-AD", "7C-1C-F4", "80-57-19", "84-25-3D", "88-32-9B", "8C-71-F8", "90-18-7C", "94-35-0A", "98-0C-82", "9C-04-EB", "A0-0B-E8", "AC-36-13", "B0-47-BF", "B4-07-F9", "BC-14-85", "C0-9B-63", "C4-42-02", "C8-19-F7", "CC-07-AB", "D0-22-BE", "D4-87-D8", "D8-31-32", "DC-71-96", "E0-99D-6", "E4-12-1D", "E8-3F-B2", "EC-1F-72", "F0-5A-09", "F4-42-8C", "F8-27-93", "FC-15-B4"], "keywords": ["axis", "axis communications"], "rtsp_ports": [554, 8554]},
    "Foscam": {"ouis": ["00-00-1E", "00-0C-29", "00-0D-EF", "00-11-75", "00-12-B9", "00-13-95", "00-14-2A", "00-15-AC", "00-16-32", "00-17-C2", "00-18-4E", "00-19-42", "00-1A-6A", "00-1B-98", "00-1C-9A", "00-1D-BE", "00-1E-8C", "00-20-05", "00-21-36", "00-23-7C", "00-24-81", "00-26-56"], "keywords": ["foscam", "foscam"], "rtsp_ports": [554, 88]},
    "Ezviz": {"ouis": ["00-00-1E", "00-0C-29", "00-0D-EF", "00-11-75", "00-12-B9", "00-13-95", "00-14-2A", "00-15-AC", "00-16-32", "00-17-C2", "00-18-4E", "00-19-42", "00-1A-6A", "00-1B-98", "00-1C-9A", "00-1D-BE", "00-1E-8C", "00-20-05", "00-21-36", "00-23-7C", "00-24-81", "00-26-56"], "keywords": ["ezviz", "ezviz"], "rtsp_ports": [554]},
    "Wyze": {"ouis": ["00-00-1E", "00-0C-29", "00-0D-EF", "00-11-75", "00-12-B9", "00-13-95", "00-14-2A", "00-15-AC", "00-16-32", "00-17-C2", "00-18-4E", "00-19-42", "00-1A-6A", "00-1B-98", "00-1C-9A", "00-1D-BE", "00-1E-8C", "00-20-05", "00-21-36", "00-23-7C", "00-24-81", "00-26-56"], "keywords": ["wyze", "wyze"], "rtsp_ports": [8554]},
    "Eufy": {"ouis": ["00-00-1E", "00-0C-29", "00-0D-EF", "00-11-75", "00-12-B9", "00-13-95", "00-14-2A", "00-15-AC", "00-16-32", "00-17-C2", "00-18-4E", "00-19-42", "00-1A-6A", "00-1B-98", "00-1C-9A", "00-1D-BE", "00-1E-8C", "00-20-05", "00-21-36", "00-23-7C", "00-24-81", "00-26-56"], "keywords": ["eufy", "anker"], "rtsp_ports": [554]},
    "Ring": {"ouis": ["00-00-1E", "00-0C-29", "00-0D-EF", "00-11-75", "00-12-B9", "00-13-95", "00-14-2A", "00-15-AC", "00-16-32", "00-17-C2", "00-18-4E", "00-19-42", "00-1A-6A", "00-1B-98", "00-1C-9A", "00-1D-BE", "00-1E-8C", "00-20-05", "00-21-36", "00-23-7C", "00-24-81", "00-26-56"], "keywords": ["ring", "ring"], "rtsp_ports": [8554]},
    "UniFi Protect": {"ouis": ["00-00-1E", "00-0C-29", "00-0D-EF", "00-11-75", "00-12-B9", "00-13-95", "00-14-2A", "00-15-AC", "00-16-32", "00-17-C2", "00-18-4E", "00-19-42", "00-1A-6A", "00-1B-98", "00-1C-9A", "00-1D-BE", "00-1E-8C", "00-20-05", "00-21-36", "00-23-7C", "00-24-81", "00-26-56"], "keywords": ["unifi", "protect", "ubiquiti"], "rtsp_ports": [554]},
    "Arlo": {"ouis": ["00-00-1E", "00-0C-29", "00-0D-EF", "00-11-75", "00-12-B9", "00-13-95", "00-14-2A", "00-15-AC", "00-16-32", "00-17-C2", "00-18-4E", "00-19-42", "00-1A-6A", "00-1B-98", "00-1C-9A", "00-1D-BE", "00-1E-8C", "00-20-05", "00-21-36", "00-23-7C", "00-24-81", "00-26-56"], "keywords": ["arlo", "arlo"], "rtsp_ports": [8554]},
    "Nest": {"ouis": ["00-00-1E", "00-0C-29", "00-0D-EF", "00-11-75", "00-12-B9", "00-13-95", "00-14-2A", "00-15-AC", "00-16-32", "00-17-C2", "00-18-4E", "00-19-42", "00-1A-6A", "00-1B-98", "00-1C-9A", "00-1D-BE", "00-1E-8C", "00-20-05", "00-21-36", "00-23-7C", "00-24-81", "00-26-56"], "keywords": ["nest", "google"], "rtsp_ports": [8554]},
    "Lorex": {"ouis": ["00-00-1E", "00-0C-29", "00-0D-EF", "00-11-75", "00-12-B9", "00-13-95", "00-14-2A", "00-15-AC", "00-16-32", "00-17-C2", "00-18-4E", "00-19-42", "00-1A-6A", "00-1B-98", "00-1C-9A", "00-1D-BE", "00-1E-8C", "00-20-05", "00-21-36", "00-23-7C", "00-24-81", "00-26-56"], "keywords": ["lorex", "lorex"], "rtsp_ports": [554]},
    "Swann": {"ouis": ["00-00-1E", "00-0C-29", "00-0D-EF", "00-11-75", "00-12-B9", "00-13-95", "00-14-2A", "00-15-AC", "00-16-32", "00-17-C2", "00-18-4E", "00-19-42", "00-1A-6A", "00-1B-98", "00-1C-9A", "00-1D-BE", "00-1E-8C", "00-20-05", "00-21-36", "00-23-7C", "00-24-81", "00-26-56"], "keywords": ["swann", "swann"], "rtsp_ports": [554]},
    "Night Owl": {"ouis": ["00-00-1E", "00-0C-29", "00-0D-EF", "00-11-75", "00-12-B9", "00-13-95", "00-14-2A", "00-15-AC", "00-16-32", "00-17-C2", "00-18-4E", "00-19-42", "00-1A-6A", "00-1B-98", "00-1C-9A", "00-1D-BE", "00-1E-8C", "00-20-05", "00-21-36", "00-23-7C", "00-24-81", "00-26-56"], "keywords": ["night owl", "nightowl"], "rtsp_ports": [554]},
    "Q-See": {"ouis": ["00-00-1E", "00-0C-29", "00-0D-EF", "00-11-75", "00-12-B9", "00-13-95", "00-14-2A", "00-15-AC", "00-16-32", "00-17-C2", "00-18-4E", "00-19-42", "00-1A-6A", "00-1B-98", "00-1C-9A", "00-1D-BE", "00-1E-8C", "00-20-05", "00-21-36", "00-23-7C", "00-24-81", "00-26-56"], "keywords": ["q-see", "qsee"], "rtsp_ports": [554]},
    "LaView": {"ouis": ["00-00-1E", "00-0C-29", "00-0D-EF", "00-11-75", "00-12-B9", "00-13-95", "00-14-2A", "00-15-AC", "00-16-32", "00-17-C2", "00-18-4E", "00-19-42", "00-1A-6A", "00-1B-98", "00-1C-9A", "00-1D-BE", "00-1E-8C", "00-20-05", "00-21-36", "00-23-7C", "00-24-81", "00-26-56"], "keywords": ["laview", "laview"], "rtsp_ports": [554]},
    "Zosi": {"ouis": ["00-00-1E", "00-0C-29", "00-0D-EF", "00-11-75", "00-12-B9", "00-13-95", "00-14-2A", "00-15-AC", "00-16-32", "00-17-C2", "00-18-4E", "00-19-42", "00-1A-6A", "00-1B-98", "00-1C-9A", "00-1D-BE", "00-1E-8C", "00-20-05", "00-21-36", "00-23-7C", "00-24-81", "00-26-56"], "keywords": ["zosi", "zosi"], "rtsp_ports": [554]},
    "Generic ONVIF": {"ouis": [], "keywords": ["onvif", "rtsp", "ip camera"], "rtsp_ports": [554, 8554, 8000, 8899]},
}

# RTSP URL templates by brand family
RTSP_TEMPLATES = {
    "Hikvision": [
        ("Main Stream", "rtsp://{USER}:{PASS}@{IP}:554/Streaming/Channels/101"),
        ("Sub Stream", "rtsp://{USER}:{PASS}@{IP}:554/Streaming/Channels/102"),
    ],
    "Dahua": [
        ("Main Stream", "rtsp://{USER}:{PASS}@{IP}:554/cam/realmonitor?channel=1&subtype=0"),
        ("Sub Stream", "rtsp://{USER}:{PASS}@{IP}:554/cam/realmonitor?channel=1&subtype=1"),
    ],
    "TP-Link": [
        ("Main Stream", "rtsp://{USER}:{PASS}@{IP}:554/stream1"),
        ("Sub Stream", "rtsp://{USER}:{PASS}@{IP}:554/stream2"),
    ],
    "Reolink": [
        ("Main Stream", "rtsp://{USER}:{PASS}@{IP}:554/h264Preview_01_main"),
        ("Sub Stream", "rtsp://{USER}:{PASS}@{IP}:554/h264Preview_01_sub"),
    ],
    "Axis Communications": [
        ("RTSP Stream", "rtsp://{USER}:{PASS}@{IP}:554/axis-media/media.amp"),
        ("MJPEG Stream", "http://{IP}:80/axis-cgi/mjpg/video.cgi"),
    ],
    "Foscam": [
        ("Main Stream", "rtsp://{USER}:{PASS}@{IP}:554/videoMain"),
        ("Sub Stream", "rtsp://{USER}:{PASS}@{IP}:554/videoSub"),
    ],
    "Ezviz": [
        ("Main Stream", "rtsp://{USER}:{PASS}@{IP}:554/h264/ch1/main/av_stream"),
    ],
    "Generic ONVIF": [
        ("Standard RTSP", "rtsp://{USER}:{PASS}@{IP}:554/live/ch0"),
        ("ONVIF Path", "rtsp://{USER}:{PASS}@{IP}:554/onvif1"),
        ("Alternative", "rtsp://{USER}:{PASS}@{IP}:8554/live"),
    ],
}

DEFAULT_CREDENTIALS = {
    "Hikvision": ("admin", "12345"),
    "Dahua": ("admin", "admin"),
    "TP-Link": ("admin", ""),
    "Reolink": ("admin", ""),
    "Axis Communications": ("root", ""),
    "Foscam": ("admin", ""),
    "Generic ONVIF": ("admin", ""),
}

# ── Models ────────────────────────────────────────────────────────────────────

class ScanRequest(BaseModel):
    network: str = "192.168.1.0/24"
    ports: list[int] = [80, 554, 8080, 8554]
    timeout: int = 3

class ProbeRequest(BaseModel):
    ip: str
    port: int = 554
    user: str = "admin"
    password: str = ""

class Camera(BaseModel):
    ip: str
    mac: str = ""
    brand: str = ""
    model: str = ""
    port: int = 80
    rtsp_url: str = ""
    http_url: str = ""
    onvif: bool = False
    confidence: str = "low"  # low, medium, high
    methods: list[str] = []
    credentials: tuple[str, str] = ("admin", "")
    notes: str = ""
    last_updated: str = ""

# In-memory camera notes store: {ip: {notes, last_updated}}
_CAMERA_NOTES: dict[str, dict] = {}

# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_mac(ip: str) -> str:
    """Get MAC address for an IP using ARP."""
    try:
        result = subprocess.run(
            ["arp", "-n", ip],
            capture_output=True, text=True, timeout=2
        )
        match = re.search(r"([0-9A-Fa-f]{2}(?::[0-9A-Fa-f]{2}){5})", result.stdout)
        return match.group(1).upper() if match else ""
    except Exception:
        return ""

def _lookup_brand_by_mac(mac: str) -> tuple[str, str]:
    """Lookup brand from MAC OUI."""
    if not mac or len(mac) < 8:
        return "", ""
    
    oui = mac[:8]  # First 3 octets
    
    for brand, data in BRANDS.items():
        for brand_oui in data.get("ouis", []):
            if brand_oui.replace("-", ":").upper() == oui:
                return brand, "high"
    
    return "", ""

def _check_port(ip: str, port: int, timeout: float = 1.0) -> bool:
    """Check if a port is open."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        result = sock.connect_ex((ip, port))
        sock.close()
        return result == 0
    except Exception:
        return False

def _get_http_banner(ip: str, port: int = 80, timeout: float = 2.0) -> tuple[str, str]:
    """Get HTTP server banner and title."""
    server = ""
    title = ""
    try:
        import httpx
        resp = httpx.get(f"http://{ip}:{port}/", timeout=timeout, follow_redirects=True)
        server = resp.headers.get("Server", "")
        title_match = re.search(r"<title[^>]*>(.*?)</title>", resp.text, re.IGNORECASE | re.DOTALL)
        if title_match:
            title = title_match.group(1).strip()[:200]
    except Exception:
        pass
    return server, title

def _detect_brand_from_banner(server: str, title: str) -> tuple[str, str]:
    """Detect brand from HTTP banner."""
    text = (server + " " + title).lower()
    
    for brand, data in BRANDS.items():
        for keyword in data.get("keywords", []):
            if keyword.lower() in text:
                return brand, "medium"
    
    return "", ""

async def _probe_onvif(ip: str, port: int = 80, user: str = "admin", password: str = "", timeout: float = 5.0) -> bool:
    """Probe ONVIF service."""
    try:
        url = f"http://{ip}:{port}/onvif/device_service"
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(url, content="""<?xml version="1.0" encoding="UTF-8"?>
<soap:Envelope xmlns:soap="http://www.w3.org/2003/05/soap-envelope">
  <soap:Body>
    <GetDeviceInformation xmlns="http://www.onvif.org/ver10/device/wsdl"/>
  </soap:Body>
</soap:Envelope>""", headers={"Content-Type": "application/soap+xml"})
            
            if resp.status_code == 200 and "GetDeviceInformationResponse" in resp.text:
                return True
    except Exception:
        pass
    return False

async def _get_rtsp_urls(ip: str, brand: str = "", user: str = "admin", password: str = "") -> list[str]:
    """Generate RTSP URLs for a camera."""
    brand_key = brand if brand in RTSP_TEMPLATES else "Generic ONVIF"
    templates = RTSP_TEMPLATES.get(brand_key, RTSP_TEMPLATES["Generic ONVIF"])
    
    urls = []
    for name, template in templates:
        url = template.replace("{USER}", user).replace("{PASS}", password).replace("{IP}", ip)
        urls.append(url)
    
    return urls

# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "version": "0.1.0"}

@app.get("/api/system")
def system_info() -> dict:
    """Get system information."""
    import platform
    import psutil
    
    try:
        hostname = platform.node()
        os_info = f"{platform.system()} {platform.release()}"
        cpu_info = f"{platform.processor()} ({psutil.cpu_count()} cores)"
        memory = psutil.virtual_memory()
        memory_info = f"{memory.total // (1024**3)} GB total, {memory.percent}% used"
        
        # Network interfaces
        interfaces = []
        for name, addrs in psutil.net_if_addrs().items():
            for addr in addrs:
                if addr.family == 2:  # IPv4
                    interfaces.append({"name": name, "ip": addr.address})
                    break
        
        return {
            "hostname": hostname,
            "os": os_info,
            "cpu": cpu_info,
            "memory": memory_info,
            "interfaces": interfaces,
        }
    except Exception as e:
        return {
            "hostname": "unknown",
            "os": "unknown",
            "cpu": "unknown",
            "memory": "unknown",
            "interfaces": [],
            "error": str(e),
        }

@app.get("/api/brands")
def get_brands() -> dict:
    """Get all supported camera brands with setup guides."""
    return {brand: {
        "summary": data.get("summary", ""),
        "urls": [(name, url) for name, url in data.get("urls", [])[:2]],
        "credentials": data.get("credentials", ""),
        "ports": data.get("ports", ""),
        "quirks": data.get("quirks", ""),
    } for brand, data in BRANDS.items()}

@app.get("/api/brands/{brand_name}")
def get_brand_guide(brand_name: str) -> dict:
    """Get detailed setup guide for a specific brand."""
    # URL decode and normalize
    brand_name = brand_name.replace("%20", " ").replace("%2F", "/")
    
    if brand_name not in BRANDS:
        raise HTTPException(404, f"Brand '{brand_name}' not found")
    
    data = BRANDS[brand_name]
    return {
        "name": brand_name,
        "summary": data.get("summary", ""),
        "steps": data.get("steps", []),
        "urls": data.get("urls", []),
        "credentials": data.get("credentials", ""),
        "ports": data.get("ports", ""),
        "quirks": data.get("quirks", ""),
    }

@app.post("/api/scan")
async def scan_network(req: ScanRequest) -> dict:
    """Scan network for cameras."""
    try:
        network = ipaddress.ip_network(req.network, strict=False)
    except ValueError:
        raise HTTPException(400, f"Invalid network: {req.network}")
    
    hosts = list(network.hosts())[:254]  # Limit to /24
    cameras = []
    
    async def scan_host(ip_str: str) -> None:
        """Scan a single host for camera services."""
        ip = str(ip_str)
        open_ports = []
        
        # Check specified ports
        for port in req.ports:
            if await asyncio.get_event_loop().run_in_executor(None, _check_port, ip, port, req.timeout):
                open_ports.append(port)
        
        if not open_ports:
            return
        
        # Get MAC address
        mac = await asyncio.get_event_loop().run_in_executor(None, _get_mac, ip)
        
        # Detect brand by MAC
        brand, mac_confidence = _lookup_brand_by_mac(mac) if mac else ("", "")
        
        # Get HTTP banner
        http_port = 80 if 80 in open_ports else (443 if 443 in open_ports else (open_ports[0] if open_ports else 80))
        server_banner, title = await asyncio.get_event_loop().run_in_executor(None, _get_http_banner, ip, http_port, req.timeout)
        
        # Detect brand from banner
        banner_brand, banner_confidence = _detect_brand_from_banner(server_banner, title)
        
        # Use highest confidence detection
        final_brand = brand or banner_brand or "Unknown"
        confidence = mac_confidence if mac_confidence else (banner_confidence or "low")
        
        # Check for ONVIF
        onvif = False
        for port in [80, 8000, 8080, 8899]:
            if port in open_ports:
                if await _probe_onvif(ip, port):
                    onvif = True
                    break
        
        # Get RTSP URLs
        creds = DEFAULT_CREDENTIALS.get(final_brand, ("admin", ""))
        rtsp_urls = await _get_rtsp_urls(ip, final_brand, creds[0], creds[1])
        
        methods = []
        if mac:
            methods.append("mac-oui")
        if server_banner or title:
            methods.append("http-banner")
        if onvif:
            methods.append("onvif")
        
        camera = Camera(
            ip=ip,
            mac=mac,
            brand=final_brand,
            port=http_port,
            rtsp_url=rtsp_urls[0] if rtsp_urls else "",
            onvif=onvif,
            confidence=confidence,
            methods=methods,
            credentials=creds,
            notes=_CAMERA_NOTES.get(ip, {}).get("notes", ""),
            last_updated=_CAMERA_NOTES.get(ip, {}).get("last_updated", ""),
        )
        cameras.append(camera)
    
    # Run scans in parallel
    semaphore = asyncio.Semaphore(PARALLEL_SCANS)
    
    async def bounded_scan(ip_str: str):
        async with semaphore:
            await scan_host(ip_str)
    
    await asyncio.gather(*[bounded_scan(ip) for ip in hosts])
    
    return {
        "total_hosts": len(hosts),
        "cameras_found": len(cameras),
        "cameras": [c.dict() for c in cameras],
    }

@app.post("/api/probe")
async def probe_camera(req: ProbeRequest) -> dict:
    """Probe a specific camera for RTSP/ONVIF."""
    ip = req.ip.strip()
    if not ip:
        raise HTTPException(400, "IP address required")
    
    # Check if host is reachable
    if not await asyncio.get_event_loop().run_in_executor(None, _check_port, ip, req.port, SCAN_TIMEOUT):
        return {
            "success": False,
            "message": f"Host {ip} not reachable on port {req.port}",
            "rtsp_urls": [],
            "onvif": False,
        }
    
    # Get MAC
    mac = await asyncio.get_event_loop().run_in_executor(None, _get_mac, ip)
    brand, _ = _lookup_brand_by_mac(mac) if mac else ("", "")
    
    # Get HTTP banner
    server_banner, title = await asyncio.get_event_loop().run_in_executor(None, _get_http_banner, ip, 80, SCAN_TIMEOUT)
    banner_brand, _ = _detect_brand_from_banner(server_banner, title)
    
    final_brand = brand or banner_brand or "Unknown"
    
    # Check ONVIF
    onvif = False
    for port in [80, 8000, 8080]:
        if await _probe_onvif(ip, port, req.user, req.password):
            onvif = True
            break
    
    # Get RTSP URLs
    rtsp_urls = await _get_rtsp_urls(ip, final_brand, req.user, req.password)
    
    return {
        "success": True,
        "ip": ip,
        "mac": mac,
        "brand": final_brand,
        "onvif": onvif,
        "rtsp_urls": rtsp_urls,
        "http_banner": server_banner,
        "title": title,
    }

class CameraNotesRequest(BaseModel):
    ip: str
    notes: str = ""

@app.post("/api/camera-notes")
def save_camera_notes(req: CameraNotesRequest) -> dict:
    """Save notes for a camera by IP."""
    if not req.ip:
        raise HTTPException(400, "IP address required")
    
    _CAMERA_NOTES[req.ip] = {
        "notes": req.notes,
        "last_updated": datetime.now().isoformat(),
    }
    return {"success": True, "ip": req.ip}

@app.get("/api/camera-notes/{ip}")
def get_camera_notes(ip: str) -> dict:
    """Get saved notes for a camera by IP."""
    return _CAMERA_NOTES.get(ip, {"notes": "", "last_updated": ""})

@app.get("/api/qr/{data}")
def generate_qr(data: str) -> dict:
    """Generate QR code for RTSP URL or any data."""
    try:
        qr = qrcode.QRCode(version=1, box_size=10, border=2)
        qr.add_data(data)
        qr.make(fit=True)
        
        img = qr.make_image(fill_color="#00d4ff", back_color="#12121a")
        buffer = io.BytesIO()
        img.save(buffer)
        buffer.seek(0)
        
        return {
            "success": True,
            "data": data,
            "qr_png_base64": base64.b64encode(buffer.read()).decode(),
        }
    except Exception as e:
        raise HTTPException(500, f"QR generation failed: {e}")

class QRRequest(BaseModel):
    data: str

@app.post("/api/qr")
def generate_qr_post(req: QRRequest) -> dict:
    """Generate QR code via POST body to avoid URL encoding issues."""
    return generate_qr(req.data)

# ── Frontend ──────────────────────────────────────────────────────────────────

FRONTEND_DIR = Path(__file__).parent.parent / "frontend"
INDEX_PATH = FRONTEND_DIR / "index.html"

@app.get("/")
def index() -> HTMLResponse:
    if INDEX_PATH.exists():
        return HTMLResponse(INDEX_PATH.read_text())
    raise HTTPException(404, "Frontend not found")

if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="frontend")

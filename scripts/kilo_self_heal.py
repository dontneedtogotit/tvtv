#!/usr/bin/env python3
"""
kilo_self_heal.py — Bounded Kilo Code API self-heal loop for tvtv HTPC install.

Captures an error log, asks the Kilo Code Gateway for a remediation command
from a strict allowlist, validates it, applies it, and retries the failed
operation. Exits 0 when the operation succeeds (possibly after retries),
1 when it still fails after all retries, 2 when the Kilo API is unreachable.

Stdlib only — safe to run on a fresh target with no venv.

Usage:
    python3 kilo_self_heal.py \
        --stage apt-install \
        --log /var/log/tvtv-apt.log \
        --cmd "apt-get install -y --no-install-recommends linux-firmware" \
        --max-retries 2
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

KILO_BASE_URL = os.environ.get("KILO_GATEWAY_URL", "https://api.kilo.ai/api/gateway")
KILO_TIMEOUT = 45  # seconds per API call

# ── Credential lookup (keys only; values never logged) ────────────────────────

def _get_kilo_api_key() -> str:
    key = os.environ.get("KILO_API_KEY", "")
    if key:
        return key
    for p in (
        Path.home() / ".config" / "tvtv" / "credentials.json",
        Path("/home/htpc/.config/tvtv/credentials.json"),
        Path("/home/htpc/tvtv/config/credentials.json"),
    ):
        try:
            d = json.loads(p.read_text())
            if "KILO_API_KEY" in d:
                return d["KILO_API_KEY"]
        except Exception:
            pass
    return ""

# ── Allowlists ─────────────────────────────────────────────────────────────────
# Kilo may only suggest commands matching these templates with these specific values.
# Anything outside is rejected. This is the safety boundary.

ALLOWED_PKGS = {
    "wpasupplicant", "iwd", "network-manager", "dhcpcd", "linux-firmware",
    "openssh-server", "curl", "wget", "git", "python3", "python3-pip",
    "python3-venv", "chrony", "ethtool", "samba", "snapd",
    "lm-sensors", "thermald", "pipewire", "wireplumber", "alsa-utils",
    "cec-utils", "ydotool", "ydotoold", "playerctl", "mpv", "yt-dlp",
    "nodejs", "epiphany-browser", "fonts-noto", "fonts-noto-color-emoji",
    "xdg-utils", "zram-tools", "labwc", "cage", "swaybg", "polkitd",
    "seatd", "dbus-x11", "xwayland", "mesa-va-drivers",
    "intel-media-va-driver-non-free", "intel-microcode", "iucode-tool",
    "ir-keytable", "unattended-upgrades",
}

ALLOWED_SERVICES = {
    "networkmanager", "wpa_supplicant", "systemd-resolved",
    "systemd-networkd", "udisks2", "tvtv-yt", "tvtv-updater",
    "ydotoold", "tvtv-cec-remote", "snapd", "ssh", "chrony",
    "thermald", "avahi-daemon",
}

ALLOWED_MODULES = {
    "uinput", "cec", "cec-gpio", "iwlwifi", "ath9k", "ath10k_pci",
    "ath10k", "ath11k_pci", "ath11k", "rt2800pci", "rt2800usb",
    "wpa_supplicant", "nf_conntrack", "iptable_filter", "ip_tables",
}

_INTERFACE_RE = re.compile(r"^(en[a-z0-9]+|wl[a-z0-9]+|eth[0-9]+|wlp[a-z0-9]+)$")

_KILO_MODELS = [
    "kilo-auto/free",
    "dots-studio/dots-3-note-preview:free",
    "stealth/space-bunny-alpha",
    "stepfun/step-3.7-flash:free",
]

SYSTEM_PROMPT = """\
You are a remediation assistant for an Ubuntu 24.04 HTPC appliance install.
You receive an error log. Respond with EXACTLY one JSON object, no prose, no markdown:
{"action": "<command>", "reason": "<one sentence>"}

The <command> must be one of these exact templates (substitute the placeholder with the specific value):
- apt-get update
- apt-get -f install
- dpkg --configure -a
- systemctl restart <service>.service
- systemctl enable <service>.service
- modprobe <module>
- ip link set <iface> up
- apt-get install -y --no-install-recommends <pkg>

Allowed services: {services}
Allowed packages: {pkgs}
Allowed modules: {modules}
If no allowed command fixes this error, respond: {{"action": "none", "reason": "<why>"}}
Do NOT invent commands outside this list. Do NOT include passwords, SSIDs, or credentials."""


def _validate_command(cmd: str) -> tuple[bool, str]:
    """Validate a Kilo-suggested command against the allowlist."""
    cmd = cmd.strip()
    if not cmd or cmd == "none":
        return (False, "no action suggested")

    if cmd == "apt-get update":
        return (True, cmd)
    if cmd == "apt-get -f install":
        return (True, cmd)
    if cmd == "dpkg --configure -a":
        return (True, cmd)

    m = re.match(r"^systemctl (restart|enable) ([a-z][a-z0-9-]*)\.service$", cmd)
    if m:
        svc = m.group(2)
        if svc in ALLOWED_SERVICES:
            return (True, cmd)
        return (False, f"service '{svc}' not in allowlist")

    m = re.match(r"^modprobe ([a-z][a-z0-9-]*)$", cmd)
    if m:
        mod = m.group(1)
        if mod in ALLOWED_MODULES:
            return (True, cmd)
        return (False, f"module '{mod}' not in allowlist")

    m = re.match(r"^ip link set ([a-z0-9]+) up$", cmd)
    if m:
        iface = m.group(1)
        if _INTERFACE_RE.match(iface):
            return (True, cmd)
        return (False, f"interface '{iface}' not recognised")

    m = re.match(r"^apt-get install -y --no-install-recommends (.+)$", cmd)
    if m:
        pkgs = m.group(1).split()
        for p in pkgs:
            if p not in ALLOWED_PKGS:
                return (False, f"package '{p}' not in allowlist")
        return (True, cmd)

    return (False, "command does not match any allowed template")


def _read_log_tail(path: str, lines: int = 200) -> str:
    try:
        text = Path(path).read_text(errors="replace")
        parts = text.splitlines()
        return "\n".join(parts[-lines:])
    except Exception:
        return "(could not read log file)"


def _ask_kilo(api_key: str, log_text: str) -> tuple[str | None, str]:
    """Ask Kilo for a remediation. Returns (action_command, reason)."""
    prompt = SYSTEM_PROMPT.format(
        services=", ".join(sorted(ALLOWED_SERVICES)),
        pkgs=", ".join(sorted(ALLOWED_PKGS)),
        modules=", ".join(sorted(ALLOWED_MODULES)),
    )
    messages = [
        {"role": "system", "content": prompt},
        {
            "role": "user",
            "content": f"Error log (last 200 lines):\n\n{log_text}\n\nWhat is the single most likely fix?",
        },
    ]
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    for model in _KILO_MODELS:
        payload = {
            "model": model,
            "messages": messages,
            "max_tokens": 256,
            "temperature": 0.1,
            "stream": False,
        }
        data = json.dumps(payload).encode()
        req = urllib.request.Request(
            f"{KILO_BASE_URL}/chat/completions",
            data=data,
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=KILO_TIMEOUT) as resp:
                body = json.loads(resp.read())
            if "error" in body:
                code = body["error"].get("code")
                if code in (429, 503, 502, 504):
                    continue  # transient, try next model
                return (None, f"API error: {body['error'].get('message', '')[:200]}")
            choice = body.get("choices", [{}])[0]
            raw = choice.get("message", {}).get("content", "").strip()
            # Strip code fences if present
            raw = re.sub(r"^```(?:json)?\s*", "", raw)
            raw = re.sub(r"\s*```$", "", raw)
            try:
                obj = json.loads(raw)
            except json.JSONDecodeError:
                # Try to extract JSON from prose
                m = re.search(r"\{.*\}", raw, re.DOTALL)
                if not m:
                    return (None, f"unparseable response: {raw[:200]}")
                obj = json.loads(m.group())
            action = obj.get("action", "none")
            reason = obj.get("reason", "")
            return (action, reason)
        except urllib.error.HTTPError as e:
            if e.code in (429, 503, 502, 504):
                continue
            return (None, f"HTTP {e.code}")
        except Exception as e:
            return (None, str(e)[:200])

    return (None, "all Kilo models failed or overloaded")


def _run(cmd: str, timeout: int = 300) -> tuple[int, str]:
    """Run a shell command, return (returncode, output)."""
    try:
        p = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return (p.returncode, (p.stdout + p.stderr).strip())
    except subprocess.TimeoutExpired:
        return (124, f"command timed out after {timeout}s")
    except Exception as e:
        return (1, str(e))


def main() -> int:
    ap = argparse.ArgumentParser(description="Bounded Kilo self-heal loop")
    ap.add_argument("--stage", required=True, help="stage name for logging")
    ap.add_argument("--log", required=True, help="path to error log file")
    ap.add_argument("--cmd", required=True, help="shell command to retry after fix")
    ap.add_argument("--max-retries", type=int, default=2, help="max Kilo-assisted retries (default 2)")
    args = ap.parse_args()

    api_key = _get_kilo_api_key()
    if not api_key:
        print(f"[self-heal:{args.stage}] No Kilo API key found; skipping self-heal.", file=sys.stderr)
        return 2

    for attempt in range(1, args.max_retries + 1):
        print(f"[self-heal:{args.stage}] Attempt {attempt}/{args.max_retries}", file=sys.stderr)
        log_text = _read_log_tail(args.log)
        action, reason = _ask_kilo(api_key, log_text)

        if not action or action == "none":
            print(f"[self-heal:{args.stage}] Kilo: no fix ({reason})", file=sys.stderr)
            break

        ok, msg = _validate_command(action)
        if not ok:
            print(f"[self-heal:{args.stage}] REJECTED {action!r}: {msg}", file=sys.stderr)
            break

        print(f"[self-heal:{args.stage}] Applying fix: {action} ({reason})", file=sys.stderr)
        rc, out = _run(action)
        print(f"[self-heal:{args.stage}] Fix exit={rc}: {out[:300]}", file=sys.stderr)

        if rc == 0:
            # Re-run the original command
            rc2, out2 = _run(args.cmd)
            if rc2 == 0:
                print(f"[self-heal:{args.stage}] SUCCESS after fix on attempt {attempt}", file=sys.stderr)
                return 0
            # Append retry failure to the log so next iteration sees it
            try:
                with open(args.log, "a") as f:
                    f.write(f"\n--- self-heal attempt {attempt} retry failed (rc={rc2}) ---\n{out2[:1000]}\n")
            except Exception:
                pass
        else:
            try:
                with open(args.log, "a") as f:
                    f.write(f"\n--- self-heal attempt {attempt} fix failed (rc={rc}) ---\n{out[:1000]}\n")
            except Exception:
                pass

    # Final bare retry (no Kilo) as a last resort
    print(f"[self-heal:{args.stage}] Final bare retry", file=sys.stderr)
    rc, out = _run(args.cmd)
    if rc == 0:
        print(f"[self-heal:{args.stage}] SUCCESS on final bare retry", file=sys.stderr)
        return 0

    print(f"[self-heal:{args.stage}] FAILED after all retries (rc={rc})", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())

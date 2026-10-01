#!/usr/bin/env python3
"""Idempotently customize Ubuntu Server GRUB config for tvtv HTPC OS Installer.

Bakes `autoinstall ds=nocloud;` (self-contained) or `autoinstall ds=nocloud-net;s=<url>`
(LAN-served) into GRUB config (boot/grub/grub.cfg and boot/grub/loopback.cfg),
customizes menu colors for 10-foot TV viewing, adds HTPC-branded presets,
and configures the boot timeout.

Usage:
    iso/patch-grub.py <grub.cfg> --self-contained [--timeout 10]
    iso/patch-grub.py <grub.cfg> --url <url> [--timeout 10]
"""
from __future__ import annotations

import argparse
import re
import sys

TIMEOUT_RE = re.compile(r'^(\s*set\s+timeout\s*=\s*)("?)([0-9]+)(\"?)\s*$')
MENUENTRY_RE = re.compile(r'^\s*menuentry\s+([\'"])(.*?)([\'"])\s*(.*)')


def _is_installer_kernel(line: str) -> bool:
    """True for a GRUB `linux` line that boots the casper installer kernel."""
    stripped = line.lstrip()
    return (
        stripped.startswith('linux')
        and not stripped.startswith('linux16')
        and '/casper/' in line
        and 'vmlinuz' in line
    )


def build_autoinstall_arg(self_contained: bool, url: str | None) -> str:
    if self_contained:
        return 'autoinstall ds=nocloud;'
    if url:
        return f'autoinstall ds=nocloud-net;s={url}'
    raise ValueError('Either --self-contained or --url must be provided')


def patch_text(text: str, self_contained: bool, url: str | None, timeout: int | None = None) -> tuple[str, int]:
    """Return (new_text, num_patched)."""
    autoinstall_arg = build_autoinstall_arg(self_contained, url)
    out: list[str] = []
    patched = 0
    timeout_set = False
    colors_injected = False

    # Check if TV colors already injected
    if 'menu_color_highlight' in text:
        colors_injected = True

    lines = text.split('\n')
    for idx, line in enumerate(lines):
        # Inject TV theme colors near the top after headers / loadfont
        if not colors_injected and (line.startswith('set default=') or line.startswith('set timeout=') or idx == 0):
            out.append('# ── tvtv HTPC OS 10-Foot Installer Theme ──────────────────────')
            out.append('set menu_color_normal=white/black')
            out.append('set menu_color_highlight=black/light-cyan')
            out.append('set color_normal=light-gray/black')
            out.append('set color_highlight=light-cyan/black')
            colors_injected = True

        # Timeout rewrite
        if timeout is not None and not timeout_set:
            m_time = TIMEOUT_RE.match(line)
            if m_time:
                out.append(f'{m_time.group(1)}{m_time.group(2)}{timeout}{m_time.group(4)}')
                timeout_set = True
                continue

        # Menu entry renaming for 10-foot HTPC branding
        m_menu = MENUENTRY_RE.match(line)
        if m_menu:
            title = m_menu.group(2)
            rest = m_menu.group(4)
            if 'Try or Install Ubuntu Server' in title or 'Ubuntu Server' in title and 'tvtv' not in title:
                new_title = '🚀 tvtv HTPC OS — Automated 10-Foot Install (Living Room TV)'
                out.append(f'menuentry "{new_title}" {rest}')
                continue
            elif 'Safe graphics' in title and 'tvtv' not in title:
                new_title = '📺 tvtv HTPC OS — Safe Graphics Mode (1080p HDMI)'
                out.append(f'menuentry "{new_title}" {rest}')
                continue

        # Autoinstall kernel arg injection
        if 'autoinstall' in line:
            out.append(line)
            continue

        if _is_installer_kernel(line):
            out.append(line.rstrip() + ' ' + autoinstall_arg)
            patched += 1
            continue

        out.append(line)

    return '\n'.join(out), patched


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description='Customize GRUB config for tvtv HTPC installer')
    ap.add_argument('path', help='path to a GRUB config file')
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument('--self-contained', action='store_true',
                      help='bake self-contained autoinstall (ds=nocloud;) reading user-data from ISO')
    mode.add_argument('--url', help='autoinstall URL for LAN-served config')
    ap.add_argument('--timeout', type=int, default=None,
                    help='optionally rewrite the GRUB menu timeout to this many seconds')
    args = ap.parse_args(argv)

    with open(args.path, 'r', encoding='utf-8', errors='surrogateescape') as f:
        text = f.read()

    new_text, patched = patch_text(text, args.self_contained, args.url, args.timeout)

    if patched == 0 and 'ds=nocloud' not in text:
        print(f'{args.path}: no installer kernel lines found (already patched?)', file=sys.stderr)
        return 1

    with open(args.path, 'w', encoding='utf-8', errors='surrogateescape') as f:
        f.write(new_text)

    desc = 'self-contained (ds=nocloud;)' if args.self_contained else f'LAN-served (ds=nocloud-net;s={args.url})'
    print(f'{args.path}: customized GRUB theme & patched {patched} kernel line(s) ({desc})')
    return 0


if __name__ == '__main__':
    sys.exit(main())

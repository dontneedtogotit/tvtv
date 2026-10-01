# Phase 8: Security & Isolation

Goal: an appliance that is safe to plug into a home LAN. Protect system resources,
restrict network exposure, isolate secrets, and enforce application boundaries.

Status: in progress. Core security hardening, CORS restrictions, credentials management,
and systemd isolation implemented and verified.

Tasks

- [ ] P8-1 API authentication: shared token/pairing session layer for remote & external callers.
- [x] P8-2 CORS restricted to loopback and RFC 1918 private LAN ranges via origin regex.
      Added standard security headers (X-Content-Type-Options, X-Frame-Options: SAMEORIGIN).
- [x] P8-3 Updater runs unprivileged (`User=htpc`) with `ProtectSystem=strict` and `PrivateTmp=true`.
- [ ] P8-4 Update payload verification: signature / SHA256 integrity validation before copy.
- [x] P8-5 Systemd hardening on units (`tvtv-yt.service`, `tvtv-updater.service`):
      `NoNewPrivileges=true`, `ProtectSystem=strict`, `ProtectHome=read-only`,
      `ReadWritePaths=`, `PrivateTmp=true`, `MemoryMax=4G`, `LimitNOFILE=65535`.
- [x] P8-6 Enforce manifest `permissions` array with inspection API (`has_permission()`)
      and load-time validation.
- [ ] P8-7 App sandboxing: run each app in an isolated process/transient unit with resource limits.
- [x] P8-8 Secrets out of unit files: `src/backend/credentials.py` reads from 0600 mode
      credentials file (`~/.config/tvtv/credentials.json`) with safe fallback order.
- [ ] P8-9 SSH optional and key-only by default in installer.
- [ ] P8-10 Firewall policy (UFW) + service exposure posture toggle in Settings.
- [x] P8-11 Path confinement for `media-library` and `file-manager`: strict validation against
      allowed storage roots, rejecting traversal (`/etc`, `/root`, `/etc/shadow` -> HTTP 403).
- [ ] P8-12 Input sanitization against shell/YAML injection in installer generators.

## Verification

- [x] P8-V1 `tests/test_security_phase8.py` — unit test suite exercising credentials mode 0600,
      systemd directives, permission inspection, path confinement, and CORS regex (30 checks, passes).

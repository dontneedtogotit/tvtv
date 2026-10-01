# Phase 12: Boot, Session & Display

Goal: a fast, self-healing, correctly-configured boot path.

Status: not started. Depends on Phase 18's CI to hold the boot budget.

Tasks

- [ ] P12-1 Measured boot budget with a CI gate (`systemd-analyze` target,
      currently unmeasured). Phase 5 listed "<15s to dashboard"; make it a
      number the build enforces.
- [ ] P12-2 `labwc.service` + `tvtv-session.target` replacing
      `agetty → .bash_profile → labwc`, so a crashed compositor restarts
      instead of dropping the box to a bare TTY.
- [ ] P12-3 Session watchdog: Chromium or dashboard death currently means a
      dead box until power cycle.
- [ ] P12-4 EDID-driven mode selection wired into the install path.
      `scripts/detect-tv.sh` exists but nothing calls it during install.
- [ ] P12-5 HDR / colour mode (`hdr-mode=auto`, HDR10 metadata). Absent
      despite a 4K preset existing in the installer.
- [ ] P12-6 Multi-output support — `WLR_OUTPUT` is hardcoded `HDMI-A-1` in
      three places.
- [ ] P12-7 Frame-rate switching / VRR for a large TV.
- [ ] P12-8 Hardened kiosk profile: dedicated `--user-data-dir` under
      `/var/lib/tvtv`, no first-run wizard, no crash-restore UI.
- [ ] P12-9 Idle/ambient mode and screen-off on long idle. Screen blanking is
      only disabled today.
- [ ] P12-10 Boot splash with progress so a 15s boot doesn't look like a
      hang.
- [ ] P12-11 CEC one-touch-play: switch the TV to the NUC input on playback
      start.
- [ ] P12-12 CEC volume sync in both directions.
- [ ] P12-13 User-editable CEC key map (data, not a bash `case`) with
      long-press and repeat-rate control.

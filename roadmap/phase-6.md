# Phase 6 — Ventoy/USB Installer

Goal: deliver the user-facing install path: Ventoy USB -> installer -> running NUC.

Status: complete. Self-contained remastered ISO built and verified.

Tasks
- [x] Custom installer app UI (`apps/installer/frontend/index.html`).
- [x] Hostname, user, display mode, audio, theme, and wifi settings.
- [x] Ubuntu Subiquity autoinstall canonical user-data generator.
- [x] Ventoy menu config (`iso/ventoy/ventoy.json`).
- [x] USB copy script (`iso/create-usb.sh`).
- [x] Actual ISO bake (`iso-output/tvtv-installer.iso`, 3.9GB hybrid BIOS+UEFI image with embedded autoinstall metadata and `ds=nocloud;` GRUB patching).
- [ ] Hardware boot test on physical NUC (manual step when user flashes USB).

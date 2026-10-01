# tvtv OS 10-Foot Appliance Installer

A TV-optimized, customizable operating system installer for turning an Intel NUC / Mini PC into a complete HTPC appliance connected to a 70"+ living-room TV.

---

## Features & Capabilities

- **70"+ TV 10-Foot UI**: Generous 22-26px base font size, bold high-contrast dark aesthetic, 4px solid focus rings with neon glow, full spatial D-pad remote navigation, and keyboard hotkeys.
- **Instant Hardware Presets**:
  - **70"+ Living Room TV (Samsung/LG/Sony)**: 1080p@60Hz safe HDMI, PipeWire Night Mode (dialogue vocal band EQ boost + compression), HDMI-CEC auto-wake and remote key mapping, Plasma Bigscreen + Estuary theme, YouTube + Cameras + Phone Web Remote.
  - **4K Home Theater (Dolby/DTS)**: 3840x2160 UHD @ 60Hz/30Hz, bitstream audio passthrough for AV receivers, high-bitrate MPV cache, Labwc kiosk.
  - **Ultra-Fast Minimal Kiosk**: Instant 3-second boot, lightweight Labwc Wayland kiosk (<200MB RAM), direct YouTube player.
  - **Complete HTPC OS & Surveillance**: Full stack with YouTube, NVR Camera Surveillance daemon, RTSP live feeds, ONVIF discovery, motion popup alerts on TV, Web Remote, Self-Updater, Samba media shares, and OpenSSH server.
- **PipeWire Night Mode**: Dynamic range compression + 1–4 kHz dialogue band boost so quiet movie dialogue is crystal clear while loud explosions stay contained.
- **Phone Web Remote**: Mobile remote served at `http://<tv-ip>:8080` with phone keyboard search typing, virtual D-pad, volume slider, and app launcher.
- **Storage & ZRAM**: Direct ext4, LVM, or ZFS layout with compressed in-memory ZRAM swap (zero SSD write endurance wear and instant speed).
- **Automated ISO Remastering**: Generates canonical Ubuntu 24.04 Subiquity cloud-config YAML (`user-data`) and bakes unattended ISOs via `iso/remaster.sh`.

---

## 1. Web 10-Foot Installer

1. Start tvtv stack: `./start-all.sh` or `bash scripts/start.sh`
2. Open the installer:
   - On the TV: navigate to `Installer` tile on dashboard or open `http://localhost:8000/apps-frontend/installer/`
   - On a phone / laptop on same Wi-Fi: open `http://<nuc-ip>:8000/apps-frontend/installer/`
3. Select a Preset or customize Display, Audio, CEC, Themes, Storage, and Apps.
4. Click **Generate Config** or press **G** on your remote/keyboard to generate `/tmp/tvtv-installer-user-data.yaml`.
5. Click **Bake Bootable Remastered ISO** to build an unattended ISO.

---

## 2. Terminal / CLI Installer (`install.sh`)

tvtv provides a unified CLI installer and convergence engine:

```bash
# Full interactive setup & convergence
sudo ./install.sh

# Verify system state without making changes
./install.sh --check

# Converge system state + update packages
sudo ./install.sh --update

# Converge system configuration only (skip apt)
sudo ./install.sh --no-packages

# Apply 70"+ TV UI couch scaling and theme tweaks
sudo ./install.sh --customize

# Create a bootable USB installer directly
sudo ./install.sh --make-usb /dev/sdX

# Prepare Ventoy USB data partition with ISO
sudo ./install.sh --prepare-ventoy /dev/sdX1

# Bake unattended ISO from terminal
sudo ./install.sh --bake-iso
```

---

## 3. Remote Navigation & Hotkeys

| Key / Button | Action |
|--------------|--------|
| **Arrow Keys / D-Pad** | Navigate cards and fields |
| **Enter / OK** | Select card, toggle switch, click button |
| **1, 2, 3, 4** | Jump to Preset 1-4 |
| **G** | Instant Generate Config |
| **P** | Live Cloud-Config YAML Preview Drawer |
| **Escape / Back** | Close modal / Back to main menu |

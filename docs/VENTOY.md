# tvtv-yt Ventoy Install

## Prepare USB

1. Install Ventoy on a USB stick.
2. Build or obtain `tvtv-installer.iso`.
3. Copy the ISO onto the Ventoy USB.
4. Boot the NUC from USB and select `tvtv Installer`.

## Installer options

The installer UI lets you choose:
- hostname
- username/password
- display mode: 1080p@60, 1080p@50, 720p@60, 4K@30
- optional WiFi SSID/password

## Generated config

- Writes `/tmp/tvtv-installer-user-data.yaml`
- Can be served over HTTP for Ubuntu autoinstall:
  `autoinstall ds=nocloud-net;s=http://<host>:8000/`

## Post-install

- Auto-login as `htpc`
- Labwc + Chromium kiosk
- Dashboard at http://localhost:8000

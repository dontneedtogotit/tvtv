# Install tvtv-yt on an Intel NUC

Four ways to get tvtv-yt onto the NUC. **Option A (manual) is the most
reliable and is what I recommend first** — it uses the same setup script the
autoinstall paths call, so you always end up in the same state.

- **Option A — Manual** (recommended): install Ubuntu Server 24.04, copy the
  repo, run `scripts/setup.sh`.
- **Option B — Custom installer ISO** (recommended unattended): `iso/remaster.sh`
  bakes `autoinstall` into the stock ISO's GRUB menu, so you flash it, boot the
  NUC, and it installs with **no GRUB editing**.
- **Option C — Netboot** (no ISO rebuild): boot a stock ISO and add one kernel
  arg at the GRUB menu.
- **Option D — Baked ISO + Ventoy**: build a fully self-contained ISO with
  `iso/Makefile` (root + chroot) and flash it to a Ventoy USB.

All four converge on the same result: user `htpc`, the tvtv backend as a
systemd service on `:8000`, and a Labwc + Chromium kiosk that auto-logs-in on
boot.

---

## Prerequisites

- Intel NUC with an Intel iGPU (VAAPI), HDMI out, Ethernet (or Wi-Fi).
- A TV with CEC (optional, for remote control).
- A USB stick (for the installer) and a USB keyboard (first boot only).
- A second machine on the same LAN to reach the NUC by SSH, and to host the
  autoinstall files for Options B and C.

---

## Option A — Manual install (recommended)

1. **Install Ubuntu Server 24.04 LTS** on the NUC (minimal install, OpenSSH
   server optional but handy). Create the `htpc` user during install.

2. **Copy the repo onto the NUC:**

   ```bash
   # from your dev machine
   rsync -a --exclude=.venv --exclude=.git /home/z/Projects/tvtv/ htpc@<nuc-ip>:tvtv/
   # or via USB stick: copy the repo to the stick, then on the NUC:
   #   cp -r /media/usb/tvtv ~/tvtv
   ```

3. **Run the setup script:**

   ```bash
   sudo mv ~/tvtv /home/htpc/tvtv    # setup.sh expects it at /home/htpc/tvtv
   sudo chown -R htpc:htpc /home/htpc/tvtv
   sudo bash /home/htpc/tvtv/scripts/setup.sh
   ```

   `setup.sh` installs packages (mpv, yt-dlp, labwc, swaybg, polkitd,
   cec-utils, ir-keytable, fonts), creates the `.venv`, installs the
   `tvtv-yt.service` systemd unit, writes the Labwc autostart, and configures
   autologin on tty1.

4. **Reboot:**

   ```bash
   sudo reboot
   ```

   The NUC auto-logs-in as `htpc` on tty1, `.bash_profile` starts Labwc, and
   the Labwc autostart launches Chromium in kiosk mode pointing at
   `http://localhost:8000/`. The backend is already up as a systemd service.

---

## Option B — Custom installer ISO (recommended unattended)

`iso/remaster.sh` remasters a stock Ubuntu Server 24.04 ISO so its default
GRUB entry already carries `autoinstall ds=nocloud-net;s=http://...`. You
flash it, boot the NUC, and it installs tvtv-yt with no keyboard and no GRUB
editing.

1. **Install the one required tool** (on the dev machine):

   ```bash
   sudo apt-get install -y xorriso
   ```

2. **Serve the autoinstall config** and leave it running:

   ```bash
   cd /home/z/Projects/tvtv
   ./scripts/serve-autoinstall.sh
   ```

   This serves `iso/autoinstall/` (user-data + meta-data) on port 8000. The
   repo is cloned from `https://github.com/dontneedtogotit/tvtv` during
   install, so only the two config files need to be served.

3. **Build the custom ISO** (on the same host, so the baked IP matches):

   ```bash
   ./iso/remaster.sh
   ```

   Output: `iso-output/tvtv-installer.iso`. It bakes
   `autoinstall ds=nocloud-net;s=http://<your-ip>:8000/` into GRUB (both the
   BIOS and UEFI paths) and sets the menu timeout to 10s.

4. **Flash and boot the NUC** — no GRUB editing:

   ```bash
   sudo dd if=iso-output/tvtv-installer.iso of=/dev/sdX bs=4M status=progress oflag=sync
   ```

   The install is fully unattended (wipes the disk via `direct` layout),
   reboots, and lands in the same state as Option A.

---

## Option C — Netboot (no ISO rebuild)

Same autoinstall, but you boot a stock Ubuntu Server ISO and type one kernel
arg at the GRUB menu instead of building a custom ISO.

1. **Serve the config** exactly as in Option B step 2 (`serve-autoinstall.sh`).
2. **Boot the NUC** from a stock Ubuntu Server 24.04 USB and add the kernel
   argument at the GRUB menu (press `e`, append before `---`):

   ```
   autoinstall ds=nocloud-net;s=http://<dev-machine-ip>:8000/
   ```

3. The install is fully unattended (wipes the disk via `direct` layout),
   reboots, and lands in the same state as Option A.

> **Password:** the default user is `htpc` / password `tvtv` (SHA-512 crypt
> hash baked into `user-data`). Change it before deploying — generate a new
> hash with `openssl passwd -6` and replace `identity.password` in
> `iso/autoinstall/user-data`.

---

## Option D — Baked ISO + Ventoy

Build a custom ISO with tvtv pre-baked, then boot it from a Ventoy USB.

1. **Install build tools** (on the dev machine, needs root + network):

   ```bash
   sudo apt-get install -y 7zip xorriso squashfs-tools p7zip-full
   ```

2. **Build the ISO:**

   ```bash
   cd /home/z/Projects/tvtv
   make -C iso iso        # downloads Ubuntu 24.04.2, bakes tvtv, repacks, writes iso-output/
   ```

   Output: `iso-output/tvtv-yt-0.1.0.iso`.

   > The Makefile's `customize` step runs `chroot` + `apt-get` to bake packages
   > into the squashfs and copies `iso/config/tvtv-setup.sh` +
   > `iso/config/tvtv-postinstall.service` into the live system so setup runs on
   > first boot. This step must run as root.

3. **Flash to Ventoy USB** (prepare the Ventoy stick once, then):

   ```bash
   sudo ./iso/create-usb.sh /dev/sdX      # sdX = the Ventoy USB device
   ```

   `create-usb.sh` copies the ISO into the Ventoy `iso/` dir and installs
   `iso/ventoy/ventoy.json`. **Before booting, edit the `ds=nocloud-net` URL
   in `iso/ventoy/ventoy.json`** to point at your HTTP server (it defaults to
   a placeholder `192.168.1.10`).

4. **Boot the NUC** from the Ventoy USB and select **"tvtv Installer"**.

---

## Post-install checks

- Backend health: `curl http://localhost:8000/api/health` →
  `{"status":"ok","yt_dlp":true,"mpv":true}`.
- Dashboard renders at `http://localhost:8000/` (Chromium kiosk on the TV).
- Search is fast (~2.5s) and returns thumbnails.
- CEC: TV remote arrows navigate; power button suspends the NUC.
- Media dir: `TVTV_MEDIA_DIR` (default `/home/htpc/media`).

## Known caveats

- **Video output under Wayland.** The backend runs as a systemd *system*
  service (`multi-user.target`) and launches `mpv` for playback; `mpv` must
  render inside the Labwc Wayland session, which starts separately on tty1.
  The service grants DRM access (`/dev/dri/*`) for VAAPI *decode*, but
  on-screen rendering needs the Wayland socket (`WAYLAND_DISPLAY` +
  `XDG_RUNTIME_DIR`). If playback audio-only or black-screen occurs, the
  clean fix is to run the backend from the Labwc autostart (inside the
  session) instead of as a system service, so `mpv` inherits the Wayland
  environment. This is the main remaining integration point.
- **CEC** power mapping relies on `cec-utils` + a udev rule; `setup-cec.sh`
  and `99-cec-power.rules` are placeholders and may need per-TV tuning.
- **`config/settings.json`** ships with `"default_quality": "720p"`; adjust to
  taste (the setting is honored by the play endpoint).
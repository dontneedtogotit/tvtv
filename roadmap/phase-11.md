# Phase 11: OS Identity, Rootfs & Storage

Goal: make it an operating system rather than a service on Ubuntu.

Status: not started. Depends on Phase 8 (hardening) and Phase 12 (session
units) so the read-only root doesn't fight a mutable install path.

Tasks

- [ ] P11-1 Read-only root: squashfs or erofs lower with an overlay upper,
      writable `/var`. Today the box mutates `/home/htpc/tvtv` in place.
- [ ] P11-2 A/B root partitions with slot flipping — the prerequisite for
      real OTA. Only meaningful with P11-1.
- [ ] P11-3 Dedicated media partition labelled `TVTV_MEDIA` with a systemd
      `.mount`/`.automount` unit. Retire the hardcoded `/home/htpc/media`
      default.
- [ ] P11-4 Branded identity: `tvtv-os` in `/etc/os-release`, hostname,
      `/etc/issue`, kernel cmdline branding, boot splash. It's currently
      stock Ubuntu 24.04 Server.
- [ ] P11-5 Rootfs integrity verification at boot (`dm-verity`, or a
      checksum verified in `tvtv-doctor.sh`).
- [ ] P11-6 `/etc/fstab` discipline: zram, samba share, ssh, and the media
      partition all declared as real units with ordering.
- [ ] P11-7 Disk-space guard: warn before playback fills the disk.
      `var/` and `~/.cache` grow unbounded today.
- [ ] P11-8 Journald caps (`SystemMaxUse`), logrotate for file logs, and a
      periodic vacuum job.
- [ ] P11-9 State snapshot/restore (settings, library index, history) around
      OTA.
- [ ] P11-10 Optional LUKS-encrypted media volume with TV-driven unlock at
      boot.
- [ ] P11-11 USB storage as a first-class library source with hotplug.
- [ ] P11-12 Flash write-endurance policy (tmpfs for logs/caches, read-mostly
      mounts) for eMMC/SD-based NUCs.
- [ ] P11-13 `fwupd` for firmware updates.

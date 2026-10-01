# Blocked / Manual Tasks

These steps are blocked from the agent because they require root, raw disk/filesystem operations, or a reboot.

## Manual steps required

1. Build rootfs
   - Run: `sudo bash iso/build-rootfs.sh iso/rootfs`

2. Create QEMU image
   - Run: `mkfs.ext4 -F iso/rootfs/rootfs.img`
   - Then mount and rsync:
     ```
     mount -o loop iso/rootfs/rootfs.img /mnt
     rsync -a --delete iso/rootfs/ /mnt/
     umount /mnt
     ```

3. Boot / reboot device
   - `sudo reboot` after installer/setup is not available from the agent.

## Why

The agent cannot perform unconditional system operations:
- system reboot/poweroff
- raw filesystem formatting
- direct writes to block devices

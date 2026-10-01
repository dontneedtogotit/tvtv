# tvtv-yt ISO Build System
# Builds a custom Ubuntu Server 24.04 LTS ISO with tvtv-yt pre-installed.

.PHONY: all clean build iso

ISO_NAME=tvtv-yt-0.1.0
BASE_ISO=ubuntu-24.04.2-live-server-amd64.iso
WORK_DIR=iso-work
OUTPUT_DIR=iso-output
# Project root (parent of this iso/ directory). Override if the layout differs.
SOURCE_DIR ?= $(abspath $(CURDIR)/..)

all: build

clean:
	rm -rf $(WORK_DIR) $(OUTPUT_DIR)

download-base:
	mkdir -p $(WORK_DIR)
	cd $(WORK_DIR) && \
	wget -q https://releases.ubuntu.com/24.04.2/$(BASE_ISO) || \
	wget -q https://releases.ubuntu.com/24.04/$(BASE_ISO)

prepare: download-base
	mkdir -p $(WORK_DIR)/extract $(WORK_DIR)/custom
	# Extract ISO
	cd $(WORK_DIR) && \
	7z x $(BASE_ISO) -oextract > /dev/null 2>&1 || \
	bsdtar -xf $(BASE_ISO) -C extract
	# Extract filesystem
	mkdir -p $(WORK_DIR)/fs
	cd $(WORK_DIR)/extract && \
	unsquashfs -d ../fs casper/filesystem.squashfs 2>/dev/null || \
	mksquashfs extract fs/casper/filesystem.squashfs -noappend

customize: prepare
	# Copy tvtv-yt code into filesystem (exclude VCS, venv, build output)
	@mkdir -p $(WORK_DIR)/fs/home/htpc/tvtv
	tar -C $(SOURCE_DIR) \
		--exclude=.git --exclude=.venv --exclude='__pycache__' \
		--exclude=iso/iso-work --exclude=iso/iso-output \
		-cf - . | tar -C $(WORK_DIR)/fs/home/htpc/tvtv -xf -
	# Copy autoinstall config
	mkdir -p $(WORK_DIR)/fs/var/www/autoinstall
	cp $(SOURCE_DIR)/iso/autoinstall/user-data $(WORK_DIR)/fs/var/www/autoinstall/
	# Create setup script
	mkdir -p $(WORK_DIR)/fs/usr/local/bin
	cp $(SOURCE_DIR)/iso/config/tvtv-setup.sh $(WORK_DIR)/fs/usr/local/bin/tvtv-setup.sh
	chmod +x $(WORK_DIR)/fs/usr/local/bin/tvtv-setup.sh
	# Add post-install hook
	mkdir -p $(WORK_DIR)/fs/etc/systemd/system
	cp $(SOURCE_DIR)/iso/config/tvtv-postinstall.service $(WORK_DIR)/fs/etc/systemd/system/
	# Extract the boot MBR (isohdpfx.bin) from the base ISO for hybrid boot
	xorriso -osirrox on -indev $(WORK_DIR)/$(BASE_ISO) -cpx /boot/grub/i386-pc/eltorito.img $(WORK_DIR)/eltorito.img 2>/dev/null || true
	dd if=$(WORK_DIR)/$(BASE_ISO) bs=1 count=432 of=$(WORK_DIR)/isohdpfx.bin 2>/dev/null || true
	# Extract the EFI boot image (FAT partition appended to the ISO)
	xorriso -osirrox on -indev $(WORK_DIR)/$(BASE_ISO) -cpx /efi.img $(WORK_DIR)/efi.img 2>/dev/null || true
	# Install additional packages
	chroot $(WORK_DIR)/fs apt-get update -qq
	chroot $(WORK_DIR)/fs apt-get install -y -qq \
		mpv yt-dlp labwc swaybg chromium \
		cec-utils fonts-noto fonts-noto-color-emoji \
		curl wget git python3-venv python3-pip

build: customize
	# Repack filesystem
	mksquashfs $(WORK_DIR)/fs $(WORK_DIR)/extract/casper/filesystem.squashfs \
		-noappend -comp xz -Xbcj x86 -b 1M
	# Update manifest
	chroot $(WORK_DIR)/fs dpkg-query -W --showformat='$${Package} $${Version}\n' > \
		$(WORK_DIR)/extract/casper/filesystem.manifest
	# Update md5sums (exclude the checksum file itself)
	cd $(WORK_DIR)/extract && find . -type f ! -name md5sum.txt -exec md5sum {} \; > md5sum.txt
	# Create ISO (hybrid UEFI + BIOS, GRUB2 based)
	mkdir -p $(OUTPUT_DIR)
	cd $(WORK_DIR)/extract && \
	xorriso -as mkisofs \
		-r -V "tvtv-yt" -J -joliet-long \
		-isohybrid-mbr ../isohdpfx.bin \
		-partition_offset 16 \
		--mbr-force-bootable \
		-append_partition 2 28732ac11ff8d211ba4b00a0c93ec93b ../efi.img \
		-appended_part_as_gpt \
		-iso_mbr_part_type a2a0d0ebe5b9334487c068b6b72699c7 \
		-c boot.cat \
		-b boot/grub/i386-pc/eltorito.img \
		-no-emul-boot -boot-load-size 4 -boot-info-table --grub2-boot-info \
		-eltorito-alt-boot \
		-e efi.img -no-emul-boot \
		-o ../../$(OUTPUT_DIR)/$(ISO_NAME).iso \
		. 2>/dev/null || \
	xorriso -as mkisofs -r -V "tvtv-yt" \
		-b boot/grub/i386-pc/eltorito.img \
		-no-emul-boot -boot-load-size 4 -boot-info-table \
		-o ../../$(OUTPUT_DIR)/$(ISO_NAME).iso \
		.
	@echo "ISO built: $(OUTPUT_DIR)/$(ISO_NAME).iso"

iso: build
	@echo "Build complete!"

# tvtv-yt ISO Build System
# Builds a custom Ubuntu Server 24.04 LTS ISO with tvtv-yt pre-installed.

.PHONY: all clean build iso

ISO_NAME=tvtv-yt-0.1.0
BASE_ISO=ubuntu-24.04.2-live-server-amd64.iso
WORK_DIR=iso-work
OUTPUT_DIR=iso-output

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
	# Copy tvtv-yt code into filesystem
	cp -r /home/z/Projects/tvtv $(WORK_DIR)/fs/home/htpc/tvtv
	# Copy autoinstall config
	mkdir -p $(WORK_DIR)/fs/var/www/autoinstall
	cp /home/z/Projects/tvtv/iso/autoinstall/user-data $(WORK_DIR)/fs/var/www/autoinstall/
	# Create setup script
	mkdir -p $(WORK_DIR)/fs/usr/local/bin
	cp /home/z/Projects/tvtv/iso/config/tvtv-setup.sh $(WORK_DIR)/fs/usr/local/bin/tvtv-setup.sh
	chmod +x $(WORK_DIR)/fs/usr/local/bin/tvtv-setup.sh
	# Add post-install hook
	mkdir -p $(WORK_DIR)/fs/etc/systemd/system
	cp /home/z/Projects/tvtv/iso/config/tvtv-postinstall.service $(WORK_DIR)/fs/etc/systemd/system/
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
	chroot $(WORK_DIR)/fs dpkg-query -W --showformat='${Package} ${Version}\n' > \
		$(WORK_DIR)/extract/casper/filesystem.manifest
	# Update md5sums
	cd $(WORK_DIR)/extract && find . -type f -exec md5sum {} \; > md5sum.txt
	# Create ISO
	mkdir -p $(OUTPUT_DIR)
	cd $(WORK_DIR)/extract && \
	xorriso -as mkisofs \
		-r -V "tvtv-yt" \
		--grub2-mbr ../iso-boot/mbr.bin \
		-partition_offset 16 \
		--mbr-force-bootable \
		--boot-load-size 64 \
		--boot-info-table \
		--grub2-boot-info \
		-c boot.cat \
		-b boot/grub/i386-pc/eltorito.img \
		-no-emul-boot \
		-boot-load-size 4 \
		-boot-info-table \
		--efi-boot efi.img \
		-efi-boot-part --efi-boot-image \
		-o ../$(OUTPUT_DIR)/$(ISO_NAME).iso \
		. 2>/dev/null || \
	mkisofs -r -V "tvtv-yt" -b boot/grub/i386-pc/eltorito.img \
		-no-emul-boot -boot-load-size 4 -boot-info-table \
		-o $(OUTPUT_DIR)/$(ISO_NAME).iso \
		$(WORK_DIR)/extract
	@echo "ISO built: $(OUTPUT_DIR)/$(ISO_NAME).iso"

iso: build
	@echo "Build complete!"

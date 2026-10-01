# Custom Installer

This installer frontend can generate Ubuntu autoinstall `user-data` and kernel args.

Recommended use with Ventoy:
1. Place `tvtv-installer.iso` on the Ventoy USB.
2. Boot the NUC from Ventoy.
3. Choose `tvtv Installer`.
4. The installer runs unattended with the provided settings.

Manual use:
1. Start backend and open `/apps-frontend/installer/`.
2. Fill hostname, user, display, WiFi.
3. Download generated `user-data`.
4. Boot Ubuntu Server ISO with:
   `autoinstall ds=nocloud-net;s=http://<host>:8000/`

# Phase 14: Network, Remote & Casting

Goal: the phone becomes a full controller and a sender, not just a keypad.

Status: not started. Pairs with Phase 8 on the exposure/auth story — do not
widen remote capability before auth exists.

Tasks

- [ ] P14-1 Wi-Fi configuration from the TV UI: scan and join. `nmcli` scan
      exists only inside the installer app, not in settings.
- [ ] P14-2 VPN client (WireGuard) with UI and per-app routing.
- [ ] P14-3 Wake-on-LAN and "wake this box to play X" from the phone.
- [ ] P14-4 Chromecast / DLNA / AirPlay receiver.
- [ ] P14-5 On-screen keyboard and real text entry on the TV. Today the only
      text path is `ydotool type:` from the phone.
- [ ] P14-6 Local speech-to-text for voice commands — `/api/ai/voice` parses
      text but nothing captures audio anywhere.
- [ ] P14-7 mDNS/Bonjour advertisement (`_tvtv._tcp`) for discovery.
- [ ] P14-8 Remote pairing UX with per-device permissions (Phase 8 auth).
- [ ] P14-9 Offline mode on the remote: cache the library so it degrades
      gracefully when the phone leaves the house and comes back.

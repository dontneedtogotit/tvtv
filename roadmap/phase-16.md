# Phase 16: App Ecosystem

Goal: apps that can actually be installed, isolated, and health-checked.

Status: not started. Builds on Phase 8's sandbox and Phase 7's store honesty
fix.

Tasks

- [ ] P16-1 Real lifecycle: install, remove, update, enable, disable, with
      disk accounting. Today the store lists local directories and assumes
      everything is installed.
- [ ] P16-2 Remote app repository with signing and version resolution.
- [ ] P16-3 Plugin isolation with resource limits (Phase 8 sandbox).
- [ ] P16-4 App navigation contract: declared focus order, back-stack, where
      `Escape` goes. The iframe launcher has no formal contract today.
- [ ] P16-5 App health monitoring with restart from the GUI.
- [ ] P16-6 Fold camera-setup into the app registry. It is currently a
      parallel standalone service on port 8002 with frontend code duplicated
      from `src/frontend/remote.html`, outside `start-all.sh`'s model, and
      unreachable from the remote.
- [ ] P16-7 Logs/debug viewer app over `journalctl`.
- [ ] P16-8 One-button diagnostic bundle export (support zip: doctor output,
      convergence check, service logs).
- [ ] P16-9 Settings sync across devices (Phase 17 profiles).
- [ ] P16-10 App icons and metadata in manifests surfaced in the grid.

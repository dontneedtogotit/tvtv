# Phase 5: Polish and Release — superseded, split across Phases 11, 12, 17, 18

Boot optimization, OTA rollback, i18n/accessibility and the compatibility
matrix all still open, now owned by later phases.

Tasks
- [~] boot optimization — no measurement, no budget, no CI gate.
  → Phase 12, task P12-1
- [~] OTA update pipeline — the updater service exists but runs as root with
  no backup, no rollback, and no signature verification.
  → Phase 8 (harden), Phase 11 (A/B slots)
- [ ] internationalization and accessibility
  → Phase 17
- [ ] hardware compatibility matrix
  → Phase 18
- [ ] end-user docs and release artifacts
  → Phase 18

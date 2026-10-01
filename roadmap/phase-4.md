# Phase 4: Apps and Plugin System — superseded, split across Phases 7, 8, 16

The registry and manifests shipped. Lifecycle, permissions, and the log
viewer did not.

Tasks
- [x] plugin manifest plus registry — `plugins/manifest.schema.json` +
  `src/backend/apps.py`
- [~] app store backend and frontend — lists local apps and hardcodes
  `installed: True`; no lifecycle endpoints.
  → Phase 7, task P7-8 (fix the lie); Phase 16 (real lifecycle)
- [~] permission model — every manifest declares `permissions`; nothing
  enforces them.
  → Phase 8, task P8-6
- [ ] app lifecycle management (install/update/remove/enable/disable)
  → Phase 16
- [ ] built-in apps: logs/debug viewer, capture
  → Phase 16
- [ ] settings sync across devices
  → Phase 16

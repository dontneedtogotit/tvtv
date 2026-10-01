# Phase 18: Quality & Release

Goal: make regressions impossible to miss, and ship a beta.

Status: not started. Highest leverage per line of code in the whole roadmap.

Evidence of the current gap: zero project tests (the `.pytest_cache` at the
repo root is not backed by any test file), no CI, and every verification in
this repo to date has been ad-hoc.

Tasks

- [ ] P18-1 Test suite. FastAPI `TestClient` over the main app + app
      routers, MPV IPC against a mock socket, installer user-data schema
      validation, manifest schema validation, focus-nav DOM tests.
- [ ] P18-2 CI on push: `bash -n` on shell scripts, `py_compile` on Python,
      pytest, and an ISO build smoke check. No `.github/` exists today.
- [ ] P18-3 Manifest schema validation in CI, not just in `plugins/`.
- [ ] P18-4 Single source of truth for systemd units. `install.sh` and
      `scripts/setup.sh` both write units independently and have drifted
      (including two different `KILO_API_KEY` injection mechanisms).
- [ ] P18-5 Config schema validation for `tv.conf` and `settings.json`.
- [ ] P18-6 Boot-time and memory regression budgets enforced in CI.
- [ ] P18-7 Structured logging with request IDs; replace the pervasive
      `except Exception: pass` in the backend and app routers.
- [ ] P18-8 Version manifest surfaced at `/api/health` so the updater and
      store have something real to compare.
- [ ] P18-9 Generated support matrix from `install.sh --check` +
      `tvtv-doctor.sh` output, published per release.
- [ ] P18-10 End-user docs: install, first-run, troubleshooting, recovery.
- [ ] P18-11 Release artifacts: tagged ISO, checksum, changelog.

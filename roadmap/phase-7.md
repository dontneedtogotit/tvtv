# Phase 7: Honesty & Wiring

Goal: make the installer and UI stop promising things the backend never
delivers. Every task here wires existing code to existing config — no new
subsystems, which is why this phase runs before Security.

Status: complete. All 16 tasks implemented and verified.

Tasks

## Declared-but-dead configuration

- [x] P7-1 `tv.conf` is loaded by the backend via `src/backend/profile.py`.
      `MPV_VO`, `MPV_HWDEC`, `MPV_SCALE`, `TV_AUDIO_PASSTHROUGH` and
      `TV_NIGHT_MODE` now reach MPV; `/api/health` reports the resolved
      profile. `TV_CEC_WAKE`, `WEB_REMOTE`, `CAMERA_HUB` are wired.
- [x] P7-2 `profile.mpv_args()` feeds `/api/play`; passthrough also forces
      `--hwdec=no`. Verified in `scripts/verify-phase7.py`.
- [x] P7-3 Backend reads and reports `TV_SCALE`. The Chromium
      `--force-device-scale-factor` flag is passed via profile resolution.
- [x] P7-4 `/api/trending` endpoint added to core backend and called from UI.
- [x] P7-5 `camera-setup/` moved under `apps/` with a manifest and a
      reverse-proxy router (`apps/camera-setup/backend/proxy.py`) to its
      scanner service on 8002. It appears in the app grid and the
      remote's Cameras button resolves.

## Player/feature wiring

- [x] P7-6 Subtitles reach MPV: `/subtitles` returns a URL and `PlayRequest`
      passes `--sub-file` to MPV. Selection UI is Phase 9 task P9-3.
- [x] P7-7 Playback position is checkpointed in-process via `src/backend/mpv.py`
      and a background task every 15s. History is keyed by URL.
      `/api/position` and `/api/control` no longer spawn python subprocesses.
- [x] P7-8 The App Store reports real disk state (`installed`, `built_in`,
      `disabled`), persists enable/disable state, prevents self-disable,
      and honestly states repository status.

## Stub backends & path confinement

- [x] P7-9 `apps/history` (`/in-progress`, `/recent`, `/play`), `apps/remote`
      (`/capabilities`), `apps/settings` (`/overview`, `/capabilities`)
      built out with real operational endpoints.
- [x] P7-10 `apps/media-library` and `apps/file-manager` enforce strict
      path confinement within allowed media roots (rejects `/etc` with 403).
- [x] P7-11 Settings persistence merges over disk instead of overwriting,
      preserving unknown/future keys.

## Robustness & updates

- [x] P7-12 App manifests validated against required schema at load time.
      Broken manifests are skipped and logged without taking down the server.
- [x] P7-13 `AppRegistry.app_router` registers modules in `sys.modules`
      before exec, fixing pydantic forward refs and restoring `/openapi.json`
      (49 routes documented).
- [x] P7-14 Updater creates backup refs and supports `POST /api/rollback`.
      In-repo `.version` file tracks current installed release.
- [x] P7-15 Added `.gitignore` and removed tracked `.pyc` cache artifacts.
- [x] P7-16 `README.md`, `docs/ARCHITECTURE.md`, `docs/APPS.md` updated to
      match all real routes, services, ports, and capabilities.

## Verification

- [x] P7-V1 `tests/test_app_registry.py` — manifest validation + registry
      resilience unit test (16 checks, passes).
- [x] P7-V2 `scripts/verify-phase7.py` — end-to-end integration test with
      live uvicorn, mock MPV socket, profile args, subtitle passing,
      checkpointing, settings merge, proxying, path confinement, and
      trending endpoint (48 checks, passes).

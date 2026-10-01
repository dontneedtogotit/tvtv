# Phase 13: Audio Engine

Goal: a living-room audio stack that behaves like one.

Status: not started. Task P13-4 first — `install.sh` currently deletes
`/etc/pipewire/pipewire.conf.d/90-hdmi-pin.conf` as obsolete while the design
calls HDMI pinning a feature, so the two must be reconciled before anything
is built on top.

Tasks

- [ ] P13-1 Night mode as a real PipeWire/WirePlumber `filter-chain`:
      loudness/limiter plus a 1–4 kHz dialogue band. Today `TV_NIGHT_MODE=1`
      is exported and nothing implements the DSP.
- [ ] P13-2 Passthrough wired to real profile switching (`profile.passthrough`)
      including TrueHD / DTS-HD / E-AC3, gated on display-port audio
      capability probing.
- [ ] P13-3 Output picker UI using `wpctl`. The doctor script calls `pactl`,
      which a PipeWire-only install may not provide.
- [ ] P13-4 Reconcile the HDMI audio pin (implement pinning, or drop the
      claim from docs and `BAD_FILES`).
- [ ] P13-5 Per-app volume offsets, notification ducking, master limiter.
- [ ] P13-6 Bluetooth audio pairing and output switching (soundbar /
      headphones). There is no Bluetooth code anywhere today.
- [ ] P13-7 Persisted per-output EQ curves.
- [ ] P13-8 Audio delay / lip-sync compensation for TV.

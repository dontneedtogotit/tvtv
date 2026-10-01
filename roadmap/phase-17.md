# Phase 17: UX, Accessibility & i18n

Goal: the interface is actually usable by a whole household — by a
five-year-old, a grandparent, and a screen-reader user, in any language.

Status: not started.

Evidence of the current gap: the main 10-foot UI
(`src/frontend/index.html`, 34 KB) contains **zero** `aria-*` attributes, no
focus trap, no reduced-motion handling, and every string is hardcoded English.

Tasks

- [ ] P17-1 Accessibility pass on the shell and every app frontend:
      `aria-*` roles/states/labels, `aria-live` for status changes, focus
      trap in the app iframe, logical tab order matching visual order.
- [ ] P17-2 Screen-reader mode with sensible reading order for a D-pad UI.
- [ ] P17-3 High-contrast theme and a reduced-motion setting honoured in CSS.
- [ ] P17-4 Full i18n. `locale` is set in the autoinstall identity and never
      reaches the UI; every string is hardcoded English.
- [ ] P17-5 Long-press and context menus on cards — CEC remotes emit
      long-press and currently nothing handles it.
- [ ] P17-6 Predictable multi-level back-stack semantics for the shell + app
      iframes (currently one level of back).
- [ ] P17-7 Notification centre: updates available, storage low, network
      lost, recording finished.
- [ ] P17-8 First-boot onboarding wizard in the UI for manually installed
      boxes (today the installer app only exists in the install path).
- [ ] P17-9 User profiles with per-profile limits and a kid mode.
- [ ] P17-10 Theme store. `TV_THEME` exists and exactly one theme ships.
- [ ] P17-11 Home-rail live widgets: weather, system temperature, camera
      status.
- [ ] P17-12 Parental controls / content filtering.

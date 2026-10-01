// tvtv shared focus navigation: keyboard + CEC-like arrow key support.
// Supports spatial arrow movement, Enter to activate, Page Up/Down to jump a
// row, Home/End to jump to first/last, and Escape to emit a "back" event.

export function initFocusNav(root = document) {
  const focusableSelector = [
    'button', 'input', 'select', 'textarea',
    '[tabindex]:not([tabindex="-1"])',
    '.tile', '.nav-tab', '.video-card', '.app', '.row-item', '[data-focusable]',
  ].join(',');

  const focusable = () => Array.from(root.querySelectorAll(focusableSelector))
    .filter(el => !el.hasAttribute('disabled') && !el.hasAttribute('aria-hidden') && el.offsetParent !== null)
    .map(el => { if (el.tabIndex < 0) el.tabIndex = 0; return el; });

  let index = 0;

  const setFocus = (el) => {
    el.classList.add('focused');
    el.focus({ preventScroll: false });
  };
  const clearFocus = (el) => el.classList.remove('focused');

  // Move focus to the nearest element along a direction vector.
  const move = (dx, dy) => {
    const items = focusable();
    if (!items.length) return;
    if (index >= items.length) index = 0;
    clearFocus(items[index]);
    const current = items[index].getBoundingClientRect();
    const cx = current.left + current.width / 2;
    const cy = current.top + current.height / 2;
    let best = -1;
    let bestScore = Infinity;
    for (let i = 0; i < items.length; i++) {
      if (i === index) continue;
      const r = items[i].getBoundingClientRect();
      const icx = r.left + r.width / 2;
      const icy = r.top + r.height / 2;
      const ddx = icx - cx;
      const ddy = icy - cy;
      // Primary axis must advance in the intended direction.
      if (dx > 0 && ddx <= 0) continue;
      if (dx < 0 && ddx >= 0) continue;
      if (dy > 0 && ddy <= 0) continue;
      if (dy < 0 && ddy >= 0) continue;
      const dist = Math.hypot(ddx, ddy);
      // Penalize off-axis distance to prefer same row/column.
      const offAxis = dx !== 0 ? Math.abs(ddy) : Math.abs(ddx);
      const score = dist + offAxis * 0.7;
      if (score < bestScore) { bestScore = score; best = i; }
    }
    if (best !== -1) index = best;
    setFocus(items[index]);
    items[index].scrollIntoView({ block: 'nearest', inline: 'nearest' });
  };

  // Jump focus by a "page" - skip over items on the same row.
  const page = (dir) => {
    const items = focusable();
    if (!items.length) return;
    if (index >= items.length) index = 0;
    clearFocus(items[index]);
    const cur = items[index].getBoundingClientRect();
    let candidates = items.map((el, i) => ({ i, r: el.getBoundingClientRect() }))
      .filter(({ i }) => i !== index);
    // Prefer items directly above/below, beyond the current row.
    candidates = candidates.filter(({ r }) =>
      dir > 0 ? r.top > cur.top : r.bottom < cur.bottom);
    candidates.sort((a, b) => dir > 0 ? a.r.top - b.r.top : b.r.bottom - a.r.bottom);
    const best = candidates.find(({ r }) =>
      dir > 0 ? r.top >= cur.bottom - 4 : r.bottom <= cur.top + 4) || candidates[0];
    if (best) index = best.i;
    setFocus(items[index]);
    items[index].scrollIntoView({ block: 'center', inline: 'nearest' });
  };

  const first = () => { const it = focusable(); if (it.length) { index = 0; setFocus(it[0]); } };
  const last = () => { const it = focusable(); if (it.length) { index = it.length - 1; setFocus(it[index]); } };

  root.addEventListener('keydown', (e) => {
    switch (e.key) {
      case 'ArrowRight': e.preventDefault(); move(1, 0); break;
      case 'ArrowLeft': e.preventDefault(); move(-1, 0); break;
      case 'ArrowDown': e.preventDefault(); move(0, 1); break;
      case 'ArrowUp': e.preventDefault(); move(0, -1); break;
      case 'PageDown': e.preventDefault(); page(1); break;
      case 'PageUp': e.preventDefault(); page(-1); break;
      case 'Home': e.preventDefault(); first(); break;
      case 'End': e.preventDefault(); last(); break;
      case 'Enter': {
        e.preventDefault();
        const it = focusable();
        if (it[index]) it[index].click();
        break;
      }
      case 'Escape': {
        e.preventDefault();
        root.dispatchEvent(new CustomEvent('tvtv:back', { bubbles: true }));
        // When embedded in the tvtv shell, notify the parent to close us.
        if (window.parent && window.parent !== window) {
          window.parent.postMessage('tvtv:back', '*');
        }
        break;
      }
    }
  });

  const items = focusable();
  if (items.length) setFocus(items[index]);

  return {
    focus: (i) => { const it = focusable(); if (it[i]) { index = i; setFocus(it[i]); } },
    refocus: () => { const it = focusable(); if (it.length) { index = Math.min(index, it.length - 1); setFocus(it[index]); } },
  };
}
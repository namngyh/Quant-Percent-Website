/* Draggable dividers.

   Two of them: one between the side panel and the charts, one between the
   price chart and the indicator panes below it. Sizes are remembered per
   browser, because a layout you had to set up again on every visit is worse
   than one you cannot change at all. */

const Resizer = (() => {
  const KEY = 'qp.layout.v1';

  const LIMITS = {
    // 300, not 260: below that the paper ticket's two prices and the stop and
    // target fields no longer fit side by side and started wrapping mid-number.
    panel: { min: 300, max: 640, fallback: 344 },
    panes: { min: 90, max: 420, fallback: 128 },
  };

  let layout = { panel: LIMITS.panel.fallback, panes: LIMITS.panes.fallback };
  let onChange = () => {};

  function load() {
    try {
      const saved = JSON.parse(localStorage.getItem(KEY) || '{}');
      for (const key of Object.keys(layout)) {
        const value = Number(saved[key]);
        if (Number.isFinite(value)) layout[key] = clamp(key, value);
      }
    } catch {
      // Unreadable storage just means the defaults stand.
    }
  }

  function save() {
    try {
      localStorage.setItem(KEY, JSON.stringify(layout));
    } catch {
      // Nothing to do; the size still applies for this session.
    }
  }

  const clamp = (key, value) =>
    Math.max(LIMITS[key].min, Math.min(LIMITS[key].max, Math.round(value)));

  function apply() {
    const root = document.documentElement;
    root.style.setProperty('--panel-w', `${layout.panel}px`);
    root.style.setProperty('--pane-h', `${layout.panes}px`);
    onChange();
  }

  /** Wire one divider. `axis` is 'x' for width, 'y' for height. */
  function attach(handle, key, axis, { invert = false } = {}) {
    if (!handle) return;

    let startPos = 0;
    let startValue = 0;

    const move = (event) => {
      const pos = axis === 'x' ? event.clientX : event.clientY;
      const delta = (pos - startPos) * (invert ? -1 : 1);
      layout[key] = clamp(key, startValue + delta);
      apply();
    };

    const end = () => {
      document.removeEventListener('pointermove', move);
      document.removeEventListener('pointerup', end);
      document.body.classList.remove('resizing', 'resizing-x', 'resizing-y');
      handle.classList.remove('active');
      save();
    };

    handle.addEventListener('pointerdown', (event) => {
      event.preventDefault();
      startPos = axis === 'x' ? event.clientX : event.clientY;
      startValue = layout[key];
      document.addEventListener('pointermove', move);
      document.addEventListener('pointerup', end);
      // The axis class pins one cursor for the whole drag. Without it the
      // pointer flickered between a text caret, an arrow and the resize arrow
      // as it crossed labels, buttons and the chart during the gesture.
      document.body.classList.add('resizing', axis === 'x' ? 'resizing-x' : 'resizing-y');
      handle.classList.add('active');
    });

    // Double-click restores the default, so a mis-drag is one gesture to undo.
    handle.addEventListener('dblclick', () => {
      layout[key] = LIMITS[key].fallback;
      apply();
      save();
    });

    // Keyboard: the divider is focusable, so it can be nudged without a mouse.
    handle.tabIndex = 0;
    handle.addEventListener('keydown', (event) => {
      const step = event.shiftKey ? 40 : 10;
      const keys = axis === 'x'
        ? { ArrowLeft: -step, ArrowRight: step }
        : { ArrowUp: -step, ArrowDown: step };
      const delta = keys[event.key];
      if (delta === undefined) return;
      event.preventDefault();
      layout[key] = clamp(key, layout[key] + delta * (invert ? -1 : 1));
      apply();
      save();
    });
  }

  function init(config) {
    onChange = config.onChange || (() => {});
    load();
    apply();
    attach(document.getElementById('resize-panel'), 'panel', 'x');
    attach(document.getElementById('resize-panes'), 'panes', 'y', { invert: true });
  }

  // Each chart in the grid has its own divider above its indicator panes;
  // they all set the one shared pane height.
  function attachPanes(handle) {
    attach(handle, 'panes', 'y', { invert: true });
  }

  return { init, attachPanes, get layout() { return { ...layout }; } };
})();

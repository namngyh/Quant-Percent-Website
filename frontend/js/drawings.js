/* Drawing on the chart: trend lines, levels, boxes, Fibonacci, text, a ruler.
 *
 * Lightweight Charts 4.2.3 has no drawing tools at all, so this is a canvas
 * laid over the chart and kept in step with it. The only thing that makes that
 * work is anchoring every shape in *chart* coordinates — a time and a price —
 * and converting to pixels at paint time:
 *
 *     timeScale().timeToCoordinate(time)   ->  x
 *     series.priceToCoordinate(price)      ->  y
 *
 * Anchoring in pixels instead would be far simpler and completely wrong: the
 * drawing would slide off its bars the moment anyone scrolled, zoomed, resized
 * the window, or switched timeframe. Anchored in chart space it stays welded
 * to the candles it was drawn against, which is the entire point of drawing on
 * a chart rather than on a screenshot.
 *
 * Repainting is driven by the chart's own events (visible range, crosshair)
 * plus a resize observer, so the overlay never runs a render loop of its own.
 *
 * Shapes are stored per symbol+timeframe in localStorage. They are notes about
 * one series; showing a trend line drawn on BTC 1h over VIC daily would be
 * worse than losing it.
 */

/* One drawing layer per chart; `Drawings`, at the bottom, is the active one. */
function createDrawings() {
  const STORE_KEY = 'qp.drawings';
  /* Ink, like the rest of the chrome. A drawing is the user's own annotation,
     not market data, so it must not borrow the green and red that mean
     direction — and on a white ground with green and red candles, black is
     the one colour that reads clearly over both. */
  const COLOUR = '#131722';
  const HIT_PX = 7;          // how close the pointer must be to grab a shape

  /* The toolbar. `id` is the stored tool name; `points` is how many clicks a
     shape takes, which is also what tells the state machine when it is done. */
  const TOOLS = [
    { id: 'cursor', points: 0, label: () => L('Con trỏ', 'Cursor') },
    { id: 'trend', points: 2, label: () => L('Đường xu hướng', 'Trend line') },
    { id: 'horizontal', points: 1, label: () => L('Đường ngang', 'Horizontal line') },
    { id: 'ray', points: 2, label: () => L('Tia ngang', 'Horizontal ray') },
    { id: 'vertical', points: 1, label: () => L('Đường dọc', 'Vertical line') },
    { id: 'rect', points: 2, label: () => L('Hình chữ nhật', 'Rectangle') },
    { id: 'fib', points: 2, label: () => L('Fibonacci thoái lui', 'Fib retracement') },
    { id: 'text', points: 1, label: () => L('Chữ', 'Text') },
    { id: 'measure', points: 2, label: () => L('Thước đo', 'Measure') },
  ];

  const FIB_LEVELS = [0, 0.236, 0.382, 0.5, 0.618, 0.786, 1];

  let chart = null;
  let series = null;
  // The chart manager this layer belongs to, for snapping and bar counts.
  let manager = null;
  // Only the active chart's layer answers the keyboard: Delete and Escape
  // must not act on shapes in a chart nobody is looking at.
  let isActive = true;
  let observer = null;
  let canvas = null;
  let ctx = null;
  let host = null;

  let tool = 'cursor';
  let shapes = [];           // committed shapes for the current series
  let pending = null;        // the shape being drawn, before its last click
  let hover = null;          // pointer position in chart coords, for previews
  let dragging = null;       // { shape, grabbedAt, origin }
  let selected = null;       // the shape the cursor last picked up
  let seriesKey = null;      // symbol + timeframe these shapes belong to
  let visible = true;
  let locked = false;
  let magnet = false;
  let onChange = () => {};

  // ---------- coordinate conversion ----------

  const toX = (time) => chart?.timeScale().timeToCoordinate(time);
  const toY = (price) => series?.priceToCoordinate(price);
  const fromX = (x) => chart?.timeScale().coordinateToTime(x);
  const fromY = (y) => series?.coordinateToPrice(y);

  /* A point in chart space. Returns null when the pointer is off the plotted
     range — `coordinateToTime` gives null past the last bar, and a shape
     anchored to a null time can never be drawn again. */
  function pointAt(clientX, clientY) {
    const rect = canvas.getBoundingClientRect();
    const x = clientX - rect.left;
    const y = clientY - rect.top;
    const time = fromX(x);
    let price = fromY(y);
    if (time === null || time === undefined || price === null) return null;
    if (magnet) price = snapToBar(time, price);
    return { time, price };
  }

  /* Magnet: pull the price to the nearest OHLC value of the bar under the
     pointer. Snapping to the bar's own levels is what makes a line drawn "off
     the high" actually sit on the high, rather than a pixel above it. */
  function snapToBar(time, price) {
    const bar = (manager || ChartManager).barAt?.(time);
    if (!bar) return price;
    const levels = [bar.open, bar.high, bar.low, bar.close];
    let best = price;
    let bestGap = Infinity;
    for (const level of levels) {
      const gap = Math.abs(level - price);
      if (gap < bestGap) { bestGap = gap; best = level; }
    }
    return best;
  }

  // ---------- storage ----------

  function load(key) {
    seriesKey = key;
    shapes = [];
    try {
      const all = JSON.parse(localStorage.getItem(STORE_KEY) || '{}');
      if (Array.isArray(all[key])) shapes = all[key];
    } catch { /* unreadable store: start empty rather than fail to draw */ }
    pending = null;
    selected = null;
    paint();
    onChange();
  }

  function save() {
    if (!seriesKey) return;
    try {
      const all = JSON.parse(localStorage.getItem(STORE_KEY) || '{}');
      if (shapes.length) all[seriesKey] = shapes;
      else delete all[seriesKey];
      localStorage.setItem(STORE_KEY, JSON.stringify(all));
    } catch { /* quota or private mode: the drawings still work this session */ }
  }

  // ---------- painting ----------

  function resize() {
    if (!canvas || !host) return;
    const rect = host.getBoundingClientRect();
    const dpr = window.devicePixelRatio || 1;
    canvas.width = Math.round(rect.width * dpr);
    canvas.height = Math.round(rect.height * dpr);
    canvas.style.width = `${rect.width}px`;
    canvas.style.height = `${rect.height}px`;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    paint();
  }

  function paint() {
    if (!ctx || !canvas) return;
    const dpr = window.devicePixelRatio || 1;
    ctx.clearRect(0, 0, canvas.width / dpr, canvas.height / dpr);
    if (!visible) return;

    for (const shape of shapes) drawShape(shape, false);
    if (pending) drawShape(previewOf(pending), true);
  }

  /* The shape as it looks mid-draw: its committed points plus wherever the
     pointer is now. Without this the second click is a leap of faith. */
  function previewOf(p) {
    if (!hover) return p;
    return { ...p, points: [...p.points, hover] };
  }

  function screenPoints(shape) {
    return shape.points.map((pt) => ({ x: toX(pt.time), y: toY(pt.price) }));
  }

  function drawShape(shape, isPreview) {
    const pts = screenPoints(shape);
    // A point whose time has scrolled out of the loaded range converts to
    // null; drawing with null coordinates paints nothing and warns nowhere, so
    // the shape is skipped explicitly.
    if (pts.some((p) => p.x === null || p.y === null
                     || p.x === undefined || p.y === undefined)) return;

    const isSelected = shape === selected && !isPreview;

    ctx.save();
    ctx.strokeStyle = shape.colour || COLOUR;
    ctx.fillStyle = shape.colour || COLOUR;
    ctx.lineWidth = isSelected ? 2.5 : 1.5;
    ctx.setLineDash(isPreview ? [4, 4] : []);
    ctx.font = '12px system-ui, sans-serif';

    const w = canvas.width / (window.devicePixelRatio || 1);
    const [a, b] = pts;

    switch (shape.tool) {
      case 'trend':
        if (!b) break;
        line(a.x, a.y, b.x, b.y);
        break;

      case 'horizontal':
        line(0, a.y, w, a.y);
        label(`${fmt(shape.points[0].price)}`, w - 6, a.y - 5, 'right');
        break;

      case 'ray':
        if (!b) break;
        // From the first point rightwards at the first point's price, which is
        // what a "ray" means on a chart: a level that starts somewhere.
        line(a.x, a.y, w, a.y);
        break;

      case 'vertical':
        line(a.x, 0, a.x, canvas.height / (window.devicePixelRatio || 1));
        break;

      case 'rect': {
        if (!b) break;
        const x = Math.min(a.x, b.x);
        const y = Math.min(a.y, b.y);
        ctx.globalAlpha = 0.12;
        ctx.fillRect(x, y, Math.abs(b.x - a.x), Math.abs(b.y - a.y));
        ctx.globalAlpha = 1;
        ctx.strokeRect(x, y, Math.abs(b.x - a.x), Math.abs(b.y - a.y));
        break;
      }

      case 'fib': {
        if (!b) break;
        const from = shape.points[0].price;
        const to = shape.points[1].price;
        const x0 = Math.min(a.x, b.x);
        const x1 = Math.max(a.x, b.x);
        for (const level of FIB_LEVELS) {
          const price = from + (to - from) * level;
          const y = toY(price);
          if (y === null) continue;
          ctx.globalAlpha = level === 0 || level === 1 ? 0.9 : 0.55;
          line(x0, y, Math.max(x1, x0 + 40), y);
          ctx.globalAlpha = 1;
          label(`${(level * 100).toFixed(1)}%  ${fmt(price)}`, x0 + 4, y - 4, 'left');
        }
        break;
      }

      case 'text':
        label(shape.text || '', a.x, a.y, 'left', true);
        break;

      case 'measure': {
        if (!b) break;
        const from = shape.points[0];
        const to = shape.points[1];
        const move = ((to.price - from.price) / from.price) * 100;
        const bars = (manager || ChartManager).barsBetween?.(from.time, to.time) ?? null;
        ctx.globalAlpha = 0.12;
        ctx.fillRect(Math.min(a.x, b.x), Math.min(a.y, b.y),
                     Math.abs(b.x - a.x), Math.abs(b.y - a.y));
        ctx.globalAlpha = 1;
        line(a.x, a.y, b.x, b.y);
        // Both numbers, because "how far" on a chart is two questions: how far
        // in price and how far in time.
        const text = bars === null
          ? `${move >= 0 ? '+' : ''}${move.toFixed(2)}%`
          : `${move >= 0 ? '+' : ''}${move.toFixed(2)}%  ·  ${bars} ${L('nến', 'bars')}`;
        label(text, (a.x + b.x) / 2, Math.min(a.y, b.y) - 6, 'center', true);
        break;
      }

      default:
        break;
    }

    /* Handles on the selected shape's anchors: they say which shape is about
       to be deleted, and they are the part you grab to move it. */
    if (isSelected) {
      ctx.setLineDash([]);
      for (const p of pts) {
        ctx.beginPath();
        ctx.arc(p.x, p.y, 4, 0, Math.PI * 2);
        ctx.fillStyle = '#fff';
        ctx.fill();
        ctx.lineWidth = 2;
        ctx.strokeStyle = shape.colour || COLOUR;
        ctx.stroke();
      }
    }
    ctx.restore();
  }

  function line(x1, y1, x2, y2) {
    ctx.beginPath();
    ctx.moveTo(x1, y1);
    ctx.lineTo(x2, y2);
    ctx.stroke();
  }

  function label(text, x, y, align = 'left', boxed = false) {
    if (!text) return;
    ctx.textAlign = align;
    const width = ctx.measureText(text).width;
    if (boxed) {
      const left = align === 'center' ? x - width / 2 - 5 : x - 5;
      ctx.save();
      ctx.globalAlpha = 0.92;
      ctx.fillStyle = '#fff';
      ctx.fillRect(left, y - 13, width + 10, 17);
      ctx.strokeRect(left, y - 13, width + 10, 17);
      ctx.restore();
    }
    ctx.fillText(text, x, y);
  }

  const fmt = (v) => Number(v).toLocaleString(I18n.locale(), {
    minimumFractionDigits: 2, maximumFractionDigits: 2,
  });

  // ---------- hit testing ----------

  function distanceToSegment(px, py, x1, y1, x2, y2) {
    const dx = x2 - x1;
    const dy = y2 - y1;
    const lengthSq = dx * dx + dy * dy;
    // A zero-length segment is a point, and projecting onto it divides by zero.
    const t = lengthSq === 0 ? 0
      : Math.max(0, Math.min(1, ((px - x1) * dx + (py - y1) * dy) / lengthSq));
    return Math.hypot(px - (x1 + t * dx), py - (y1 + t * dy));
  }

  /** The topmost shape within HIT_PX of the pointer, or null. */
  function shapeAt(x, y) {
    for (let i = shapes.length - 1; i >= 0; i -= 1) {
      const shape = shapes[i];
      const pts = screenPoints(shape);
      if (pts.some((p) => p.x === null || p.y === null)) continue;
      const [a, b] = pts;
      const w = canvas.width / (window.devicePixelRatio || 1);
      let near = Infinity;
      if (shape.tool === 'horizontal' || shape.tool === 'ray') {
        near = Math.abs(y - a.y);
      } else if (shape.tool === 'vertical') {
        near = Math.abs(x - a.x);
      } else if (shape.tool === 'text') {
        near = Math.hypot(x - a.x, y - a.y);
      } else if (b) {
        near = shape.tool === 'rect' || shape.tool === 'fib' || shape.tool === 'measure'
          ? Math.min(
            distanceToSegment(x, y, a.x, a.y, b.x, a.y),
            distanceToSegment(x, y, b.x, a.y, b.x, b.y),
            distanceToSegment(x, y, b.x, b.y, a.x, b.y),
            distanceToSegment(x, y, a.x, b.y, a.x, a.y),
          )
          : distanceToSegment(x, y, a.x, a.y, b.x, b.y);
      }
      if (near <= HIT_PX) return shape;
    }
    return null;
  }

  // ---------- interaction ----------

  function onPointerDown(event) {
    if (!visible) return;
    const rect = canvas.getBoundingClientRect();
    const x = event.clientX - rect.left;
    const y = event.clientY - rect.top;

    if (tool === 'cursor') {
      if (locked) return;
      const hit = shapeAt(x, y);
      if (hit !== selected) { selected = hit; paint(); onChange(); }
      if (!hit) return;
      const at = pointAt(event.clientX, event.clientY);
      if (!at) return;
      // Moving a shape moves every anchor by the same delta, so its geometry
      // is preserved: dragging a Fib must not also rescale it.
      dragging = { shape: hit, from: at, origin: hit.points.map((p) => ({ ...p })) };
      canvas.setPointerCapture(event.pointerId);
      event.preventDefault();
      event.stopPropagation();
      return;
    }

    const at = pointAt(event.clientX, event.clientY);
    if (!at) return;
    event.preventDefault();
    event.stopPropagation();

    const spec = TOOLS.find((t) => t.id === tool);
    if (!pending) pending = { tool, points: [at], colour: COLOUR, id: Date.now() };
    else pending.points.push(at);

    if (pending.points.length >= spec.points) commit();
    else paint();
  }

  function commit() {
    if (pending.tool === 'text') {
      const text = window.prompt(L('Nội dung ghi chú', 'Note text'), '');
      if (!text) { pending = null; paint(); return; }
      pending.text = text;
    }
    shapes.push(pending);
    selected = pending;
    pending = null;
    save();

    /* Back to the cursor once a shape is finished.

       The tool used to stay armed so that drawing five levels was five clicks.
       That is the wrong trade: it means every click afterwards draws another
       shape, including the click you make to select the one you just drew, and
       the only way out is to notice the toolbar. Ten shapes in and wanting to
       delete the fifth, you cannot even point at it. Drawing is occasional;
       looking at the chart is constant, so the resting state is the cursor. */
    setTool('cursor');
    paint();
    onChange();
  }

  function onPointerMove(event) {
    if (!visible) return;
    const at = pointAt(event.clientX, event.clientY);

    if (dragging && at) {
      const dt = at.time - dragging.from.time;
      const dp = at.price - dragging.from.price;
      dragging.shape.points = dragging.origin.map((p) => ({
        time: p.time + dt, price: p.price + dp,
      }));
      paint();
      return;
    }

    if (pending) { hover = at; paint(); return; }

    // Only claim the pointer when there is something under it, or the chart
    // beneath can never be panned.
    if (tool === 'cursor' && !locked) {
      const rect = canvas.getBoundingClientRect();
      const over = shapeAt(event.clientX - rect.left, event.clientY - rect.top);
      canvas.style.cursor = over ? 'move' : '';
      canvas.style.pointerEvents = over ? 'auto' : 'none';
    }
  }

  function onPointerUp(event) {
    if (dragging) {
      dragging = null;
      save();
      try { canvas.releasePointerCapture(event.pointerId); } catch { /* already released */ }
    }
  }

  function onKey(event) {
    if (!isActive) return;
    if (event.key === 'Escape') {
      pending = null;
      hover = null;
      selected = null;
      setTool('cursor');
      paint();
      onChange();
      return;
    }
    /* Delete removes the selected shape — but not while the user is typing.
       Without the target check, backspacing a symbol out of the search box
       would quietly delete a drawing behind it. */
    if (event.key !== 'Delete' && event.key !== 'Backspace') return;
    const el = event.target;
    if (el && (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA' || el.isContentEditable)) return;
    if (removeSelected()) event.preventDefault();
  }

  /** Delete the selected shape. Returns whether there was one. */
  function removeSelected() {
    if (!selected || locked) return false;
    const at = shapes.indexOf(selected);
    if (at < 0) { selected = null; return false; }
    shapes.splice(at, 1);
    selected = null;
    save();
    paint();
    onChange();
    return true;
  }

  // ---------- public ----------

  function setTool(id) {
    if (!TOOLS.some((t) => t.id === id)) return tool;
    tool = id;
    pending = null;
    hover = null;
    /* The overlay only swallows the pointer while a drawing tool is active.
       Left on, it would eat every pan and zoom on the chart underneath — the
       tool would work and the chart would appear frozen. */
    canvas.style.pointerEvents = id === 'cursor' ? 'none' : 'auto';
    canvas.style.cursor = id === 'cursor' ? '' : 'crosshair';
    paint();
    onChange();
    return tool;
  }

  function undo() {
    if (!shapes.length) return;
    if (shapes.pop() === selected) selected = null;
    save();
    paint();
    onChange();
  }

  function clear() {
    if (!shapes.length) return;
    shapes = [];
    selected = null;
    save();
    paint();
    onChange();
  }

  function setVisible(on) { visible = on; paint(); onChange(); }
  function setLocked(on) { locked = on; onChange(); }
  function setMagnet(on) { magnet = on; onChange(); }

  function init(config) {
    chart = config.chart;
    series = config.series;
    host = config.host;
    manager = config.manager || null;
    onChange = config.onChange || (() => {});

    canvas = document.createElement('canvas');
    canvas.className = 'draw-layer';
    canvas.style.pointerEvents = 'none';
    host.appendChild(canvas);
    ctx = canvas.getContext('2d');

    canvas.addEventListener('pointerdown', onPointerDown);
    // Move and up listen on the window: a drag that leaves the canvas should
    // keep dragging, and a pointer released outside it should still finish.
    window.addEventListener('pointermove', onPointerMove);
    window.addEventListener('pointerup', onPointerUp);
    window.addEventListener('keydown', onKey);

    // Repaint whenever the chart moves under the drawings.
    chart.timeScale().subscribeVisibleLogicalRangeChange(paint);
    chart.subscribeCrosshairMove(() => { if (pending) paint(); });
    observer = new ResizeObserver(resize);
    observer.observe(host);
    resize();
  }

  /** Becoming inactive also disarms a half-chosen tool on this layer. */
  function setActive(on) {
    isActive = Boolean(on);
    if (!isActive && canvas) {
      pending = null;
      hover = null;
      if (tool !== 'cursor') setTool('cursor');
    }
  }

  function destroy() {
    window.removeEventListener('pointermove', onPointerMove);
    window.removeEventListener('pointerup', onPointerUp);
    window.removeEventListener('keydown', onKey);
    observer?.disconnect();
    canvas?.remove();
    canvas = null;
    ctx = null;
  }

  /** The price series changed shape, so coordinates come from the new one. */
  function setSeries(next) {
    series = next;
    paint();
  }

  return {
    init, load, setSeries, setTool, undo, clear, resize, paint,
    setVisible, setLocked, setMagnet, removeSelected, setActive, destroy,
    get hasSelection() { return selected !== null; },
    get tools() { return TOOLS.slice(); },
    get tool() { return tool; },
    get count() { return shapes.length; },
    get visible() { return visible; },
    get locked() { return locked; },
    get magnet() { return magnet; },
  };
}

const DrawingHub = (() => {
  let active = createDrawings();
  return {
    create: () => createDrawings(),
    get active() { return active; },
    setActive(layer) { if (layer) active = layer; },
  };
})();

const Drawings = new Proxy({}, {
  get: (_, prop) => DrawingHub.active[prop],
  set: (_, prop, value) => { DrawingHub.active[prop] = value; return true; },
});

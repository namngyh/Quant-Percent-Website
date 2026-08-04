/* RAEMF-MC dashboard — vanilla JS, không phụ thuộc thư viện ngoài. */
"use strict";

const $ = (sel) => document.querySelector(sel);
const SVG_NS = "http://www.w3.org/2000/svg";
const nf = new Intl.NumberFormat("en-US", { maximumFractionDigits: 2 });
const pf = new Intl.NumberFormat("en-US", { style: "percent", maximumFractionDigits: 1 });

const REGIMES = [
  { key: "Bull", label: "Bull (tăng)", cssVar: "--bull" },
  { key: "Sideway", label: "Sideway (đi ngang)", cssVar: "--sideway" },
  { key: "Bear", label: "Bear (giảm)", cssVar: "--bear" },
  { key: "Stress", label: "Stress (căng thẳng)", cssVar: "--stress" },
];
const regimeColor = (key) => {
  const item = REGIMES.find((r) => r.key === key);
  return item ? getComputedStyle(document.documentElement).getPropertyValue(item.cssVar).trim() : "#888";
};

/* ---------- theme ---------- */
function initTheme() {
  const saved = localStorage.getItem("raemf-theme");
  if (saved) document.documentElement.dataset.theme = saved;
  $("#theme-toggle").addEventListener("click", () => {
    const cur = document.documentElement.dataset.theme
      || (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
    const next = cur === "dark" ? "light" : "dark";
    document.documentElement.dataset.theme = next;
    localStorage.setItem("raemf-theme", next);
    renderAllCharts();
  });
}

/* ---------- fetch helpers ---------- */
async function getJSON(url) {
  const res = await fetch(url);
  if (!res.ok) {
    let detail = res.statusText;
    try { detail = (await res.json()).detail || detail; } catch (_) { /* noop */ }
    throw new Error(detail);
  }
  return res.json();
}

/* ---------- tooltip ---------- */
const tooltip = $("#tooltip");
function showTooltip(x, y, title, rows) {
  tooltip.replaceChildren();
  const t = document.createElement("div");
  t.className = "tt-title";
  t.textContent = title;
  tooltip.appendChild(t);
  for (const row of rows) {
    const el = document.createElement("div");
    el.className = "tt-row";
    const key = document.createElement("span");
    key.className = "tt-key";
    if (row.color) {
      const line = document.createElement("span");
      line.className = "tt-line";
      line.style.color = row.color;
      key.appendChild(line);
    }
    key.appendChild(document.createTextNode(row.label));
    const val = document.createElement("span");
    val.className = "tt-val";
    val.textContent = row.value;
    el.append(key, val);
    tooltip.appendChild(el);
  }
  tooltip.hidden = false;
  const rect = tooltip.getBoundingClientRect();
  const px = Math.min(x + 14, window.innerWidth - rect.width - 8);
  const py = Math.min(y + 14, window.innerHeight - rect.height - 8);
  tooltip.style.left = `${Math.max(4, px)}px`;
  tooltip.style.top = `${Math.max(4, py)}px`;
}
function hideTooltip() { tooltip.hidden = true; }

/* ---------- SVG helpers ---------- */
function svgEl(tag, attrs) {
  const el = document.createElementNS(SVG_NS, tag);
  for (const [k, v] of Object.entries(attrs || {})) el.setAttribute(k, v);
  return el;
}
function niceTicks(min, max, count) {
  if (!(max > min)) { max = min + 1; }
  const span = max - min;
  const step0 = span / Math.max(1, count);
  const mag = Math.pow(10, Math.floor(Math.log10(step0)));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => span / s <= count) || 10 * mag;
  const start = Math.ceil(min / step) * step;
  const ticks = [];
  for (let v = start; v <= max + 1e-9; v += step) ticks.push(v);
  return ticks;
}
function cssColor(name) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

/* Khung tọa độ chung: trả về scale + vẽ trục/lưới. */
function buildFrame(container, yMin, yMax, opts) {
  const W = 960, H = 320, m = { top: 14, right: 20, bottom: 30, left: 56 };
  container.replaceChildren();
  const svg = svgEl("svg", { viewBox: `0 0 ${W} ${H}`, role: "img" });
  container.appendChild(svg);
  const innerW = W - m.left - m.right, innerH = H - m.top - m.bottom;
  const pad = (yMax - yMin) * 0.06 || 1;
  const y0 = yMin - pad, y1 = yMax + pad;
  const sy = (v) => m.top + innerH - ((v - y0) / (y1 - y0)) * innerH;
  const sx = (i, n) => m.left + (n <= 1 ? innerW / 2 : (i / (n - 1)) * innerW);
  for (const tick of niceTicks(y0, y1, 5)) {
    svg.appendChild(svgEl("line", { x1: m.left, x2: W - m.right, y1: sy(tick), y2: sy(tick), class: "gridline" }));
    const label = svgEl("text", { x: m.left - 8, y: sy(tick) + 4, "text-anchor": "end", style: "font-variant-numeric: tabular-nums" });
    label.textContent = nf.format(tick);
    svg.appendChild(label);
  }
  svg.appendChild(svgEl("line", { x1: m.left, x2: W - m.right, y1: m.top + innerH, y2: m.top + innerH, class: "axisline" }));
  (opts.xTicks || []).forEach(({ index, text }) => {
    const x = sx(index, opts.n);
    const label = svgEl("text", { x, y: H - 8, "text-anchor": "middle" });
    label.textContent = text;
    svg.appendChild(label);
  });
  return { svg, sx: (i) => sx(i, opts.n), sy, W, H, m, innerW, innerH };
}

function linePath(frame, values, indexOffset = 0) {
  let d = "";
  values.forEach((v, i) => {
    if (v == null) return;
    d += `${d ? "L" : "M"}${frame.sx(i + indexOffset).toFixed(2)},${frame.sy(v).toFixed(2)}`;
  });
  return d;
}

/* Lớp hover: crosshair bám theo X gần nhất + tooltip cho mọi series. */
function attachHover(frame, container, n, onIndex) {
  const hair = svgEl("line", { class: "crosshair", y1: frame.m.top, y2: frame.m.top + frame.innerH, visibility: "hidden" });
  frame.svg.appendChild(hair);
  const dot = svgEl("circle", { r: 4.5, fill: cssColor("--accent"), stroke: cssColor("--surface-1"), "stroke-width": 2, visibility: "hidden" });
  frame.svg.appendChild(dot);
  const toIndex = (evt) => {
    const rect = frame.svg.getBoundingClientRect();
    const x = ((evt.clientX - rect.left) / rect.width) * frame.W;
    const frac = (x - frame.m.left) / frame.innerW;
    return Math.max(0, Math.min(n - 1, Math.round(frac * (n - 1))));
  };
  frame.svg.addEventListener("pointermove", (evt) => {
    const i = toIndex(evt);
    const x = frame.sx(i);
    hair.setAttribute("x1", x); hair.setAttribute("x2", x);
    hair.setAttribute("visibility", "visible");
    const info = onIndex(i, evt);
    if (info && info.dotY != null) {
      dot.setAttribute("cx", x); dot.setAttribute("cy", info.dotY);
      dot.setAttribute("visibility", "visible");
    } else {
      dot.setAttribute("visibility", "hidden");
    }
  });
  frame.svg.addEventListener("pointerleave", () => {
    hair.setAttribute("visibility", "hidden");
    dot.setAttribute("visibility", "hidden");
    hideTooltip();
  });
}

/* ---------- biểu đồ giá ---------- */
let priceData = null;
let priceDays = 365;

async function loadPrice() {
  priceData = await getJSON(`/api/price?days=${priceDays}`);
  renderPriceChart();
}
function renderPriceChart() {
  if (!priceData) return;
  const { dates, close } = priceData;
  const container = $("#price-chart");
  if (!dates.length) { container.textContent = "Chưa có dữ liệu."; return; }
  const values = close.filter((v) => v != null);
  const n = dates.length;
  const tickCount = Math.min(6, n);
  const xTicks = Array.from({ length: tickCount }, (_, k) => {
    const index = Math.round((k / Math.max(1, tickCount - 1)) * (n - 1));
    return { index, text: dates[index] };
  });
  const frame = buildFrame(container, Math.min(...values), Math.max(...values), { n, xTicks });
  frame.svg.appendChild(svgEl("path", {
    d: linePath(frame, close), fill: "none", stroke: cssColor("--accent"),
    "stroke-width": 2, "stroke-linejoin": "round", "stroke-linecap": "round",
  }));
  const lastIdx = n - 1;
  frame.svg.appendChild(svgEl("circle", {
    cx: frame.sx(lastIdx), cy: frame.sy(close[lastIdx]), r: 4.5,
    fill: cssColor("--accent"), stroke: cssColor("--surface-1"), "stroke-width": 2,
  }));
  const endLabel = svgEl("text", {
    x: frame.sx(lastIdx) - 6, y: frame.sy(close[lastIdx]) - 10, "text-anchor": "end",
    style: "fill: var(--text-primary); font-weight: 600; font-size: 12px",
  });
  endLabel.textContent = nf.format(close[lastIdx]);
  frame.svg.appendChild(endLabel);
  attachHover(frame, container, n, (i, evt) => {
    showTooltip(evt.clientX, evt.clientY, dates[i], [
      { label: "Đóng cửa", value: nf.format(close[i]), color: cssColor("--accent") },
    ]);
    return { dotY: frame.sy(close[i]) };
  });
}

/* ---------- biểu đồ dự phóng Monte Carlo ---------- */
let mcData = null;
let mcHorizon = 20;

async function loadMC() {
  try {
    mcData = await getJSON(`/api/mc-quantiles?horizon=${mcHorizon}`);
  } catch (err) {
    $("#mc-chart").textContent = `Chưa có dự phóng (${err.message})`;
    mcData = null;
    return;
  }
  renderMCChart();
}
function renderMCChart() {
  if (!mcData) return;
  const q = mcData.quantiles;
  const steps = mcData.steps;
  const n = steps.length;
  const container = $("#mc-chart");
  const allVals = [...q.q025, ...q.q975].filter((v) => v != null);
  // Bỏ tick cuối để không đè lên nhãn trục "số phiên tới" ở mép phải.
  const xTicks = niceTicks(0, steps[n - 1], 6)
    .filter((v) => Number.isInteger(v) && v < steps[n - 1] * 0.93)
    .map((v) => ({ index: v, text: `${v}` }));
  const frame = buildFrame(container, Math.min(...allVals), Math.max(...allVals), { n, xTicks });
  const xAxisTitle = svgEl("text", { x: frame.W - frame.m.right, y: frame.H - 8, "text-anchor": "end" });
  xAxisTitle.textContent = "số phiên tới";
  frame.svg.appendChild(xAxisTitle);

  const band = (lo, hi, opacityVar) => {
    let d = "";
    hi.forEach((v, i) => { d += `${d ? "L" : "M"}${frame.sx(i).toFixed(2)},${frame.sy(v).toFixed(2)}`; });
    for (let i = n - 1; i >= 0; i -= 1) d += `L${frame.sx(i).toFixed(2)},${frame.sy(lo[i]).toFixed(2)}`;
    frame.svg.appendChild(svgEl("path", { d: `${d}Z`, fill: opacityVar, stroke: "none" }));
  };
  band(q.q025, q.q975, cssColor("--accent-soft"));
  band(q.q250, q.q750, cssColor("--accent-soft-2"));
  frame.svg.appendChild(svgEl("path", {
    d: linePath(frame, q.q500), fill: "none", stroke: cssColor("--accent"),
    "stroke-width": 2, "stroke-linejoin": "round", "stroke-linecap": "round",
  }));
  attachHover(frame, container, n, (i, evt) => {
    showTooltip(evt.clientX, evt.clientY, `Phiên +${steps[i]}`, [
      { label: "Trung vị", value: nf.format(q.q500[i]), color: cssColor("--accent") },
      { label: "Vùng 50%", value: `${nf.format(q.q250[i])} – ${nf.format(q.q750[i])}` },
      { label: "Vùng 95%", value: `${nf.format(q.q025[i])} – ${nf.format(q.q975[i])}` },
    ]);
    return { dotY: frame.sy(q.q500[i]) };
  });

  const legend = $("#mc-legend");
  legend.replaceChildren();
  const items = [
    { swatch: "line", color: cssColor("--accent"), text: "Trung vị mô phỏng" },
    { swatch: "rect", color: cssColor("--accent-soft-2"), text: "Vùng 50% (q25–q75)" },
    { swatch: "rect", color: cssColor("--accent-soft"), text: "Vùng 95% (q2.5–q97.5)" },
  ];
  for (const item of items) {
    const el = document.createElement("span");
    el.className = "legend-item";
    const key = document.createElement("span");
    if (item.swatch === "line") { key.className = "legend-line"; key.style.borderTopColor = item.color; }
    else { key.className = "legend-swatch"; key.style.background = item.color; }
    el.append(key, document.createTextNode(item.text));
    legend.appendChild(el);
  }

  const s = mcData.summary || {};
  const box = $("#mc-summary");
  box.replaceChildren();
  const entries = [
    ["Lợi suất kỳ vọng", s.expected_return, pf],
    ["Xác suất tăng", s.prob_positive, pf],
    ["Xác suất drawdown > 10%", s.prob_drawdown_gt_10pct, pf],
    ["VaR 95%", s.var_95, pf],
  ];
  for (const [label, value, fmt] of entries) {
    if (value == null) continue;
    const el = document.createElement("span");
    const b = document.createElement("b");
    b.textContent = fmt.format(value);
    el.append(`${label}: `, b);
    box.appendChild(el);
  }
}

/* ---------- xác suất trạng thái ---------- */
async function loadOutlook() {
  let outlook;
  try {
    outlook = await getJSON("/api/outlook");
  } catch (err) {
    $("#prob-grid").textContent = `Chưa có dự báo (${err.message})`;
    return;
  }
  $("#outlook-date").textContent = `Tính đến phiên ${outlook.as_of_date}`;
  for (const h of [20, 40, 60]) {
    const info = outlook.horizons?.[h];
    const classEl = $(`#class-${h}`);
    const confEl = $(`#conf-${h}`);
    if (!info) { classEl.textContent = "—"; continue; }
    classEl.replaceChildren();
    const dot = document.createElement("span");
    dot.className = "class-dot";
    dot.style.background = regimeColor(info.predicted_class);
    classEl.append(dot, document.createTextNode(info.predicted_class));
    confEl.textContent = `Độ tin cậy: ${info.confidence} · xác suất ${pf.format(info.probabilities[info.predicted_class])}`;
  }
  const grid = $("#prob-grid");
  grid.replaceChildren();
  for (const h of [20, 40, 60]) {
    const info = outlook.horizons?.[h];
    if (!info) continue;
    const card = document.createElement("div");
    card.className = "prob-card";
    const title = document.createElement("h3");
    title.textContent = `${h} phiên · dự báo: ${info.predicted_class}`;
    card.appendChild(title);
    for (const regime of REGIMES) {
      const p = info.probabilities[regime.key] ?? 0;
      const row = document.createElement("div");
      row.className = "prob-row" + (regime.key === info.predicted_class ? " predicted" : "");
      const name = document.createElement("span");
      name.className = "prob-name";
      const dot = document.createElement("span");
      dot.className = "class-dot";
      dot.style.width = "9px"; dot.style.height = "9px";
      dot.style.background = regimeColor(regime.key);
      name.append(dot, document.createTextNode(regime.key));
      name.title = regime.label;
      const track = document.createElement("div");
      track.className = "prob-track";
      const fill = document.createElement("div");
      fill.className = "prob-fill";
      fill.style.width = `${(p * 100).toFixed(1)}%`;
      fill.style.background = regimeColor(regime.key);
      track.appendChild(fill);
      const val = document.createElement("span");
      val.className = "prob-val";
      val.textContent = pf.format(p);
      row.append(name, track, val);
      card.appendChild(row);
    }
    grid.appendChild(card);
  }
}

/* ---------- hình pipeline ---------- */
async function loadFigures() {
  const box = $("#figures");
  try {
    const { groups } = await getJSON("/api/figures");
    box.replaceChildren();
    for (const group of groups) {
      const h = document.createElement("h3");
      h.textContent = group.updated ? `${group.group} · cập nhật ${group.updated}` : group.group;
      box.appendChild(h);
      for (const url of group.files) {
        const a = document.createElement("a");
        a.href = url; a.target = "_blank"; a.rel = "noopener";
        const img = document.createElement("img");
        img.src = url; img.loading = "lazy";
        img.alt = url.split("/").pop().split("?")[0];
        a.appendChild(img);
        box.appendChild(a);
      }
    }
  } catch (err) {
    box.textContent = `Không tải được hình (${err.message})`;
  }
}

/* ---------- trạng thái & jobs ---------- */
let lastJobState = null;
let jobPollTimer = null;

function setJobChip(state) {
  const chip = $("#job-chip");
  chip.classList.remove("good", "running", "bad");
  if (!state) { chip.textContent = "✓ sẵn sàng"; chip.classList.add("good"); return; }
  if (state === "running") { chip.textContent = "⏳ đang chạy…"; chip.classList.add("running"); }
  else if (state === "success") { chip.textContent = "✓ hoàn tất"; chip.classList.add("good"); }
  else if (state === "cancelled") { chip.textContent = "■ đã hủy"; }
  else { chip.textContent = "✕ lỗi — xem nhật ký"; chip.classList.add("bad"); }
}

async function refreshStatus() {
  let status;
  try {
    status = await getJSON("/api/status");
  } catch (_) { return; }
  if (status.data) {
    $("#tile-close").textContent = nf.format(status.data.last_close);
    $("#tile-date").textContent = `Phiên ${status.data.end_date} · ${nf.format(status.data.rows)} phiên lịch sử`;
    const deltaEl = $("#tile-delta");
    if (status.data.prev_close) {
      const d = status.data.last_close - status.data.prev_close;
      const dp = d / status.data.prev_close;
      deltaEl.textContent = `${d >= 0 ? "▲" : "▼"} ${nf.format(Math.abs(d))} (${pf.format(Math.abs(dp))}) so với phiên trước`;
      deltaEl.className = "tile-delta " + (d >= 0 ? "up" : "down");
    }
  }
  const hint = $("#incoming-hint");
  if (status.incoming_files?.length) {
    hint.textContent = `Có ${status.incoming_files.length} file chờ trong incoming/: ${status.incoming_files.join(", ")} — bấm “Cập nhật dữ liệu & chạy hôm nay”.`;
  } else if (status.data && status.outlook_as_of && status.outlook_as_of !== status.data.end_date) {
    hint.textContent = `Báo cáo hiện tại tính đến ${status.outlook_as_of}, dữ liệu đã đến ${status.data.end_date} — nên chạy lại báo cáo.`;
  } else {
    hint.textContent = "Xuất file DataPro (toàn bộ lịch sử) vào thư mục incoming/ rồi bấm nút chạy.";
  }
}

async function refreshJobs() {
  let state;
  try {
    state = await getJSON("/api/jobs");
  } catch (_) { return; }
  const job = state.current;
  const running = job && job.state === "running";
  $("#btn-daily").disabled = running;
  $("#btn-retrain").disabled = running;
  $("#btn-cancel").hidden = !running;
  setJobChip(job ? job.state : null);
  if (job) {
    const log = $("#job-log");
    const stick = log.scrollTop + log.clientHeight >= log.scrollHeight - 8;
    log.textContent = state.log || "(chưa có log)";
    if (stick) log.scrollTop = log.scrollHeight;
    if (running) $("#log-details").open = true;
  }
  if (lastJobState === "running" && job && job.state !== "running") {
    await Promise.all([refreshStatus(), loadPrice(), loadOutlook(), loadMC(), loadFigures()]);
  }
  lastJobState = job ? job.state : null;
  clearTimeout(jobPollTimer);
  jobPollTimer = setTimeout(refreshJobs, running ? 2000 : 6000);
}

async function startJob(kind) {
  if (kind === "retrain" && !confirm("Retrain toàn bộ pipeline có thể chạy rất lâu (train + backtest lại). Tiếp tục?")) return;
  try {
    await fetch(`/api/jobs/${kind}`, { method: "POST" }).then(async (r) => {
      if (!r.ok) throw new Error((await r.json()).detail || r.statusText);
    });
  } catch (err) {
    alert(`Không khởi động được tác vụ: ${err.message}`);
  }
  refreshJobs();
}

/* ---------- khởi động ---------- */
function renderAllCharts() { renderPriceChart(); renderMCChart(); }

function initControls() {
  $("#range-row").addEventListener("click", (evt) => {
    const btn = evt.target.closest("button[data-days]");
    if (!btn) return;
    priceDays = Number(btn.dataset.days);
    for (const b of $("#range-row").querySelectorAll("button")) b.classList.toggle("active", b === btn);
    loadPrice();
  });
  $("#horizon-row").addEventListener("click", (evt) => {
    const btn = evt.target.closest("button[data-h]");
    if (!btn) return;
    mcHorizon = Number(btn.dataset.h);
    for (const b of $("#horizon-row").querySelectorAll("button")) b.classList.toggle("active", b === btn);
    loadMC();
  });
  $("#btn-daily").addEventListener("click", () => startJob("daily"));
  $("#btn-retrain").addEventListener("click", () => startJob("retrain"));
  $("#btn-cancel").addEventListener("click", async () => {
    await fetch("/api/jobs/cancel", { method: "POST" });
    refreshJobs();
  });
}

initTheme();
initControls();
refreshStatus();
refreshJobs();
loadPrice();
loadOutlook();
loadMC();
loadFigures();
setInterval(refreshStatus, 15000);

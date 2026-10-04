/* EliteBot — client dashboard */
"use strict";

const $ = (id) => document.getElementById(id);
const fmt = (v, d = 2) =>
  v === null || v === undefined || isNaN(v) ? "—" : Number(v).toLocaleString("fr-FR", { minimumFractionDigits: d, maximumFractionDigits: d });
const cls = (v) => v > 0 ? "pos" : v < 0 ? "neg" : "";

let lastState = null;

/* ------------------------------------------------------------------ API --- */
async function getState() {
  const r = await fetch("/api/state", { cache: "no-store" });
  if (!r.ok) throw new Error("HTTP " + r.status);
  return r.json();
}
async function post(url, body) {
  const r = await fetch(url, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body || {}),
  });
  return r.json().catch(() => ({}));
}

/* ---------------------------------------------------------------- panic --- */
let panicArmed = false;
$("btn-panic").addEventListener("click", async () => {
  if (!panicArmed) {
    panicArmed = true;
    $("btn-panic").textContent = "⚠ CONFIRMER LA LIQUIDATION ?";
    setTimeout(() => { panicArmed = false; $("btn-panic").textContent = "⏻ PANIC — ARRÊT D'URGENCE"; }, 4000);
    return;
  }
  panicArmed = false;
  $("btn-panic").textContent = "LIQUIDATION…";
  await post("/api/panic");
  setTimeout(() => { $("btn-panic").textContent = "⏻ PANIC — ARRÊT D'URGENCE"; refresh(); }, 1200);
});

/* --------------------------------------------------------------- toggles --- */
async function sendBot(enabled) { await post("/api/bot/toggle", { enabled }); refresh(); }
async function sendFilters(patch) { await post("/api/filters", patch); refresh(); }

$("tg-bot").addEventListener("change", (e) => sendBot(e.target.checked));
$("tg-news").addEventListener("change", (e) => sendFilters({ news: e.target.checked }));
$("tg-vol").addEventListener("change", (e) => sendFilters({ volatility: e.target.checked }));
$("tg-time").addEventListener("change", (e) => sendFilters({ time: e.target.checked }));
$("btn-reset-breaker").addEventListener("click", async () => { await post("/api/breaker/reset"); refresh(); });

/* ----------------------------------------------------------------- chart --- */
function drawEquityChart(canvas, points) {
  const dpr = window.devicePixelRatio || 1;
  const w = canvas.clientWidth, h = canvas.clientHeight;
  canvas.width = w * dpr; canvas.height = h * dpr;
  const ctx = canvas.getContext("2d");
  ctx.scale(dpr, dpr);
  ctx.clearRect(0, 0, w, h);
  if (!points || points.length < 2) {
    ctx.fillStyle = "#9ca3af"; ctx.font = "13px sans-serif";
    ctx.fillText("Collecte des données en cours…", 12, h / 2);
    return;
  }
  const vals = points.map((p) => p[1]);
  let min = Math.min(...vals), max = Math.max(...vals);
  const pad = (max - min) * 0.15 || 10;
  min -= pad; max += pad;
  const x = (i) => (i / (points.length - 1)) * (w - 10) + 5;
  const y = (v) => h - 8 - ((v - min) / (max - min)) * (h - 20);

  // grille
  ctx.strokeStyle = "#1f2937"; ctx.lineWidth = 1;
  for (let i = 0; i <= 4; i++) {
    const gy = 8 + (i / 4) * (h - 20);
    ctx.beginPath(); ctx.moveTo(0, gy); ctx.lineTo(w, gy); ctx.stroke();
  }
  // remplissage
  const grad = ctx.createLinearGradient(0, 0, 0, h);
  grad.addColorStop(0, "rgba(56,189,248,.25)");
  grad.addColorStop(1, "rgba(56,189,248,0)");
  ctx.beginPath();
  points.forEach((p, i) => (i ? ctx.lineTo(x(i), y(p[1])) : ctx.moveTo(x(0), y(p[1]))));
  ctx.lineTo(x(points.length - 1), h); ctx.lineTo(x(0), h); ctx.closePath();
  ctx.fillStyle = grad; ctx.fill();
  // ligne
  ctx.beginPath();
  points.forEach((p, i) => (i ? ctx.lineTo(x(i), y(p[1])) : ctx.moveTo(x(0), y(p[1]))));
  ctx.strokeStyle = "#38bdf8"; ctx.lineWidth = 2; ctx.stroke();
  // dernier point
  const lastP = points[points.length - 1];
  ctx.beginPath(); ctx.arc(x(points.length - 1), y(lastP[1]), 3.5, 0, Math.PI * 2);
  ctx.fillStyle = "#38bdf8"; ctx.fill();
}

/* ------------------------------------------------------------------ rendu --- */
function pill(el, text, state) { el.textContent = text; el.className = "pill " + (state || ""); }

function render(s) {
  lastState = s;
  const acc = s.account, daily = s.daily, stats = s.stats;

  $("kpi-balance").textContent = fmt(acc.balance) + " " + (acc.currency || "");
  $("kpi-equity").textContent = fmt(acc.equity) + " " + (acc.currency || "");
  const fl = acc.floating;
  const flEl = $("kpi-floating");
  flEl.textContent = (fl > 0 ? "+" : "") + fmt(fl);
  flEl.className = "kpi-value " + cls(fl);

  const dd = daily.drawdown_pct || 0;
  const ddEl = $("kpi-dd");
  ddEl.textContent = fmt(dd) + " %";
  ddEl.className = "kpi-value " + (dd >= 3 ? "neg" : "");
  const fill = $("dd-fill");
  fill.style.width = Math.min(100, (dd / 3) * 100) + "%";
  fill.style.background = dd >= 3 ? "#ef4444" : dd >= 2 ? "#f59e0b" : "#22c55e";

  $("kpi-price").textContent = fmt(s.price, 2);
  $("kpi-spread").textContent = "spread " + fmt(s.spread, 2) + " $";
  $("kpi-trades").textContent = stats.trades_today;
  $("kpi-wl").textContent = `W/L ${stats.wins}/${stats.losses} · ouverts ${stats.open_count}`;

  pill($("pill-mode"), s.mode === "live" ? "MT5 LIVE" : "SIMULATION", s.mode === "live" ? "warn" : "ok");
  pill($("pill-conn"), s.broker_connected ? "Broker connecté" : "Broker déconnecté", s.broker_connected ? "ok" : "bad");
  pill($("pill-bot"), s.bot_enabled ? "Robot ON" : "Robot OFF", s.bot_enabled ? "ok" : "bad");
  pill($("pill-breaker"), s.breaker.tripped ? "BREAKER " + (s.breaker.reason || "") : "Breaker OK",
       s.breaker.tripped ? "bad" : "ok");

  $("conn-info").textContent = `${acc.login} · ${acc.server} · ${new Date(s.server_time * 1000).toLocaleTimeString("fr-FR")}`;
  $("ver").textContent = s.version || "";

  // toggles (sans reboucler sur les handlers)
  setToggle("tg-bot", "lbl-bot", s.bot_enabled);
  setToggle("tg-news", "lbl-news", s.filters.news);
  setToggle("tg-vol", "lbl-vol", s.filters.volatility);
  setToggle("tg-time", "lbl-time", s.filters.time);

  // positions
  const tb = $("positions-table").querySelector("tbody");
  tb.innerHTML = "";
  (s.positions || []).forEach((p) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `<td>${p.ticket}</td>
      <td class="${p.type === "buy" ? "pos" : "neg"}">${p.type === "buy" ? "▲ BUY" : "▼ SELL"}</td>
      <td>${p.volume}</td><td>${fmt(p.open_price)}</td><td>${fmt(p.current_price)}</td>
      <td>${fmt(p.sl)}</td><td>${fmt(p.tp)}</td>
      <td class="${cls(p.profit)}">${(p.profit > 0 ? "+" : "") + fmt(p.profit)}</td>`;
    tb.appendChild(tr);
  });
  $("no-positions").style.display = (s.positions || []).length ? "none" : "block";

  // logs
  const ul = $("log-list");
  ul.innerHTML = "";
  (s.trade_log || []).slice(0, 40).forEach((e) => {
    const li = document.createElement("li");
    const t = new Date(e.ts * 1000).toLocaleTimeString("fr-FR");
    li.innerHTML = `<span class="t">${t}</span><span class="k-${e.kind}">${e.message}</span>`;
    ul.appendChild(li);
  });

  // news
  const nl = $("news-list");
  nl.innerHTML = "";
  const upcoming = s.upcoming_news || [];
  if (!upcoming.length) {
    nl.innerHTML = `<li>${s.news_status || "Aucune news à venir."}</li>`;
  } else {
    upcoming.forEach((n) => {
      const li = document.createElement("li");
      const dt = new Date(n.time * 1000).toLocaleString("fr-FR", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });
      li.innerHTML = `<b>${n.currency}</b> ${dt} — ${n.title}`;
      nl.appendChild(li);
    });
  }

  // diagnostics
  const d = s.diagnostics || {};
  const items = [
    ["Tendance H1 (EMA200)", d.trend === "up" ? "▲ HAUSSIÈRE" : d.trend === "down" ? "▼ BAISSIÈRE" : "— NEUTRE"],
    ["EMA200 H1", fmt(d.ema200_h1)],
    ["RSI (14, M5)", fmt(d.rsi, 1)],
    ["ATR (14, M5)", fmt(d.atr, 3)],
    ["BB sup. / inf.", d.bb ? `${fmt(d.bb.upper)} / ${fmt(d.bb.lower)}` : "—"],
    ["Dernière bougie", d.last_bar ? String(d.last_bar).replace("T", " ").slice(0, 16) : "—"],
    ["Cooldown", d.cooldown_left > 0 ? d.cooldown_left + " bougies" : "prêt"],
    ["Verdict", d.verdict || "—"],
  ];
  const dg = $("diag-grid");
  dg.innerHTML = "";
  items.forEach(([l, v]) => {
    const div = document.createElement("div");
    div.className = "diag-item";
    div.innerHTML = `<div class="l">${l}</div><div class="v">${v}</div>`;
    dg.appendChild(div);
  });

  drawEquityChart($("equity-chart"), s.equity_curve);
}

function setToggle(tgId, lblId, on) {
  const tg = $(tgId);
  if (tg.checked !== !!on) tg.checked = !!on;
  $(lblId).textContent = on ? "ON" : "OFF";
}

/* ------------------------------------------------------------------ loop --- */
let errored = false;
async function refresh() {
  try {
    const s = await getState();
    render(s);
    errored = false;
  } catch (e) {
    if (!errored) { errored = true; console.warn("State fetch failed:", e); }
  }
}
refresh();
setInterval(refresh, 2000);
window.addEventListener("resize", () => { if (lastState) drawEquityChart($("equity-chart"), lastState.equity_curve); });

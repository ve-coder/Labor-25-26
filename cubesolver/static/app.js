// Oberfläche: WebSocket-Live-Daten, Steuerung, Handbetrieb, Statistik, Einstellungen.
import { Cube3D } from "./cube3d.js";

const $ = (s) => document.querySelector(s);
const $$ = (s) => [...document.querySelectorAll(s)];
const COLOR_HEX = { W: "#f4f4f0", Y: "#f2d230", R: "#c8312c", O: "#ee7d22", G: "#2f9e4a", B: "#1f5fc4" };
const COLOR_NAME = { W: "Weiß", Y: "Gelb", R: "Rot", O: "Orange", G: "Grün", B: "Blau" };
const SIDES = ["U", "D", "L", "R", "F", "B"];
const MOTOR_NO = { L: 1, R: 2, U: 3, D: 4, F: 5, B: 6 };
const CYLS = [["U", "U", ["U"]], ["D", "D (hebt Würfel)", ["D"]], ["LR", "L + R", ["L", "R"]], ["FB", "F + B", ["F", "B"]]];

let state = {};
let settings = [];
let solution = [];

// ------------------------------------------------------------------ API
async function api(path, method = "GET", body) {
  const r = await fetch(path, {
    method,
    headers: body ? { "Content-Type": "application/json" } : {},
    body: body ? JSON.stringify(body) : undefined,
  });
  let data = null;
  try { data = await r.json(); } catch { /* leer */ }
  if (!r.ok) throw new Error((data && data.detail) || r.statusText);
  return data;
}

function toast(text, err = false) {
  const t = $("#toast");
  t.textContent = text;
  t.className = "toast" + (err ? " err" : "");
  t.hidden = false;
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => (t.hidden = true), err ? 6000 : 2500);
}

async function act(fn) {
  try { return await fn(); } catch (e) { toast(e.message, true); }
}

// ------------------------------------------------------------------ 3D-Würfel
const cube = new Cube3D($("#cube3d"), { onStickerClick: openPalette });
$("#resetView").onclick = () => cube.resetView();

function openPalette({ face, index }, x, y) {
  const p = $("#palette");
  p.innerHTML = `<div class="title">Feld ${face}${index + 1} korrigieren</div>`;
  for (const [c, hex] of Object.entries(COLOR_HEX)) {
    const b = document.createElement("button");
    b.style.background = hex;
    b.title = COLOR_NAME[c];
    b.setAttribute("aria-label", COLOR_NAME[c]);
    b.onclick = () => { p.hidden = true; act(() => api("/api/cube/sticker", "POST", { face, index, color: c })); };
    p.appendChild(b);
  }
  p.style.left = Math.min(x, window.innerWidth - 140) + "px";
  p.style.top = Math.min(y, window.innerHeight - 140) + "px";
  p.hidden = false;
}
document.addEventListener("pointerdown", (e) => {
  const p = $("#palette");
  if (!p.hidden && !p.contains(e.target) && e.target.tagName !== "CANVAS") p.hidden = true;
});

// ------------------------------------------------------------------ WebSocket
function connect() {
  const ws = new WebSocket((location.protocol === "https:" ? "wss://" : "ws://") + location.host + "/ws");
  ws.onopen = () => { $("#conn").classList.add("on"); };
  ws.onclose = () => { $("#conn").classList.remove("on"); setTimeout(connect, 1500); };
  ws.onmessage = (m) => handle(JSON.parse(m.data));
}

function handle(ev) {
  switch (ev.type) {
    case "state": renderState(ev); break;
    case "cube":
      cube.setState(ev.facelets);
      break;
    case "anim": cube.animate(ev); break;
    case "block": CubeBlocks.highlight(ev.id); break;
    case "solution": solution = ev.text ? ev.text.split(" ") : []; renderMoves(0); break;
    case "move_index": renderMoves(ev.index); break;
    case "log": addLog(ev); break;
    case "loghistory": $("#logList").innerHTML = ""; ev.lines.forEach(addLog); break;
    case "stats": loadStats(); break;
  }
}

// ------------------------------------------------------------------ Zustand
const STATUS_CLASS = { "läuft": "run", "wartet": "warn", "fehler": "err", "gestoppt": "warn", "fertig": "ok", "bereit": "" };

function renderState(s) {
  state = s;
  const pill = $("#statusPill");
  pill.textContent = s.status;
  pill.className = "pill " + (STATUS_CLASS[s.status] || "");
  $("#stepLabel").textContent = s.step || "";
  const mb = $("#modeBadge");
  mb.textContent = s.mode === "sim" ? "Simulation" : "Raspberry Pi";
  mb.className = "badge " + s.mode;
  $("#simBox").hidden = s.mode !== "sim";
  $("#programName").textContent = s.program ? "Programm: " + s.program : "";
  $("#btnStart").disabled = s.running;
  $("#btnHome").disabled = s.running;
  $("#btnNext").disabled = !(s.running && s.step_mode);
  $("#stepMode").checked = s.step_mode;
  $("#interlocks").checked = s.interlocks;
  const eb = $("#errorBox");
  eb.hidden = !(s.status === "fehler" && s.error);
  eb.textContent = s.error || "";
  $("#scanInfo").textContent = `${s.scanned}/54 Felder gescannt`;
  const cam = s.camera || {};
  const co = $("#camOk");
  co.textContent = cam.error ? "Kamerafehler" : `${cam.ok}/9${cam.stable ? " erkannt" : ""}`;
  co.className = "pill " + (cam.error ? "err" : cam.stable ? "ok" : "");
  if (s.solution !== solution.join(" ")) solution = s.solution ? s.solution.split(" ") : [];
  renderMoves(s.solution_index);
  renderManual(s.hw);
}

function renderMoves(index) {
  const el = $("#moves");
  const html = solution.map((m, i) => `<span class="${i < index ? "done" : i === index && state.running ? "now" : ""}">${m}</span>`).join("");
  if (el.dataset.html !== html) {
    el.innerHTML = html || '<span class="muted small" style="border:none;background:none">Noch keine Lösung</span>';
    el.dataset.html = html;
  }
}

// ------------------------------------------------------------------ Steuerung
let blocksDirty = false;
$("#btnStart").onclick = () => act(async () => {
  const program = CubeBlocks.toProgram();
  program.name = $("#progSelect").value + (blocksDirty ? " (geändert)" : "");
  await api("/api/run", "POST", { program });
});
$("#btnStop").onclick = () => act(() => api("/api/stop", "POST"));
$("#btnHome").onclick = () => act(() => api("/api/home", "POST"));
$("#btnNext").onclick = () => act(() => api("/api/next", "POST"));
$("#stepMode").onchange = (e) => act(() => api("/api/step_mode", "POST", { on: e.target.checked }));

const speed = $("#speedSolve");
let speedTimer;
speed.oninput = () => {
  $("#speedVal").textContent = speed.value;
  clearTimeout(speedTimer);
  speedTimer = setTimeout(() => act(async () => {
    settings = await api("/api/settings", "PUT", { speed_solve: Number(speed.value) });
    renderSettings();
  }), 250);
};

// ------------------------------------------------------------------ Tabs
$$(".tabs button").forEach((b) => b.onclick = () => {
  $$(".tabs button").forEach((x) => x.classList.toggle("active", x === b));
  $$(".tab").forEach((t) => t.classList.toggle("active", t.id === "tab-" + b.dataset.tab));
  if (b.dataset.tab === "program") CubeBlocks.resize();
  if (b.dataset.tab === "stats") loadStats();
});

// ------------------------------------------------------------------ Programme
CubeBlocks.init($("#blockly"));
CubeBlocks.onChange(() => { blocksDirty = true; });

async function loadProgramList(select) {
  const names = await api("/api/programs");
  const sel = $("#progSelect");
  sel.innerHTML = names.map((n) => `<option>${n}</option>`).join("");
  sel.value = select || localStorageGet("program") || "standard";
  if (!sel.value) sel.value = "standard";
}

async function loadProgram(name) {
  const p = await api("/api/programs/" + encodeURIComponent(name));
  CubeBlocks.load(p);
  blocksDirty = false;
  localStorageSet("program", name);
}

$("#progLoad").onclick = () => act(() => loadProgram($("#progSelect").value));
$("#progSelect").onchange = () => act(() => loadProgram($("#progSelect").value));
$("#progSave").onclick = () => act(async () => {
  const name = $("#progSelect").value;
  if (name === "standard" && !confirm("Das Standardprogramm überschreiben? (Original bleibt in programs/standard.json erhalten)")) return;
  await api("/api/programs/" + encodeURIComponent(name), "PUT", CubeBlocks.toProgram());
  blocksDirty = false;
  toast("Gespeichert");
});
$("#progSaveAs").onclick = () => act(async () => {
  const name = prompt("Name des Programms:");
  if (!name) return;
  await api("/api/programs/" + encodeURIComponent(name), "PUT", CubeBlocks.toProgram());
  await loadProgramList(name);
  localStorageSet("program", name);
  blocksDirty = false;
  toast("Gespeichert als " + name);
});
$("#progDelete").onclick = () => act(async () => {
  const name = $("#progSelect").value;
  if (!confirm(`Programm „${name}“ löschen?`)) return;
  await api("/api/programs/" + encodeURIComponent(name), "DELETE");
  await loadProgramList("standard");
  await loadProgram("standard");
});

function localStorageGet(k) { try { return localStorage.getItem("cs-" + k); } catch { return null; } }
function localStorageSet(k, v) { try { localStorage.setItem("cs-" + k, v); } catch { /* egal */ } }

// ------------------------------------------------------------------ Handbetrieb
function buildManual() {
  $("#cylGrid").innerHTML = CYLS.map(([id, label, sides]) => `
    <div class="cyl" data-cyl="${id}">
      <div class="row"><span class="name">${label}</span><span class="spacer"></span><span class="pill" data-cylstate>–</span></div>
      <div class="reeds">${sides.map((s) => `<span>${s}: <i class="led" data-reed="${s}-in"></i>ein <i class="led" data-reed="${s}-out"></i>aus</span>`).join("")}</div>
      <div class="btn-row" style="margin:0">
        <button data-cylact="1">Ausfahren</button><button data-cylact="0">Einfahren</button>
      </div>
    </div>`).join("");
  $("#motorGrid").innerHTML = SIDES.map((s) => `
    <div class="motor" data-motor="${s}">
      <div class="row"><span class="name">${s}</span><span class="muted small">M${MOTOR_NO[s]}</span><span class="spacer"></span><span class="angle" data-angle>0°</span></div>
      <div class="btns">
        <button data-jog="-90">−90°</button><button data-jog="90">+90°</button><button data-jog="180">180°</button><button data-jog="-180">−180°</button>
        <button data-jogsteps="-10">−10</button><button data-jogsteps="-1">−1</button><button data-jogsteps="1">+1</button><button data-jogsteps="10">+10</button>
      </div>
    </div>`).join("");
  $$("[data-cylact]").forEach((b) => b.onclick = () => act(() =>
    api("/api/manual/cylinder", "POST", { cyl: b.closest("[data-cyl]").dataset.cyl, extended: b.dataset.cylact === "1" })));
  const spq = () => Number((settings.find((x) => x.key === "steps_per_90") || {}).value || 50);
  $$("[data-jog]").forEach((b) => b.onclick = () => act(() =>
    api("/api/manual/jog", "POST", { side: b.closest("[data-motor]").dataset.motor, steps: Number(b.dataset.jog) / 90 * spq() })));
  $$("[data-jogsteps]").forEach((b) => {
    b.title = "Feinjustage in Schritten (nur mit eingefahrenem Greifer)";
    b.onclick = () => act(() => api("/api/manual/jog", "POST", { side: b.closest("[data-motor]").dataset.motor, steps: Number(b.dataset.jogsteps) }));
  });
  $$("[data-pair]").forEach((b) => b.onclick = () => act(() => api("/api/manual/pair", "POST", { angle: Number(b.dataset.pair) })));
  $$("[data-beep]").forEach((b) => b.onclick = () => act(() => api("/api/manual/beep", "POST", { pattern: b.dataset.beep })));
  $("#interlocks").onchange = (e) => act(async () => {
    if (!e.target.checked && !confirm("Sicherheitsprüfungen wirklich abschalten? Nur zum Einrichten ohne Würfel!")) { e.target.checked = true; return; }
    await api("/api/manual/interlocks", "POST", { on: e.target.checked });
  });
  $("#modelReset").onclick = () => act(() => api("/api/cube/reset", "POST"));
  $("#modelSolve").onclick = () => act(async () => { const r = await api("/api/cube/solve_preview", "POST"); toast("Lösung: " + (r.text || "schon gelöst")); });
  $("#simInsert").onclick = () => act(async () => { const r = await api("/api/sim/insert", "POST"); toast("Neuer Würfel: " + r.scramble); });
  $("#simRemove").onclick = () => act(() => api("/api/sim/remove", "POST"));
}

function renderManual(hw) {
  if (!hw) return;
  const manualLocked = state.running;
  $$("#tab-manual button").forEach((b) => { if (!b.dataset.beep) b.disabled = manualLocked; });
  for (const [id, , sides] of CYLS) {
    const card = $(`[data-cyl="${id}"]`);
    const target = hw.cylinders[id];
    const atOut = sides.every((s) => hw.reeds[s].out), atIn = sides.every((s) => hw.reeds[s].in);
    const pill = card.querySelector("[data-cylstate]");
    pill.textContent = atOut ? "ausgefahren" : atIn ? "eingefahren" : target ? "fährt aus …" : "fährt ein …";
    pill.className = "pill " + (atOut ? "ok" : atIn ? "" : "warn");
  }
  for (const s of SIDES) {
    $(`[data-reed="${s}-in"]`).classList.toggle("on", !!hw.reeds[s].in);
    $(`[data-reed="${s}-out"]`).classList.toggle("on", !!hw.reeds[s].out);
    const m = $(`[data-motor="${s}"]`);
    const a = m.querySelector("[data-angle]");
    a.textContent = `${Math.round(hw.motors[s])}°`;
    a.classList.toggle("busy", hw.busy.includes(s));
  }
  $("#lightBarrier").textContent = hw.light_barrier ? "Würfel erkannt" : "frei";
}

// ------------------------------------------------------------------ Statistik
function fmt(v, unit = "") { return v === null || v === undefined ? "–" : `${String(v).replace(".", ",")}${unit}`; }

async function loadStats() {
  const s = await api("/api/stats");
  const k = [
    ["Durchläufe", s.total],
    ["Erfolgsquote", s.success_rate === null ? "–" : s.success_rate + " %"],
    ["Ø Gesamtzeit", fmt(s.avg_total_s, " s")],
    ["Bestzeit", fmt(s.best_total_s, " s")],
    ["Ø Scanzeit", fmt(s.avg_scan_s, " s")],
    ["Ø Lösezeit", fmt(s.avg_solve_s, " s")],
    ["Ø Züge", fmt(s.avg_moves)],
    ["Wenigste Züge", fmt(s.best_moves)],
  ];
  $("#kpis").innerHTML = k.map(([l, v]) => `<div class="kpi"><div class="v">${v}</div><div class="l">${l}</div></div>`).join("");
  const rows = s.last.map((r) => `<tr>
    <td>${new Date(r.time * 1000).toLocaleString("de-AT", { dateStyle: "short", timeStyle: "medium" })}</td>
    <td>${r.program || "–"}${r.mode === "sim" ? ' <span class="muted small">(Sim)</span>' : ""}</td>
    <td class="${r.ok ? "ok-txt" : "err-txt"}">${r.ok ? "gelöst" : escapeHtml(r.error || "abgebrochen")}</td>
    <td class="num">${fmt(r.total_s, " s")}</td><td class="num">${fmt(r.scan_s, " s")}</td>
    <td class="num">${fmt(r.solve_s, " s")}</td><td class="num">${fmt(r.moves)}</td></tr>`).join("");
  $("#statsTable").innerHTML = `<thead><tr><th>Zeit</th><th>Programm</th><th>Ergebnis</th><th class="num">Gesamt</th><th class="num">Scan</th><th class="num">Lösen</th><th class="num">Züge</th></tr></thead><tbody>${rows || '<tr><td colspan="7" class="muted">Noch keine Durchläufe</td></tr>'}</tbody>`;
  const errs = Object.entries(s.errors);
  $("#statsErrors").innerHTML = errs.length ? `<h3>Häufigste Fehler</h3>` + errs.sort((a, b) => b[1] - a[1]).map(([e, n]) => `<div class="kv"><span>${escapeHtml(e)}</span><b>${n}×</b></div>`).join("") : "";
}
$("#statsClear").onclick = () => act(async () => { if (confirm("Statistik löschen?")) { await api("/api/stats", "DELETE"); loadStats(); } });

function escapeHtml(t) { return String(t).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c])); }

// ------------------------------------------------------------------ Einstellungen
async function loadSettings() {
  settings = await api("/api/settings");
  renderSettings();
}

function renderSettings() {
  const groups = {};
  for (const s of settings) (groups[s.group] ||= []).push(s);
  $("#settingsForm").innerHTML = Object.entries(groups).map(([g, items]) => `
    <fieldset><legend>${g}</legend>${items.map(settingRow).join("")}</fieldset>`).join("");
  $$("#settingsForm [name]").forEach((el) => el.addEventListener("input", () => {
    const item = settings.find((x) => x.key === el.name);
    el.closest(".setting").classList.toggle("changed", String(readInput(el)) !== String(item.value));
  }));
  const sp = settings.find((x) => x.key === "speed_solve");
  if (sp && document.activeElement !== speed) {
    speed.max = Math.max(3000, sp.value);
    speed.value = sp.value;
    $("#speedVal").textContent = sp.value;
  }
}

function settingRow(s) {
  const id = "set-" + s.key;
  let input;
  if (s.type === "bool") input = `<label class="switch"><input type="checkbox" id="${id}" name="${s.key}" ${s.value ? "checked" : ""}><span></span></label>`;
  else if (s.type === "choice") input = `<select id="${id}" name="${s.key}">${Object.entries(s.choices).map(([v, l]) => `<option value="${v}" ${String(s.value) === v ? "selected" : ""}>${l}</option>`).join("")}</select>`;
  else if (s.type === "str") input = `<input type="text" id="${id}" name="${s.key}" value="${escapeHtml(s.value)}">`;
  else input = `<span style="display:flex;align-items:center"><input type="number" id="${id}" name="${s.key}" value="${s.value}" ${s.min !== undefined ? `min="${s.min}"` : ""} ${s.max !== undefined ? `max="${s.max}"` : ""} step="${s.type === "float" ? "any" : 1}">${s.unit ? `<span class="unit">${s.unit}</span>` : ""}</span>`;
  return `<div class="setting"><label for="${id}">${s.label}${s.restart ? ' <span class="muted" title="wirkt nach Neustart">↻</span>' : ""}</label>${input}${s.hint ? `<div class="hint">${s.hint}</div>` : ""}</div>`;
}

function readInput(el) {
  if (el.type === "checkbox") return el.checked;
  if (el.type === "number") return Number(el.value);
  return el.value;
}

$("#settingsSave").onclick = () => act(async () => {
  const changes = {};
  for (const el of $$("#settingsForm [name]")) {
    const item = settings.find((x) => x.key === el.name);
    const v = readInput(el);
    if (String(v) !== String(item.value)) changes[el.name] = v;
  }
  if (!Object.keys(changes).length) { toast("Keine Änderungen"); return; }
  settings = await api("/api/settings", "PUT", changes);
  renderSettings();
  const restart = Object.keys(changes).some((k) => settings.find((x) => x.key === k).restart);
  toast(restart ? "Gespeichert – einige Werte wirken erst nach Neustart des Servers" : "Gespeichert");
});
$("#settingsRevert").onclick = () => renderSettings();

// ------------------------------------------------------------------ Log
function addLog(l) {
  const list = $("#logList");
  const d = document.createElement("div");
  d.innerHTML = `<span class="t">${new Date(l.t * 1000).toLocaleTimeString("de-AT")}</span><span class="${l.level}">${escapeHtml(l.text)}</span>`;
  list.prepend(d);
  while (list.children.length > 300) list.lastChild.remove();
}

// ------------------------------------------------------------------ Start
(async function init() {
  buildManual();
  await act(loadSettings);
  await act(async () => { await loadProgramList(); await loadProgram($("#progSelect").value); });
  const st = await act(() => api("/api/state"));
  if (st && st.startup_error) { const b = $("#banner"); b.textContent = st.startup_error; b.hidden = false; }
  connect();
})();

"use strict";

/* ==========================================================================
   CEI Labs Agent — single-page UI (design pass).
   Vanilla JS, no dependencies. Talks to the FastAPI endpoints in server.py
   and streams SSE for /api/pull and /api/chat. The API contract (request /
   response shapes and the /api/chat event taxonomy) is unchanged from the
   functional baseline — only the presentation is new.
   ========================================================================== */

/* ------------------------------- helpers -------------------------------- */

const $ = (id) => document.getElementById(id);
const REDUCED = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

const TIER_ORDER = ["featherweight", "default", "default-alt", "heavyweight", "max", "experimental"];
const TIER_LABELS = {
  featherweight: "Featherweight",
  default: "Default",
  "default-alt": "Default \u00b7 alternative",
  heavyweight: "Heavyweight",
  max: "Max",
  experimental: "Experimental",
};

async function getJSON(url) {
  const res = await fetch(url, { headers: { Accept: "application/json" } });
  if (!res.ok) throw new Error(`${url} -> HTTP ${res.status}`);
  return res.json();
}

async function postJSON(url, body) {
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify(body ?? {}),
  });
  if (!res.ok) throw new Error(`${url} -> HTTP ${res.status}`);
  return res.json();
}

/** Open a POST SSE stream and invoke onEvent for each parsed "data:" payload. */
async function streamSSE(url, body, onEvent) {
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
    body: JSON.stringify(body ?? {}),
  });
  if (!res.ok || !res.body) throw new Error(`${url} -> HTTP ${res.status}`);

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    let sep;
    while ((sep = buffer.indexOf("\n\n")) !== -1) {
      const block = buffer.slice(0, sep);
      buffer = buffer.slice(sep + 2);
      for (const line of block.split("\n")) {
        const trimmed = line.replace(/^data:\s?/, "");
        if (!trimmed || trimmed === line) continue;
        try { onEvent(JSON.parse(trimmed)); } catch (_e) { /* ignore malformed fragment */ }
      }
    }
  }
}

let toastTimer = null;
function toast(message, kind) {
  const el = $("toast");
  el.textContent = message;
  el.className = "toast" + (kind ? ` toast--${kind}` : "");
  el.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { el.hidden = true; }, 3800);
}

/** Small inline SVG icons (decorative). */
const SVG = "http://www.w3.org/2000/svg";
function svg(paths, size) {
  const s = document.createElementNS(SVG, "svg");
  s.setAttribute("width", size || 13); s.setAttribute("height", size || 13);
  s.setAttribute("viewBox", "0 0 24 24"); s.setAttribute("fill", "none");
  s.setAttribute("stroke", "currentColor"); s.setAttribute("stroke-width", "2.2");
  s.setAttribute("stroke-linecap", "round"); s.setAttribute("stroke-linejoin", "round");
  for (const d of paths) { const p = document.createElementNS(SVG, "path"); p.setAttribute("d", d); s.appendChild(p); }
  return s;
}
function icon(kind) {
  switch (kind) {
    case "user": { const s = svg(["M4 21c0-4 4-6 8-6s8 2 8 6"]); const c = document.createElementNS(SVG, "circle"); c.setAttribute("cx", 12); c.setAttribute("cy", 8); c.setAttribute("r", 4); s.insertBefore(c, s.firstChild); return s; }
    case "assistant": { const sp = document.createElement("span"); sp.style.fontFamily = "var(--font-mono)"; sp.style.fontWeight = "500"; sp.textContent = "\u203A_"; return sp; }
    case "ssh_exec": { const s = svg(["M7 9l3 3-3 3", "M13 15h4"]); const r = document.createElementNS(SVG, "rect"); r.setAttribute("x", 3); r.setAttribute("y", 4); r.setAttribute("width", 18); r.setAttribute("height", 16); r.setAttribute("rx", 2); r.setAttribute("opacity", ".35"); s.insertBefore(r, s.firstChild); return s; }
    case "notes": return svg(["M5 3h10l4 4v14H5z", "M9 12h6M9 16h6M9 8h3"]);
    case "final": return svg(["M12 3l2.5 5.5L20 9l-4 4 1 6-5-3-5 3 1-6-4-4 5.5-.5z"], 14);
    case "invalid": return svg(["M10.3 3.9L2.4 18a2 2 0 0 0 1.7 3h15.8a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z", "M12 9v4M12 17h.01"]);
    case "error": { const s = svg(["M15 9l-6 6M9 9l6 6"]); const c = document.createElementNS(SVG, "circle"); c.setAttribute("cx", 12); c.setAttribute("cy", 12); c.setAttribute("r", 9); s.insertBefore(c, s.firstChild); return s; }
    default: return svg([]);
  }
}

/* ------------------------------- state ---------------------------------- */

const state = {
  system: null,
  models: [],
  recommended: null,
  config: null,
  selectedTag: null,
  selectedPreset: null,
  chatBusy: false,
  installBusy: false,
  lastMessage: null,
};

/* --------------------------- status bar --------------------------------- */

async function loadSystem() {
  try {
    const sys = await getJSON("/api/system");
    state.system = sys;
    renderStatusBar(sys);
  } catch (e) {
    renderStatusBar(null);
  }
}

function renderStatusBar(sys) {
  const dot = $("ollama-dot");
  const text = $("ollama-text");
  const fill = $("ram-fill");
  const value = $("ram-value");
  const meter = $("ram-meter");

  if (!sys) {
    dot.className = "dot dot--unknown";
    text.textContent = "Ollama: unavailable";
    value.textContent = "\u2013";
    fill.style.width = "0%";
    return;
  }

  const total = Number(sys.ram_total_gb) || 0;
  const free = Number(sys.ram_free_gb) || 0;
  const pct = total > 0 ? Math.max(0, Math.min(100, (free / total) * 100)) : 0;
  fill.style.width = pct.toFixed(0) + "%";
  fill.className = "meter__fill" + (free < 2.4 ? " meter__fill--danger" : free < 4.2 ? " meter__fill--warn" : "");
  value.textContent = `${free.toFixed(1)} / ${total.toFixed(1)} GB`;
  meter.setAttribute("aria-label", `RAM: ${free.toFixed(1)} of ${total.toFixed(1)} gigabytes free`);

  if (sys.ollama_up) {
    dot.className = "dot dot--up";
    text.textContent = "Ollama: online";
  } else {
    dot.className = "dot dot--down";
    text.textContent = "Ollama: offline";
  }
  applyOllamaGate(sys.ollama_up);
}

/** Disable the composer with a friendly nudge while Ollama is down. */
function applyOllamaGate(up) {
  const send = $("send-btn");
  const input = $("chat-input");
  const nudge = $("composer-nudge");
  if (up) {
    send.disabled = state.chatBusy;
    input.disabled = false;
    nudge.hidden = true;
  } else {
    send.disabled = true;
    input.disabled = false;
    nudge.hidden = false;
    $("composer-nudge-text").textContent = "Start Ollama to chat \u2014 everything runs locally on your laptop.";
  }
}

/* ---------------------------- model catalog ----------------------------- */

async function loadModels() {
  try {
    const data = await getJSON("/api/models");
    state.models = Array.isArray(data.models) ? data.models : [];
    state.recommended = data.recommended || null;
    if (!state.selectedTag) {
      state.selectedTag =
        (state.config && state.config.model) ||
        state.recommended ||
        (state.models[0] && state.models[0].tag) || null;
    }
    renderCatalog();
  } catch (e) {
    toast("Could not load model list.", "err");
  }
}

function currentModel() { return state.models.find((m) => m.tag === state.selectedTag) || null; }

function renderCatalog() {
  const root = $("model-catalog");
  root.innerHTML = "";

  const byTier = new Map();
  const sorted = [...state.models].sort((a, b) => TIER_ORDER.indexOf(a.tier) - TIER_ORDER.indexOf(b.tier));
  for (const m of sorted) { if (!byTier.has(m.tier)) byTier.set(m.tier, []); byTier.get(m.tier).push(m); }

  for (const [tier, items] of byTier) {
    const group = document.createElement("div");
    const label = document.createElement("div");
    label.className = "tier__label";
    const lbl = document.createElement("span"); lbl.textContent = TIER_LABELS[tier] || tier;
    const rule = document.createElement("span"); rule.className = "tier__rule";
    label.append(lbl, rule);
    group.appendChild(label);

    const cards = document.createElement("div");
    cards.className = "tier__cards";
    for (const m of items) cards.appendChild(modelCard(m));
    group.appendChild(cards);
    root.appendChild(group);
  }
  renderPresets();
}

function modelCard(m) {
  const selected = m.tag === state.selectedTag;
  const card = document.createElement("div");
  card.className = "mcard" + (selected ? " is-selected" : "") + (m.fits ? "" : " is-nofit");
  card.dataset.tag = m.tag;
  card.setAttribute("role", "radio");
  card.setAttribute("aria-checked", selected ? "true" : "false");
  card.tabIndex = 0;

  const top = document.createElement("div"); top.className = "mcard__top";
  const left = document.createElement("div");
  const nameRow = document.createElement("div");
  nameRow.style.display = "flex"; nameRow.style.alignItems = "center"; nameRow.style.gap = "8px"; nameRow.style.flexWrap = "wrap";
  const name = document.createElement("span"); name.className = "mcard__name"; name.textContent = m.display_name;
  nameRow.appendChild(name);
  if (m.recommended) { const b = document.createElement("span"); b.className = "badge badge--rec"; b.textContent = "\u2605 Recommended"; nameRow.appendChild(b); }
  const tag = document.createElement("span"); tag.className = "mcard__tag"; tag.textContent = m.tag;
  left.append(nameRow, tag);
  const radio = document.createElement("span"); radio.className = "mcard__radio";
  top.append(left, radio);
  card.appendChild(top);

  if (m.notes) { const notes = document.createElement("div"); notes.className = "mcard__notes"; notes.textContent = m.notes; card.appendChild(notes); }

  const meta = document.createElement("div"); meta.className = "mcard__meta";
  if (m.installed) { const b = document.createElement("span"); b.className = "badge badge--installed"; b.textContent = "\u2713 Installed"; meta.appendChild(b); }
  if (!m.fits) { const b = document.createElement("span"); b.className = "badge badge--nofit"; b.textContent = `\u26A0 needs ${m.min_ram_gb} GB`; meta.appendChild(b); }
  const line = document.createElement("span");
  line.className = "mcard__metaline";
  line.textContent = `${m.download_gb} GB \u00b7 ${(m.native_max_ctx / 1000).toFixed(0)}K ctx${m.thinking_capable ? " \u00b7 thinking" : ""}`;
  meta.appendChild(line);
  card.appendChild(meta);

  if (!m.installed) {
    const wrap = document.createElement("div"); wrap.className = "mcard__install";
    const btn = document.createElement("button");
    btn.type = "button"; btn.className = "install-btn"; btn.textContent = "\u2193 Install model";
    btn.addEventListener("click", (e) => { e.stopPropagation(); installModel(m.tag, wrap); });
    const prog = document.createElement("div"); prog.className = "progress";
    prog.innerHTML = '<div class="progress__bar"><div class="progress__fill"></div><div class="progress__shimmer"></div></div><p class="progress__text" role="status" aria-live="polite"></p>';
    wrap.append(btn, prog);
    card.appendChild(wrap);
  }

  card.addEventListener("click", () => selectModel(m.tag));
  card.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); selectModel(m.tag); } });
  return card;
}

function selectModel(tag) {
  if (state.selectedTag === tag) return;
  state.selectedTag = tag;
  const m = currentModel();
  state.selectedPreset = (state.config && state.config.model === tag && state.config.preset) || (m && m.default_preset) || (m && m.presets[0] && m.presets[0].name) || null;

  document.querySelectorAll(".mcard").forEach((c) => {
    const on = c.dataset.tag === tag;
    c.classList.toggle("is-selected", on);
    c.setAttribute("aria-checked", on ? "true" : "false");
  });
  renderPresets();
  saveConfig({ model: tag, preset: state.selectedPreset });
}

function renderPresets() {
  const m = currentModel();
  $("preset-model-name").textContent = m ? m.display_name : "\u2014";
  const wrap = $("preset-chips");
  wrap.innerHTML = "";
  if (!m || !Array.isArray(m.presets)) { $("preset-hint").textContent = ""; return; }

  if (!state.selectedPreset || !m.presets.some((p) => p.name === state.selectedPreset)) {
    state.selectedPreset = m.default_preset || (m.presets[0] && m.presets[0].name);
  }

  for (const p of m.presets) {
    const chip = document.createElement("button");
    chip.type = "button";
    chip.className = "chip" + (p.name === state.selectedPreset ? " is-selected" : "") + (p.fits ? "" : " is-nofit");
    chip.setAttribute("role", "radio");
    chip.setAttribute("aria-checked", p.name === state.selectedPreset ? "true" : "false");
    const nm = document.createElement("span"); nm.className = "chip__name"; nm.textContent = p.name;
    const meta = document.createElement("span"); meta.className = "chip__meta"; meta.textContent = `ctx ${(p.num_ctx / 1000).toFixed(0)}K \u00b7 ~${p.est_ram_gb} GB`;
    chip.append(nm, meta);
    chip.addEventListener("click", () => selectPreset(p.name));
    wrap.appendChild(chip);
  }
  updatePresetHint();
}

function selectPreset(name) {
  state.selectedPreset = name;
  document.querySelectorAll("#preset-chips .chip").forEach((c) => {
    const on = c.querySelector(".chip__name").textContent === name;
    c.classList.toggle("is-selected", on);
    c.setAttribute("aria-checked", on ? "true" : "false");
  });
  updatePresetHint();
  saveConfig({ preset: name });
}

function updatePresetHint() {
  const m = currentModel();
  const p = m && m.presets.find((x) => x.name === state.selectedPreset);
  const hint = $("preset-hint");
  if (!p) { hint.textContent = ""; return; }
  hint.textContent =
    `Context ${p.num_ctx.toLocaleString()} tokens, up to ${p.num_predict} output tokens` +
    (p.think ? ", thinking on." : ".") +
    ` Estimated ${p.est_ram_gb} GB RAM` +
    (p.fits ? "." : " \u2014 may not fit your system.");
}

/* --------------------------- install (pull) ----------------------------- */

async function installModel(tag, wrap) {
  if (state.installBusy) return;
  state.installBusy = true;
  const btn = wrap.querySelector(".install-btn");
  const prog = wrap.querySelector(".progress");
  const fill = wrap.querySelector(".progress__fill");
  const text = wrap.querySelector(".progress__text");
  btn.disabled = true;
  prog.classList.add("is-active");
  fill.style.width = "0%";
  text.textContent = "Starting download\u2026";

  try {
    await streamSSE("/api/pull", { tag }, (ev) => {
      if (ev.done) return;
      const status = ev.status || "working";
      if (typeof ev.total === "number" && ev.total > 0 && typeof ev.completed === "number") {
        const pct = Math.max(0, Math.min(100, (ev.completed / ev.total) * 100));
        fill.style.width = pct.toFixed(1) + "%";
        text.textContent = `${status} \u2014 ${pct.toFixed(0)}%`;
      } else {
        text.textContent = status;
        if (/success/i.test(status)) fill.style.width = "100%";
      }
    });

    fill.style.width = "100%";
    text.textContent = "Installed.";
    toast(`${tag} installed.`, "ok");
    await Promise.all([loadSystem(), loadModels()]);
  } catch (e) {
    text.textContent = "Install failed.";
    toast("Model install failed. Is Ollama running?", "err");
  } finally {
    state.installBusy = false;
    btn.disabled = false;
    setTimeout(() => prog.classList.remove("is-active"), 1800);
  }
}

/* ------------------------------ config ---------------------------------- */

async function loadConfig() {
  try {
    state.config = await getJSON("/api/config");
    applyConfigToForm(state.config);
  } catch (e) {
    state.config = null;
  }
}

function applyConfigToForm(cfg) {
  if (!cfg) return;
  if (cfg.model && state.models.some((m) => m.tag === cfg.model)) {
    state.selectedTag = cfg.model;
    state.selectedPreset = cfg.preset || null;
    renderCatalog();
  }
  const ssh = cfg.ssh || {};
  if (ssh.host) $("ssh-host").value = ssh.host;
  if (ssh.username) $("ssh-user").value = ssh.username;
  if (ssh.port) $("ssh-port").value = ssh.port;
  // Password is redacted server-side; leave the field blank.
  if (cfg.ssh_configured) {
    $("ssh-status").textContent = "\u2713 Target saved.";
    $("ssh-status").className = "ssh-status ssh-status--ok";
  }
}

async function saveConfig(partial) {
  const clean = {};
  for (const [k, v] of Object.entries(partial)) { if (v !== null && v !== undefined) clean[k] = v; }
  if (Object.keys(clean).length === 0) return;
  try { await postJSON("/api/config", clean); } catch (e) { toast("Could not save settings.", "err"); }
}

/* ------------------------------- SSH ------------------------------------ */

function readSSHForm() {
  return {
    host: $("ssh-host").value.trim(),
    port: parseInt($("ssh-port").value, 10) || 22,
    username: $("ssh-user").value.trim(),
    password: $("ssh-pass").value,
    timeout: 15,
  };
}

async function testAndSaveSSH(evt) {
  evt.preventDefault();
  const btn = $("ssh-test-btn");
  const status = $("ssh-status");
  const cfg = readSSHForm();

  if (!cfg.host || !cfg.username) {
    status.textContent = "Host and username are required.";
    status.className = "ssh-status ssh-status--err";
    return;
  }

  btn.disabled = true;
  status.textContent = "\u2026 Testing connection\u2026";
  status.className = "ssh-status ssh-status--busy";

  try {
    const res = await postJSON("/api/ssh/test", cfg);
    if (res.ok) {
      status.textContent = "\u2713 " + (res.message === "ok" ? "Connected \u2014 target saved." : (res.message || "Connected."));
      status.className = "ssh-status ssh-status--ok";
      await saveConfig({ ssh: cfg });
    } else {
      status.textContent = "\u2715 " + (res.message || "Connection failed.");
      status.className = "ssh-status ssh-status--err";
    }
  } catch (e) {
    status.textContent = "\u2715 Connection test failed.";
    status.className = "ssh-status ssh-status--err";
  } finally {
    btn.disabled = false;
  }
}

/* ------------------------------- chat ----------------------------------- */

function clearEmptyState() { const empty = $("empty-state"); if (empty) empty.remove(); }

function appendMsg(el) {
  clearEmptyState();
  const t = $("transcript");
  t.appendChild(el);
  t.scrollTop = t.scrollHeight;
  return el;
}

function msgShell(kind, roleLabel, iconKind, extraHead) {
  const el = document.createElement("div");
  el.className = `msg msg--${kind}`;
  const head = document.createElement("div"); head.className = "msg__head";
  const ic = document.createElement("span"); ic.className = "msg__icon"; ic.appendChild(icon(iconKind));
  const role = document.createElement("span"); role.className = "msg__role"; role.textContent = roleLabel;
  head.append(ic, role);
  if (extraHead) head.appendChild(extraHead);
  el.appendChild(head);
  return el;
}

function addUserMessage(txt) {
  const el = msgShell("user", "You", "user");
  const body = document.createElement("div"); body.className = "msg__text"; body.textContent = txt;
  el.appendChild(body);
  appendMsg(el);
}

function addAssistantMessage(txt) {
  const el = msgShell("assistant", "Agent", "assistant");
  const body = document.createElement("div"); body.className = "msg__text"; body.textContent = txt;
  el.appendChild(body);
  appendMsg(el);
}

function formatArgs(args) {
  if (!args || typeof args !== "object") return "";
  if (typeof args.command === "string") return "$ " + args.command;
  try {
    return Object.entries(args).map(([k, v]) => `${k}: ${typeof v === "string" ? v : JSON.stringify(v)}`).join("   ");
  } catch (_e) { return JSON.stringify(args); }
}

function addActionMessage(name, args) {
  const iconKind = (name && name.indexOf("note") >= 0) ? "notes" : "ssh_exec";
  const el = msgShell("action", "Action", iconKind);
  const chip = document.createElement("div"); chip.className = "action-chip";
  const nameEl = document.createElement("span"); nameEl.className = "action-chip__name"; nameEl.textContent = name;
  const argsEl = document.createElement("span"); argsEl.className = "action-chip__args"; argsEl.textContent = formatArgs(args);
  chip.append(nameEl, argsEl);
  el.appendChild(chip);
  appendMsg(el);
}

function addObservationMessage(txt) {
  const badge = document.createElement("span"); badge.className = "msg__untrusted"; badge.textContent = "untrusted output";
  const el = msgShell("observation", "Observation", "ssh_exec", badge);
  const pre = document.createElement("pre"); pre.className = "observation__body";
  pre.textContent = txt; // untrusted — TEXT ONLY, never innerHTML
  el.appendChild(pre);
  appendMsg(el);
}

function addFinalMessage(txt) {
  const el = msgShell("final", "You learned this", "final");
  const title = document.createElement("div"); title.className = "final__title"; title.textContent = "Here's how we cracked it \u2014 together";
  const body = document.createElement("div"); body.className = "msg__text"; body.textContent = txt;
  const saved = document.createElement("div"); saved.className = "final__saved"; saved.textContent = "\u2713 Saved to your notes \u00b7 ready for the next level";
  el.append(title, body, saved);
  appendMsg(el);
}

function addInvalidMessage(txt) {
  const el = msgShell("invalid", "Retrying", "invalid");
  const body = document.createElement("div"); body.className = "msg__text"; body.textContent = txt;
  el.appendChild(body);
  appendMsg(el);
}

function addErrorMessage(txt) {
  const el = msgShell("error", "Error", "error");
  const body = document.createElement("div"); body.className = "msg__text"; body.textContent = txt;
  const retry = document.createElement("button"); retry.className = "retry"; retry.type = "button"; retry.textContent = "\u21BB Retry";
  retry.addEventListener("click", () => { if (state.lastMessage) sendMessage(null, state.lastMessage); });
  el.append(body, retry);
  appendMsg(el);
}

function showTyping() {
  hideTyping();
  const el = document.createElement("div");
  el.className = "typing"; el.id = "typing-indicator";
  el.innerHTML = "<span></span><span></span><span></span><span class='typing__label'>the agent is working\u2026</span>";
  appendMsg(el);
}
function hideTyping() { const el = $("typing-indicator"); if (el) el.remove(); }

function handleChatEvent(ev) {
  hideTyping();
  switch (ev.type) {
    case "assistant": if (ev.text && ev.text.trim()) addAssistantMessage(ev.text); break;
    case "action": addActionMessage(ev.name, ev.args); break;
    case "observation": addObservationMessage(ev.text || ""); break;
    case "invalid": addInvalidMessage(ev.reason || "The agent stumbled and is retrying."); break;
    case "final": addFinalMessage(ev.text || ""); break;
    case "error": addErrorMessage(ev.message || "Something went wrong."); break;
    default: break;
  }
}

async function sendMessage(evt, forced) {
  if (evt) evt.preventDefault();
  if (state.chatBusy) return;
  if (state.system && state.system.ollama_up === false) return;

  const input = $("chat-input");
  const message = forced != null ? forced : input.value.trim();
  if (!message) return;
  state.lastMessage = message;

  state.chatBusy = true;
  $("send-btn").disabled = true;
  if (forced == null) { input.value = ""; autoGrow(input); }

  addUserMessage(message);
  showTyping();

  try {
    await streamSSE("/api/chat", { message }, (ev) => { if (ev.done) return; handleChatEvent(ev); });
  } catch (e) {
    hideTyping();
    addErrorMessage("Lost connection to the agent. Is the server running?");
  } finally {
    hideTyping();
    state.chatBusy = false;
    const up = !state.system || state.system.ollama_up !== false;
    $("send-btn").disabled = !up;
    input.focus();
  }
}

/* --------------------------- composer UX -------------------------------- */

function autoGrow(el) {
  el.style.height = "auto";
  el.style.height = Math.min(el.scrollHeight, 180) + "px";
}

/* ------------------------------- init ----------------------------------- */

function wireEvents() {
  $("ssh-form").addEventListener("submit", testAndSaveSSH);
  $("composer").addEventListener("submit", sendMessage);
  $("refresh-btn").addEventListener("click", () => { loadSystem(); loadModels(); });

  const input = $("chat-input");
  input.addEventListener("input", () => autoGrow(input));
  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendMessage(); }
  });
}

async function init() {
  wireEvents();
  await loadSystem();
  await loadModels();
  await loadConfig();
  setInterval(loadSystem, 15000); // live RAM / Ollama telemetry
}

if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
else init();

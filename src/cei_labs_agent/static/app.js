"use strict";

/* ==========================================================================
   CEI Labs Agent — functional baseline single-page UI.
   Vanilla JS, no external dependencies. Talks to the FastAPI endpoints in
   server.py and streams SSE for /api/pull and /api/chat.
   ========================================================================== */

/* ------------------------------- helpers -------------------------------- */

const $ = (id) => document.getElementById(id);

/** Fetch JSON from a GET endpoint. */
async function getJSON(url) {
  const res = await fetch(url, { headers: { Accept: "application/json" } });
  if (!res.ok) throw new Error(`${url} -> HTTP ${res.status}`);
  return res.json();
}

/** POST a JSON body and parse a JSON reply. */
async function postJSON(url, body) {
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify(body ?? {}),
  });
  if (!res.ok) throw new Error(`${url} -> HTTP ${res.status}`);
  return res.json();
}

/**
 * Open a POST SSE stream and invoke onEvent for each parsed "data:" payload.
 * Resolves once the stream closes. Silently ignores non-JSON keepalives.
 */
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
        if (!trimmed || trimmed === line) continue; // not a data line
        try {
          onEvent(JSON.parse(trimmed));
        } catch (_e) {
          /* ignore malformed fragment */
        }
      }
    }
  }
}

/** Show a transient toast message. */
let toastTimer = null;
function toast(message, kind) {
  const el = $("toast");
  el.textContent = message;
  el.className = "toast" + (kind ? ` toast--${kind}` : "");
  el.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { el.hidden = true; }, 3800);
}

/* ------------------------------- state ---------------------------------- */

const state = {
  system: null,      // /api/system payload
  models: [],        // models_view list
  recommended: null, // recommended tag
  config: null,      // /api/config payload
  chatBusy: false,
  installBusy: false,
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

  if (!sys) {
    dot.className = "dot dot--unknown";
    text.textContent = "Ollama: unavailable";
    value.textContent = "–";
    fill.style.width = "0%";
    return;
  }

  const total = Number(sys.ram_total_gb) || 0;
  const free = Number(sys.ram_free_gb) || 0;
  const pct = total > 0 ? Math.max(0, Math.min(100, (free / total) * 100)) : 0;
  fill.style.width = pct.toFixed(0) + "%";
  value.textContent = `${free.toFixed(1)} / ${total.toFixed(1)} GB free`;

  if (sys.ollama_up) {
    dot.className = "dot dot--up";
    text.textContent = "Ollama: online";
  } else {
    dot.className = "dot dot--down";
    text.textContent = "Ollama: offline";
  }
}

/* ---------------------------- model picker ------------------------------ */

async function loadModels() {
  try {
    const data = await getJSON("/api/models");
    state.models = Array.isArray(data.models) ? data.models : [];
    state.recommended = data.recommended || null;
    renderModelSelect();
  } catch (e) {
    toast("Could not load model list.", "err");
  }
}

/** Human label for a model option, with fit / install / recommend markers. */
function modelOptionLabel(m) {
  const parts = [`${m.display_name} (${m.tag})`];
  const badges = [];
  if (m.installed) badges.push("✓ installed");
  if (m.recommended) badges.push("★ recommended");
  if (!m.fits) badges.push(`⚠ needs ${m.min_ram_gb} GB`);
  if (badges.length) parts.push("— " + badges.join(" · "));
  return parts.join(" ");
}

function renderModelSelect() {
  const sel = $("model-select");
  const previous = sel.value;
  sel.innerHTML = "";

  // Group tier-ordered models into optgroups by tier.
  const groups = new Map();
  for (const m of state.models) {
    if (!groups.has(m.tier)) groups.set(m.tier, []);
    groups.get(m.tier).push(m);
  }

  for (const [tier, items] of groups) {
    const og = document.createElement("optgroup");
    og.label = tier;
    for (const m of items) {
      const opt = document.createElement("option");
      opt.value = m.tag;
      opt.textContent = modelOptionLabel(m);
      if (!m.fits) opt.classList.add("opt--nofit");
      og.appendChild(opt);
    }
    sel.appendChild(og);
  }

  // Restore selection: prior choice -> saved config -> recommended -> first.
  const desired =
    previous ||
    (state.config && state.config.model) ||
    state.recommended ||
    (state.models[0] && state.models[0].tag);
  if (desired) sel.value = desired;

  onModelChange(false);
}

function currentModel() {
  const tag = $("model-select").value;
  return state.models.find((m) => m.tag === tag) || null;
}

function onModelChange(persist = true) {
  const m = currentModel();
  const notes = $("model-notes");
  notes.textContent = m ? (m.notes || "") : "";
  renderPresetSelect(m);
  if (persist) {
    saveConfig({ model: m ? m.tag : null, preset: $("preset-select").value });
  }
}

function renderPresetSelect(m) {
  const sel = $("preset-select");
  sel.innerHTML = "";
  if (!m || !Array.isArray(m.presets)) {
    $("preset-hint").textContent = "";
    return;
  }

  for (const p of m.presets) {
    const opt = document.createElement("option");
    opt.value = p.name;
    const fitMark = p.fits ? "" : " — needs more RAM";
    opt.textContent = `${p.name} · ctx ${p.num_ctx} · ~${p.est_ram_gb} GB${fitMark}`;
    if (!p.fits) opt.classList.add("opt--nofit");
    sel.appendChild(opt);
  }

  const desired =
    (state.config && state.config.model === m.tag && state.config.preset) ||
    m.default_preset ||
    (m.presets[0] && m.presets[0].name);
  if (desired) sel.value = desired;

  updatePresetHint(m);
}

function updatePresetHint(m) {
  const p = m && m.presets.find((x) => x.name === $("preset-select").value);
  const hint = $("preset-hint");
  if (!p) { hint.textContent = ""; return; }
  hint.textContent =
    `Context ${p.num_ctx} tokens, up to ${p.num_predict} output tokens` +
    (p.think ? ", thinking on." : ".") +
    ` Estimated ${p.est_ram_gb} GB RAM` +
    (p.fits ? "." : " — may not fit your system.");
}

function onPresetChange() {
  const m = currentModel();
  updatePresetHint(m);
  saveConfig({ preset: $("preset-select").value });
}

/* --------------------------- install (pull) ----------------------------- */

async function installModel() {
  if (state.installBusy) return;
  const m = currentModel();
  if (!m) return;

  state.installBusy = true;
  const btn = $("install-btn");
  btn.disabled = true;
  const wrap = $("install-progress");
  const fill = $("install-fill");
  const text = $("install-text");
  wrap.hidden = false;
  fill.style.width = "0%";
  text.textContent = "Starting download…";

  try {
    await streamSSE("/api/pull", { tag: m.tag }, (ev) => {
      if (ev.done) return;
      const status = ev.status || "working";
      if (typeof ev.total === "number" && ev.total > 0 && typeof ev.completed === "number") {
        const pct = Math.max(0, Math.min(100, (ev.completed / ev.total) * 100));
        fill.style.width = pct.toFixed(1) + "%";
        text.textContent = `${status} — ${pct.toFixed(0)}%`;
      } else {
        text.textContent = status;
        if (/success/i.test(status)) fill.style.width = "100%";
      }
    });

    fill.style.width = "100%";
    text.textContent = "Installed.";
    toast(`${m.tag} installed.`, "ok");
    await Promise.all([loadSystem(), loadModels()]);
  } catch (e) {
    text.textContent = "Install failed.";
    toast("Model install failed. Is Ollama running?", "err");
  } finally {
    state.installBusy = false;
    btn.disabled = false;
    setTimeout(() => { wrap.hidden = true; }, 2500);
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
    $("model-select").value = cfg.model;
    onModelChange(false);
  }
  const ssh = cfg.ssh || {};
  if (ssh.host) $("ssh-host").value = ssh.host;
  if (ssh.username) $("ssh-user").value = ssh.username;
  if (ssh.port) $("ssh-port").value = ssh.port;
  // Password is redacted server-side; leave the field blank.
  if (cfg.ssh_configured) {
    $("ssh-status").textContent = "Target saved.";
    $("ssh-status").className = "ssh-status ssh-status--ok";
  }
}

/** Merge a partial config server-side. Fire-and-forget with error toast. */
async function saveConfig(partial) {
  const clean = {};
  for (const [k, v] of Object.entries(partial)) {
    if (v !== null && v !== undefined) clean[k] = v;
  }
  if (Object.keys(clean).length === 0) return;
  try {
    await postJSON("/api/config", clean);
  } catch (e) {
    toast("Could not save settings.", "err");
  }
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
  status.textContent = "Testing connection…";
  status.className = "ssh-status ssh-status--busy";

  try {
    const res = await postJSON("/api/ssh/test", cfg);
    if (res.ok) {
      status.textContent = res.message || "Connected.";
      status.className = "ssh-status ssh-status--ok";
      await saveConfig({ ssh: cfg });
    } else {
      status.textContent = res.message || "Connection failed.";
      status.className = "ssh-status ssh-status--err";
    }
  } catch (e) {
    status.textContent = "Connection test failed.";
    status.className = "ssh-status ssh-status--err";
  } finally {
    btn.disabled = false;
  }
}

/* ------------------------------- chat ----------------------------------- */

function clearEmptyState() {
  const empty = $("empty-state");
  if (empty) empty.remove();
}

/** Append a message element to the transcript and scroll into view. */
function appendMsg(el) {
  clearEmptyState();
  const t = $("transcript");
  t.appendChild(el);
  t.scrollTop = t.scrollHeight;
  return el;
}

function roleLabelEl(label) {
  const r = document.createElement("div");
  r.className = "msg__role";
  r.textContent = label;
  return r;
}

function addUserMessage(txt) {
  const el = document.createElement("div");
  el.className = "msg msg--user";
  el.appendChild(roleLabelEl("You"));
  const body = document.createElement("div");
  body.className = "msg__text";
  body.textContent = txt;
  el.appendChild(body);
  appendMsg(el);
}

function addAssistantMessage(txt) {
  const el = document.createElement("div");
  el.className = "msg msg--assistant";
  el.appendChild(roleLabelEl("Copilot"));
  const body = document.createElement("div");
  body.className = "msg__text";
  body.textContent = txt;
  el.appendChild(body);
  appendMsg(el);
}

function addActionMessage(name, args) {
  const el = document.createElement("div");
  el.className = "msg msg--action";
  el.appendChild(roleLabelEl("Action"));
  const chip = document.createElement("div");
  chip.className = "action-chip";
  const nameEl = document.createElement("span");
  nameEl.className = "action-chip__name";
  nameEl.textContent = name;
  chip.appendChild(nameEl);
  const argsEl = document.createElement("span");
  argsEl.className = "action-chip__args";
  argsEl.textContent = formatArgs(args);
  chip.appendChild(argsEl);
  el.appendChild(chip);
  appendMsg(el);
}

function formatArgs(args) {
  if (!args || typeof args !== "object") return "";
  if (typeof args.command === "string") return args.command;
  try {
    return Object.entries(args)
      .map(([k, v]) => `${k}: ${typeof v === "string" ? v : JSON.stringify(v)}`)
      .join("  ");
  } catch (_e) {
    return JSON.stringify(args);
  }
}

function addObservationMessage(txt) {
  const el = document.createElement("div");
  el.className = "msg msg--observation";
  el.appendChild(roleLabelEl("Observation"));
  const pre = document.createElement("pre");
  pre.className = "observation__body";
  pre.textContent = txt;
  el.appendChild(pre);
  appendMsg(el);
}

function addFinalMessage(txt) {
  const el = document.createElement("div");
  el.className = "msg msg--final";
  el.appendChild(roleLabelEl("Final answer"));
  const body = document.createElement("div");
  body.className = "msg__text";
  body.textContent = txt;
  el.appendChild(body);
  appendMsg(el);
}

function addNoticeMessage(kind, label, txt) {
  const el = document.createElement("div");
  el.className = `msg msg--${kind}`;
  el.appendChild(roleLabelEl(label));
  const body = document.createElement("div");
  body.className = "msg__text";
  body.textContent = txt;
  el.appendChild(body);
  appendMsg(el);
}

function showTyping() {
  const el = document.createElement("div");
  el.className = "typing";
  el.id = "typing-indicator";
  el.innerHTML = "<span></span><span></span><span></span>";
  appendMsg(el);
}
function hideTyping() {
  const el = $("typing-indicator");
  if (el) el.remove();
}

function handleChatEvent(ev) {
  hideTyping();
  switch (ev.type) {
    case "assistant":
      if (ev.text && ev.text.trim()) addAssistantMessage(ev.text);
      break;
    case "action":
      addActionMessage(ev.name, ev.args);
      break;
    case "observation":
      addObservationMessage(ev.text || "");
      break;
    case "invalid":
      addNoticeMessage("invalid", "Invalid action", ev.reason || "");
      break;
    case "final":
      addFinalMessage(ev.text || "");
      break;
    case "error":
      addNoticeMessage("error", "Error", ev.message || "Something went wrong.");
      break;
    default:
      break;
  }
}

async function sendMessage(evt) {
  if (evt) evt.preventDefault();
  if (state.chatBusy) return;

  const input = $("chat-input");
  const message = input.value.trim();
  if (!message) return;

  state.chatBusy = true;
  $("send-btn").disabled = true;
  input.value = "";
  autoGrow(input);

  addUserMessage(message);
  showTyping();

  try {
    await streamSSE("/api/chat", { message }, (ev) => {
      if (ev.done) return;
      handleChatEvent(ev);
    });
  } catch (e) {
    hideTyping();
    addNoticeMessage("error", "Error", "Lost connection to the agent. Is the server running?");
  } finally {
    hideTyping();
    state.chatBusy = false;
    $("send-btn").disabled = false;
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
  $("model-select").addEventListener("change", () => onModelChange(true));
  $("preset-select").addEventListener("change", onPresetChange);
  $("install-btn").addEventListener("click", installModel);
  $("ssh-form").addEventListener("submit", testAndSaveSSH);
  $("composer").addEventListener("submit", sendMessage);
  $("refresh-btn").addEventListener("click", () => {
    loadSystem();
    loadModels();
  });

  const input = $("chat-input");
  input.addEventListener("input", () => autoGrow(input));
  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  });
}

async function init() {
  wireEvents();
  await loadSystem();
  await loadModels();
  await loadConfig();
  // Periodically refresh live system status (RAM / Ollama).
  setInterval(loadSystem, 15000);
}

document.addEventListener("DOMContentLoaded", init);

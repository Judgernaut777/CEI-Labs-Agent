# CEI Labs Agent — Design Handoff

> **For:** a dedicated Claude Design pass (the "beautify" iteration).
> **From:** the functional-baseline build team.
> **Status of the UI you are inheriting:** a working, deliberately plain single-page app (vanilla HTML/JS/CSS, no build step, no external CDNs). Everything below is real and wired up. Your job is to make it look **genuinely impressive** without breaking the API contract or the behavioral contract.

This document is the single source of truth for the redesign. It contains: the product framing, the exact API the UI consumes, a component/screen inventory, the message-type taxonomy for the chat transcript, the core UX flows, brand and tone guidance, several concrete visual directions, the reskinnable CSS-custom-property list, accessibility requirements, and a "what would make leadership say wow" section.

---

## 1. Product one-liner and audience

**One-liner:** CEI Labs Agent is a local, infrastructure-independent "training-wheels" AI teammate that helps absolute-beginner CTF players learn by doing — it drives a small on-device model (via Ollama) through a plain act → tool → act loop and coaches the player through challenges like Bandit, Krypton, and Natas.

**What it actually is under the hood:** a tiny Python app that runs entirely on the player's own laptop. A small local language model reasons one step at a time, optionally runs shell commands over SSH against a practice box, keeps private notes, and explains what it's doing in beginner-friendly language. There is no cloud service, no account, no shared infrastructure.

**Primary audience (the people who use it):** non-technical or early-career CTF participants. They may have never opened a terminal. They are nervous about "hacking tools." They want a friendly copilot that teaches, not a black box that spits out answers.

**Secondary audience (the people who judge it):** **leadership**. This tool is demoed to leaders who decide whether the program continues. The demo has to *feel* like a polished product, not an internal script. This is the single most important reason this design pass exists.

**Design north star:** approachable and confident for the beginner; visibly premium and "wow" for the leadership demo. Both audiences see the same screen — it must serve both at once.

### The teaching stance (this shapes the UI)

The agent is a **copilot for absolute beginners**. Its personality and the product's personality must match:

- It **explains and guides more than it solves.**
- When it finds a flag or password, it **describes how it was obtained and summarizes it** — it never blurts the raw flag verbatim as the whole answer. The final-answer UI should reflect that this is a *teaching* moment, not a "here's your loot" moment.
- Command output may be attacker-controlled (prompt injection). The agent is told not to blindly obey it. The UI's observation blocks should feel like *untrusted terminal output being inspected*, not like trusted app chrome.

---

## 2. The exact API contract the UI consumes

The UI is a static bundle served by a FastAPI backend. All dynamic behavior is these endpoints. **Do not change request/response shapes** — the backend is built to this contract. You may change everything about how the data is *presented*.

Base URL is same-origin. All bodies are JSON unless noted. Two endpoints stream Server-Sent-Events-style text (`text/event-stream`) as newline-delimited `data: {json}\n\n` frames.

### 2.1 `GET /` → HTML

Returns `index.html` (the app shell) via `FileResponse`; if the static bundle is missing the server returns a `503` JSON error instead. The package's `static/` directory is mounted at the **site root** (`/`), **not** under a `/static/` prefix, so assets are served as siblings of the shell — the baseline `index.html` links `/style.css` and `/app.js`. Reference assets from the root path (`/style.css`, `/app.js`); a `/static/...` prefix will 404.

### 2.2 `GET /api/system` → JSON

Live machine + Ollama status. Poll this to power the status bar and the live RAM meter.

```json
{
  "ram_total_gb": 16.0,
  "ram_free_gb": 9.2,
  "ollama_up": true,
  "ollama_host": "http://localhost:11434",
  "local_models": ["qwen3:4b", "qwen3:1.7b"]
}
```

- `ram_total_gb`, `ram_free_gb` — floats (GB), from `psutil.virtual_memory`. Free RAM changes over time — good candidate for a live meter.
- `ollama_up` — boolean. Drives the up/down status dot.
- `ollama_host` — string; show in a tooltip or settings, not prominently.
- `local_models` — list of model tags already pulled locally. Cross-reference with `/api/models` to show "installed".

### 2.3 `GET /api/models` → JSON

The model catalog, already annotated for the current machine. This is the data behind the **model picker** and **preset picker**.

```json
{
  "recommended": "qwen3:4b",
  "models": [
    {
      "tag": "qwen3:1.7b",
      "display_name": "Qwen3 1.7B",
      "tier": "featherweight",
      "download_gb": 1.4,
      "min_ram_gb": 3,
      "native_max_ctx": 40960,
      "thinking_capable": false,
      "hidden": false,
      "notes": "Fastest, weakest reasoning; last resort.",
      "installed": true,
      "recommended": false,
      "fits": true,
      "default_preset": "Standard",
      "presets": [
        {
          "name": "Standard",
          "num_ctx": 8192,
          "num_predict": 640,
          "think": false,
          "est_ram_gb": 1.8,
          "fits": true
        }
      ]
    }
  ]
}
```

Field semantics the UI must express visually:

- `recommended` (top-level) — the single tag we suggest by default. Give it a badge/highlight.
- `tier` — one of `featherweight`, `default`, `default-alt`, `heavyweight`, `max`, `experimental`. **The picker groups by tier, in this order.** Tier is a first-class visual grouping.
- `installed` — already downloaded. Show a checkmark / "Installed" state; the Install button is hidden or disabled.
- `recommended` (per-model) — matches the top-level `recommended`. Badge it.
- `fits` — whether the model's `min_ram_gb` fits the machine's free RAM. Models that don't fit should be visibly de-emphasized (greyed, "needs more RAM" note) but **not hidden** — leadership likes seeing the ceiling.
- `download_gb`, `min_ram_gb`, `native_max_ctx`, `thinking_capable`, `notes` — supporting metadata for the model card.
- `presets` — per-model list. Each has `est_ram_gb` (estimated RAM at that context size) and its own `fits` flag. The preset picker repopulates per selected model. A preset that doesn't fit gets a greyed style.
- `default_preset` — which preset name to preselect.

Hidden models (`experimental` tier, e.g. `qwen3.5:4b`) are excluded server-side by default and should not appear unless explicitly revealed. Do not build UI that assumes they're always present.

### 2.4 `GET /api/config` → JSON

Current saved configuration. The SSH password is **redacted to null**; a boolean tells you whether one is configured.

```json
{
  "model": "qwen3:4b",
  "preset": "Standard",
  "ollama_host": "http://localhost:11434",
  "ssh": {
    "host": "bandit.labs.overthewire.org",
    "port": 2220,
    "username": "bandit0",
    "password": null,
    "timeout": 15
  },
  "ssh_configured": true
}
```

- Use this to hydrate the settings panel on load (selected model, selected preset, SSH host/port/user).
- **Never display a password.** `password` is always `null` here; `ssh_configured` tells you whether the SSH form should render as "connected/saved" vs "empty."

### 2.5 `POST /api/config` → JSON

Persist a partial config change. Body is a partial merge:

```json
{ "model": "qwen3:8b", "preset": "Extended", "ssh": { "host": "...", "port": 2220, "username": "...", "password": "...", "timeout": 15 } }
```

All keys optional. Returns an OK acknowledgement. Call this when the user changes the model, preset, or saves SSH details, so selections persist across reloads.

### 2.6 `POST /api/ssh/test` → JSON

Body is a full `SSHConfig` (`host`, `port`, `username`, `password`, `timeout`). The backend runs a trivial `echo ok` over SSH and reports:

```json
{ "ok": true, "message": "ok" }
```

`ok:false` returns a human-readable `message` (e.g. `ssh error: ...`). Surface this inline next to the Test button as success/failure with the message.

### 2.7 `POST /api/pull` → SSE stream (`text/event-stream`)

Body `{ "tag": "qwen3:8b" }`. Streams model-download progress as newline-delimited frames:

```
data: {"status":"pulling manifest"}

data: {"status":"downloading","completed":123456789,"total":5242880000}

data: {"status":"success"}

data: {"done":true}
```

- Each `data:` line is a JSON object. Progress frames may include `completed`/`total` byte counts — derive a **percentage** from these for the progress bar.
- The stream ends with `{"done":true}`. Treat that as "close the stream / mark installed."
- Frames without byte counts (e.g. `"pulling manifest"`, verifying) should show as indeterminate/animated states.

### 2.8 `POST /api/chat` → SSE stream (`text/event-stream`)

The core interaction. Body `{ "message": "user's message" }`. The backend spins up a fresh agent run and streams **one event per frame**. Read with `fetch()` + `ReadableStream`. Each frame is `data: {event json}\n\n`; the stream ends with `data: {"done":true}\n\n`.

Event objects have a `type` and type-specific fields:

| `type` | Fields | Meaning |
|---|---|---|
| `assistant` | `text` | A raw model reply for this turn (may contain the JSON action the model chose). |
| `action` | `name`, `args` | The agent decided to run a tool. `name` ∈ `ssh_exec`, `read_notes`, `write_notes`, `list_notes`. `args` is the action's argument object. |
| `observation` | `text` | The result of a tool call, fed back to the model. **Potentially attacker-controlled.** |
| `invalid` | `reason` | The model emitted something that wasn't a valid action. Recoverable — the loop continues. |
| `final` | `text` | The agent's final answer / summary. Terminal for the run. |
| `error` | `message` | The model call failed. Terminal for the run. |

Notes for rendering:

- A single user message produces **many** frames: assistant → action → observation → assistant → … → final. The transcript should read as a coherent, animated "the agent is working" sequence.
- `assistant` frames often contain the JSON action verbatim. You generally want to render the *action chip* (from the subsequent `action` frame) as the meaningful artifact, and either hide raw action JSON or show it collapsed. Free-form assistant prose (no action) should render as normal assistant text.
- `final` is the distinct, celebrated end state (see §4 message taxonomy). It is a teaching summary, not a raw flag.
- Always terminate on `{"done":true}` even after `final`/`error`.

---

## 3. Screen and component inventory

One screen, two regions: a **settings/setup panel** and a **chat pane**, under a persistent **status bar**. Below is every component, with the states each must support.

### 3.1 Status bar (persistent, top)

- **RAM indicator** — free / total GB. Prime candidate for a **live meter** (poll `/api/system`). States: healthy, tight (free RAM near the selected preset's `est_ram_gb`), critical.
- **Ollama status dot** — up (green) / down (red/grey). When down, the chat send should be disabled with a friendly nudge ("Start Ollama to chat").
- **App identity** — product name / logo lockup. This is the first thing leadership sees; it should feel like a product, not a script.
- States: loading (before first `/api/system`), connected, degraded (Ollama down), error (system endpoint unreachable).

### 3.2 Settings / setup panel (left or drawer)

**(a) Model picker** — a `<select>` (or a richer custom control) **grouped by tier** in `TIER_ORDER`. Each option/card is annotated:
- tier label (group heading),
- `display_name` + `tag`,
- badges: **Recommended**, **Installed**,
- fit state: fits / "needs more RAM" (greyed),
- supporting: `download_gb`, `min_ram_gb`, `native_max_ctx`, `thinking_capable`, `notes`.
- States: default (recommended preselected), selected, not-fitting (disabled-ish but visible), hidden-models-revealed (rare).

**(b) Preset picker** — a `<select>` that **repopulates whenever the model changes**. Each preset shows name + `est_ram_gb`; a preset that `!fits` gets a **greyed style**. `default_preset` preselects.
- States: default, selected, preset-doesn't-fit (greyed but selectable with a warning).

**(c) Install-model control** — a button that appears for non-installed models. On click it POSTs `/api/pull` and shows **streamed % progress** (progress bar + status text: "pulling manifest…", "downloading 42%", "verifying…", "done"). On completion, the model flips to **Installed**.
- States: idle (not installed), downloading (determinate %), indeterminate (manifest/verify), success, error/retry.

**(d) SSH connect form** — `host`, `port`, `username`, `password`, plus a **Test** button that POSTs `/api/ssh/test` and shows inline ok/fail with the returned message. Saving persists via `/api/config` (password sent on save, never re-displayed).
- States: empty, filled, testing (spinner), test-passed (green), test-failed (message), saved/configured (from `/api/config`'s `ssh_configured`).
- Security affordance: make clear this connects to a *practice* box the player controls.

### 3.3 Chat pane (main)

- **Transcript** — the scrolling conversation, rendering the message-type taxonomy in §4.
- **Composer** — message input + send. Disabled when Ollama is down. Enter-to-send with shift-enter newline is expected.
- **Empty state** — first run, before any message: a warm, on-brand welcome that orients a nervous beginner ("I'm your CTF copilot. Connect a practice box and ask me anything — I'll walk you through it.").
- **Loading / working state** — while a `/api/chat` stream is live: a visible "agent is working" indicator; the transcript grows frame by frame.
- **Error state** — an `error` event, or a dropped stream: a friendly, recoverable message with a retry.

### 3.4 Global states to design for

Every data-backed component needs: **loading**, **empty**, **populated**, **error**. Do not ship a component that only has its happy state. Leadership demos fail on the unhappy paths.

---

## 4. Chat message-type taxonomy

The transcript is not a flat list of "user / assistant" bubbles. It is a **narrated agent run**. Design distinct, recognizable treatments for each type. This taxonomy is the heart of the "wow."

1. **User message** — what the player typed. Standard, clean, right-aligned or clearly attributed.

2. **Assistant text** — the agent's reasoning/explanation in beginner-friendly prose. This is the "teacher talking." When an `assistant` frame is *only* a JSON action, prefer to suppress it and let the action chip speak; when it's prose, render it as teaching text.

3. **Action chip** — from an `action` event. A compact, scannable chip: **tool name** (`ssh_exec`, `read_notes`, `write_notes`, `list_notes`) + its **args** (e.g. the command). Feels like "the agent is doing something." Consider an icon per tool (terminal, note, list). Args like a shell command should render monospace.

4. **Observation block** — from an `observation` event. **Monospace, dimmed, terminal-flavored.** This is *untrusted output* — it should look like output being inspected, not app chrome. Long output should be collapsible/scrollable (the backend truncates and appends `...[truncated]`; show that marker). A subtle "untrusted output" affordance reinforces the anti-prompt-injection stance.

5. **Invalid notice** — from an `invalid` event. A small, non-alarming inline note ("the agent stumbled and is retrying"). It is *recoverable* — do not make it look like a crash.

6. **Final answer** — from a `final` event. **The celebrated, distinct end state.** This is a teaching summary — how the flag was obtained and what it means — *not* a raw flag dumped verbatim. Treat it as the payoff moment: distinct card, a little motion, a sense of accomplishment. Never style it as "secret loot"; style it as "you learned this."

7. **Error** — from an `error` event. Friendly, recoverable, with retry. Distinct from `invalid` (which is mid-run and self-healing) and from `final` (success).

Sequencing matters: a run reads top-to-bottom as *think → act → observe → think → … → conclude*. Motion should make that sequence feel alive without being distracting.

---

## 5. Core UX flows

### 5.1 First-run setup (the leadership-demo path)

1. App opens → status bar hydrates from `/api/system` (RAM, Ollama dot).
2. Model picker loads from `/api/models` with the **Recommended** model preselected.
3. If the recommended model isn't installed → the **Install** button invites a pull; `/api/pull` streams progress to a satisfying 100%.
4. Player fills the **SSH form** and hits **Test** → `/api/ssh/test` returns green.
5. Selections persist via `/api/config`.
6. Player types a first message → `/api/chat` streams a full narrated run ending in a **final** teaching summary.

Design this path to feel effortless and impressive end-to-end — it is the demo script.

### 5.2 Returning user

- `/api/config` hydrates prior model/preset/SSH; `ssh_configured` shows the box is remembered (password not shown). Player goes straight to chat.

### 5.3 Model change mid-session

- Change model → preset picker repopulates → if not installed, Install flow → persist via `/api/config`.

### 5.4 Chat run (the moment that sells it)

- Player sends → composer disables → transcript animates through `assistant`/`action`/`observation` frames → `final` lands as the payoff. Ollama-down disables send with a nudge.

---

## 6. Brand and tone

**Voice:** approachable, confident, a little playful. **CTF/hacker energy without being edgy** — think "friendly range instructor," not "l33t underground." Never intimidating, never condescending, never smug about exploits.

**Feelings to evoke:**
- *Beginner:* "I'm safe here. This is for me. I can do this."
- *Leadership:* "This is a real, polished product. This program is worth funding."

**Do:** warm welcomes, plain-language coaching, celebrate learning moments, treat the terminal as approachable.
**Don't:** skulls, balaclavas, "we're breaking in" framing, matrix-rain cliché played straight, raw flags flexed as trophies, jargon walls.

**Naming/identity:** "CEI Labs Agent." A clean wordmark lockup that reads as product, plus a small "your CTF copilot" descriptor. Consider a friendly mark (a helpful spark/terminal caret/guide dot) over an aggressive glyph.

---

## 7. Concrete visual directions (pick or blend)

All three keep the functional baseline intact and reskin via CSS variables (see §8). Provide a default dark theme; support light (see §9).

**Direction A — "Approachable Terminal."** A modern, rounded take on a hacker terminal: deep near-black/navy canvas, one confident accent (electric green *or* cyan *or* violet — pick one, not neon-all), crisp monospace only where it earns it (commands, observations), humanist sans for prose. Observation blocks look like a tasteful terminal pane. Playful without cosplay. *Best fit for the brand.*

**Direction B — "Guided Lab."** Softer, product-y, education-forward: card-based, generous spacing, a warm accent, subtle depth. The agent feels like a friendly tutor app. Terminal-ness is a texture, not the theme. *Safest for the nervous-beginner half of the audience.*

**Direction C — "Command Center."** A confident ops-dashboard feel for the leadership half: a live RAM meter and Ollama status as real telemetry, model catalog as a fleet, the chat as a mission log. High polish, data-dense but legible. *Highest "wow" ceiling; hardest to keep beginner-friendly — pair with B's warmth in copy.*

A strong result blends **A's terminal accent** + **B's warmth in the chat/empty states** + **C's telemetry in the status bar**.

---

## 8. Reskinnable CSS custom properties

The baseline UI is authored so **all color, plus corner radii, elevation, fonts, and key layout dimensions, flow through CSS custom properties in one `:root` block** (top of `style.css`), with **no inline styles in HTML**. Reskinning should mean re-valuing these tokens (and adding a `[data-theme]` override block), not rewriting markup. The baseline exposes exactly the tokens below — treat this as the token contract to preserve, extend, and re-value. (Spacing, motion timings, and a type scale are **not** tokenised yet; adding them is a recommended extension — see the note at the end of this section.)

**Surfaces & structure**
- `--color-bg` — app canvas background.
- `--color-surface` — primary panels/cards.
- `--color-surface-2` — secondary/raised surface.
- `--color-surface-3` — tertiary surface (inputs, deeper cards).
- `--color-border` — hairlines, dividers, input borders.
- `--color-border-strong` — emphasised borders / stronger dividers.

**Text**
- `--color-text` — primary text.
- `--color-text-muted` — secondary/dimmed text (metadata, observations).
- `--color-text-faint` — faintest text (hints, placeholders, disabled).

**Accent & brand**
- `--color-accent` — primary brand/action accent.
- `--color-accent-strong` — stronger accent for hover/active and emphasis.
- `--color-accent-soft` — low-alpha accent tint (badges, fills, focus tint).
- `--color-accent-contrast` — text/icon colour on accent fills.

**Semantic status**
- `--color-ok` — Ollama up, test passed, install success.
- `--color-warn` — tight RAM, preset doesn't fit, invalid-action notice.
- `--color-danger` — Ollama down, errors, test failed.
- `--color-info` — neutral informational.

**Message-type accents (chat taxonomy).** These are surface/border pairs, not single hues — each message type has its own fill and (where relevant) border:
- `--color-user-bg`, `--color-user-border` — user message.
- `--color-assistant-bg` — assistant text.
- `--color-action-bg`, `--color-action-border` — action chip.
- `--color-observation-bg`, `--color-observation-text` — observation block (dimmed terminal output).
- `--color-final-bg`, `--color-final-border` — final-answer (the payoff).
- `--color-invalid-bg`, `--color-invalid-border` — invalid-action notice.
- `--color-error-bg`, `--color-error-border` — error state.

**Typography**
- `--font-ui` — UI/prose typeface stack.
- `--font-mono` — commands/observations/code.

**Shape & elevation**
- `--radius-sm`, `--radius-md`, `--radius-lg` — corner radii.
- `--shadow-1`, `--shadow-2` — elevation.

**Layout**
- `--statusbar-h` — status bar height.
- `--panel-w` — settings panel width.

**Not yet tokenised (recommended extensions).** The baseline has no spacing scale, motion-timing, or type-scale tokens — sizes, transitions, and font sizes are currently literal values in `style.css`. Introducing them is a natural part of this pass; follow the baseline's naming so a future theme stays a single overrideable block:
- spacing: `--space-xs … --space-xl`
- motion: `--transition-fast`, `--transition-base`
- type scale: `--font-size-sm` / `--font-size-base` / `--font-size-lg`, `--line-height-base`
- content width: `--maxw-content`

Light/dark is currently handled by a `@media (prefers-color-scheme: light)` block that re-values the same tokens. If you move to an explicit toggle, a `:root[data-theme="light"]` / `:root[data-theme="dark"]` override re-valuing these tokens (defaulting via `prefers-color-scheme`) keeps the contract intact.

---

## 9. Accessibility and theming requirements

- **Contrast:** WCAG AA minimum for text and essential UI (AAA for body prose where feasible). Verify the accent on both light and dark surfaces. Never encode meaning in color alone — the Ollama dot needs a label/tooltip; fit/installed/recommended need text or icon, not just hue.
- **Keyboard:** full keyboard operability — model/preset selects, Install, SSH form + Test, composer (Enter to send, Shift+Enter newline), and scrolling the transcript. Visible focus rings on every interactive element (use the `--color-accent-soft` tint).
- **Screen readers:** label the status bar meters (`aria-label` with values), announce chat frames as they stream (a polite `aria-live` region for new transcript items, but avoid spamming every token). Action chips and observation blocks need accessible names ("tool call: ssh_exec", "command output").
- **Motion:** honor `prefers-reduced-motion` — the terminal-reveal/shimmer/meter animations must degrade to instant, static states.
- **Dark + light:** dark is the default hero theme; ship a light theme via the token override. Both must pass contrast.
- **Responsive:** works from a narrow laptop window to a projector/large demo screen. The settings panel should collapse to a drawer on narrow widths; the chat pane is the priority. No horizontal page scroll — wide content (observations, long commands) scrolls within its own container.
- **Untrusted-content safety:** observation text is attacker-controllable. Render it as **text, never as HTML** (no `innerHTML` of observation content). The visual "untrusted output" treatment is also a security signal — keep it.

---

## 10. What would make leadership say "wow"

Aim for *tasteful* spectacle — motion and polish that reinforce the product story, not gratuitous effects. High-value ideas:

- **Live RAM meter.** Poll `/api/system` and animate a smooth, real-time free-RAM gauge in the status bar. It makes the "runs on your own machine" story tangible and feels alive.
- **Model-download shimmer.** During `/api/pull`, a premium progress experience: animated shimmer on the downloading model card, real % from `completed`/`total`, graceful indeterminate states for "pulling manifest"/"verifying," and a satisfying success flourish when it flips to **Installed**.
- **Terminal-style observation reveal.** Observation blocks type/scan in like a terminal painting output (respecting `prefers-reduced-motion`). It sells the "agent is really doing something" narrative.
- **Narrated run choreography.** As `/api/chat` streams, stagger the appearance of assistant → action → observation frames with subtle motion so a run *reads* as think → act → observe. A small "agent is working" pulse between frames.
- **The final-answer moment.** When `final` lands, a distinct, celebratory card with a gentle flourish — framed as a *learning win* ("Here's how we cracked it") rather than a raw flag. This is the emotional peak of the demo.
- **Fit-aware model catalog.** Grouped-by-tier cards where **Recommended** glows, **Installed** is checkmarked, and models that don't fit are elegantly greyed with "needs more RAM" — leadership immediately grasps that the tool adapts to the machine.
- **Telemetry status dot.** The Ollama up/down dot as a live, confident signal (soft pulse when healthy), reinforcing "everything's local and running."
- **First-run empty state with personality.** A warm, branded welcome that makes a nervous beginner smile and a leader think "this is a product."

Keep it cohesive: one accent, consistent motion timings (`--transition-*`), and every animation reduced-motion-safe. The goal is a demo where a non-technical leader watches a beginner pull a model, connect a box, ask a question, and watch the agent teach — and comes away certain this is worth funding.

---

## 11. Guardrails for the design pass

- **Do not change** the API request/response shapes in §2 or the event-type contract in §2.8 / §4.
- **Do not** render observation or model output as HTML. Text only.
- **Do not** display SSH passwords; `/api/config` redacts them by design.
- **Do not** surface raw flags as trophies; the `final` event is a teaching summary — style it that way.
- **Keep** the no-build, no-external-CDN constraint (vanilla HTML/JS/CSS, self-contained assets).
- **Keep** all theming in CSS custom properties (§8); no inline styles in HTML.
- **Keep** every component's loading/empty/error states — the demo lives or dies on the unhappy paths.

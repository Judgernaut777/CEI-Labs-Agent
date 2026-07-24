# CEI Labs Agent — Plan (refined)

A lightweight, infra-independent "training-wheels" AI teammate for CEI Labs' CTF
event (Bandit / Krypton / Natas tracks). A small **local** model + a real
tool-use loop that participants run on their own laptop CPUs — no GPU, no cloud,
no API keys.

## Design goal

Not a pure Q&A tutor, not a fully autonomous solver — something in between.
Give participants genuine hands-on exposure to agentic tool use (the model
actually runs commands, reads output, reasons about what it sees) while
preserving challenge integrity — nudging toward explanation and partial guidance
rather than handing over flags.

This is a **pedagogy / default-experience** design, **not a security boundary**:
anyone can already bypass it by SSHing in manually, same as today. The goal is a
good default for people who'd otherwise be completely lost, not an anti-cheat gate.

Repo: https://github.com/Judgernaut777/CEI-Labs-Agent

## Reuse, don't rebuild: the agent loop

Fork the existing infra-independent loop from
`mcp-agentconnect/packages/agentconnect-runtime` rather than reinventing it. It
was built for exactly this shape of problem — a model with no native tool-calling
API that must reply with one JSON action per turn:

- **`actions.py`** — `parse_action()`: forgiving JSON extraction (handles code
  fences / surrounding prose) but strict on shape; a malformed action becomes an
  invalid action fed back as an observation so the loop retries rather than
  crashes. A reply with no JSON at all is treated as a free-form final answer.
- **`graph.py`** — a LangGraph `act → tool → act … → finalize` state machine.
  Each tool is gated by a `RuntimeConfig` flag (`allow_shell`, `allow_tests`,
  `allow_browser`) — exactly the pattern to extend with a new gated tool.
- **`agent.py`** — depends only on a `ModelSource` Protocol
  (`generate(GenerateRequest) -> GenerateResponse`), so it's already
  backend-agnostic (stub / llama.cpp / Ollama / anything OpenAI-compatible).
- Dependencies: `agentconnect-core` (pydantic schemas) + `langgraph>=1.0`. No
  ties to the router, model-manager, mTLS, or the R9700.

**Plan:** fork into the new repo. Strip `run_tests` / `fetch_url` / browser (not
relevant here), keep `read_file` / `write_file` / `list_dir` rescoped to a local
notes sandbox, and add one new tool: `ssh_exec`.

## Tools for the harness

| Tool | Purpose | Guardrail |
|---|---|---|
| **`ssh_exec`** (new) | Runs a command against the participant's assigned attacker/target box using the SSH connect info CTFd's instance-launcher panel already gives them (host/port/user/pass). **The only place real CTF work happens.** | Truncate observation length (reuse `config.observation_max_chars`). |
| `read_file` / `write_file` / `list_dir` (kept, rescoped) | Local scratch notes only (`~/.cei-labs-agent/notes/`) — track progress / discovered passwords across levels. | Sandboxed to that one directory, never the real filesystem. |
| local shell | **Disabled** (`allow_shell=False`). | See security note. |
| `finish` (kept) | Natural loop termination. | System prompt shapes it to explain / summarize rather than bluntly state the flag. |

### Security note — prompt injection is an elevated risk here specifically

Unlike a normal coding agent, the wargames' target content is **deliberately
adversarial** (Natas pages, Bandit files can contain attacker-controlled text)
and returns straight into the model's context via `ssh_exec` observations. A
small, weakly-aligned model reading that content is a realistic
prompt-injection vector. **Mitigation:** keep local shell and unrestricted
`write_file` off entirely, so the worst case of a successful injection is "the
chat response looks weird," never "arbitrary code executes on the participant's
laptop." State this plainly in the repo's security notes.

---

## Model selection (refined against verified mid-2026 data)

Verified against the Ollama library and 2026 web research (July 2026). Three of
the earlier plan's model facts were stale — corrected below.

### Fact-check

| Earlier claim | Verified reality (mid-2026) |
|---|---|
| "Qwen3.6-4B doesn't exist; smallest dense 27B" | ✅ **Still true.** `qwen3.6` starts at 27B. Correctly rejected. |
| "Qwen3.5-4B as an alternate" | ⚠️ **Exists but changed.** `qwen3.5:4b` (3.4 GB) is now multimodal + **hybrid-thinking** — no text-only instruct variant. Thinking traces are the same token-budget-burn failure that got VibeThinker/Ornith rejected. Demote to opt-in experimental. |
| "Gemma 4 E4B — no measured data, ~5GB" | ✅ **Now real & better.** Released Apr 2026, Apache-2.0, **native tool-calling (~86% acc)** in every size, `ollama pull gemma4`. Default E4B ~9.6 GB; smaller quants exist. |
| "Qwen3-4B-Instruct-2507 default" | ✅ **Still the right default.** `qwen3:4b` = 2.5 GB, 256K ctx, lightest credible option, and the only *measured* one (untuned JSON-parse rate 1.00, ~5.5 s/decision on 16 threads). Pre-select it. |

### Correctness requirement: disable thinking

The loop needs **one clean JSON action per turn**. The newest 4B models
(Qwen3.5, Gemma 4) are hybrid-thinking; left in thinking mode they emit
`<think>` traces that exhaust the token budget before the action — exactly the
failure mode that got the reasoning models rejected. The harness **must
explicitly disable thinking** for any thinking-capable model (`think: false` /
`/no_think`, and/or a tight `num_predict`) and the curated list prefers
non-thinking-by-default models. This is a correctness requirement, not tuning —
enforced per-model in the model registry and honored in `model_source.py`.

### Curated ladder (full 5 tiers, all verified pullable via Ollama)

A hardware-tiered ladder. A RAM preflight auto-suggests the highest tier that
fits; every row shows download + working RAM so participants self-select without
needing to understand why. Models are pulled on-demand (`ollama pull <tag>`) only
when first selected, never all upfront.

| Tier (RAM-suggested) | Model | Ollama tag | Download | ~Working RAM | Notes |
|---|---|---|---|---|---|
| **Featherweight** (old / 8 GB) | Qwen3 1.7B | `qwen3:1.7b` | 1.4 GB | ~3 GB | Fastest; weakest reasoning, last resort |
| **⭐ Default** (typical 8–16 GB) | Qwen3-4B (2507) | `qwen3:4b` | 2.5 GB | ~4 GB | Only *measured* option; JSON-parse 1.00; no thinking |
| Alternate (same tier) | Gemma 4 E4B | `gemma4` | ~6 GB (Q4) | ~6 GB | Native tool-calling + model diversity; newer |
| **Heavyweight** (16 GB+) | Qwen3 8B | `qwen3:8b` | 5.2 GB | ~8 GB | Noticeably better reasoning |
| Max (workstation 32 GB+) | Qwen3 14B | `qwen3:14b` | 9.3 GB | ~11 GB | Best quality for those with the RAM |
| *Experimental* (opt-in, hidden by default) | Qwen3.5 4B | `qwen3.5:4b` | 3.4 GB | ~5 GB | Multimodal / hybrid-thinking; only if thinking-disable proves reliable in smoke test |

**Rejected:** VibeThinker-3B / Ornith-1.0 (reasoning-specialized; VibeThinker
measured 52% JSON-parse failure untuned; Ornith's smallest variant is 9B).
`qwen3.6:*` (smallest dense 27B — too heavy for "most laptop CPUs").

### Design implications for the UI / server

- **RAM preflight** (`psutil`): read total & free RAM at startup, pre-select the
  highest tier that fits, gray-out / warn on tiers that don't. This is what makes
  "self-tune without understanding why" actually work.
- **Dropdown labels show size + RAM**, e.g.
  `Qwen3-4B — 2.5 GB download, needs ~4 GB free (recommended)`.
- **Context-length selector** (`num_ctx`: 4096 / 8192 / 16384 / 32768) interacts
  with RAM — bigger context costs memory; warn when chosen context × model would
  exceed free RAM.
- **Thinking-off enforced per model** in the registry.

---

## Interface: local web UI (not terminal-only)

A GUI with dropdown selectors, meant to look good. (A separate design-handoff doc
for Claude Design comes at the UI-build phase, not now.)

**Architecture:** the CLI entry point (`ctf-agent`) starts a small local web
server (FastAPI + plain HTML/JS, no heavy frontend build step) bound to
localhost, then opens the participant's default browser to it. Same pattern as
Open WebUI / text-generation-webui: trivially cross-platform, a natural home for
the model/context dropdowns, no native-GUI packaging headaches.

## Packaging — "sets itself up"

- **Don't** build PyInstaller/Nuitka native binaries for this event — near-certain
  Windows Defender/SmartScreen false-positives on unsigned binaries, macOS
  Gatekeeper quarantine on unsigned/unnotarized apps (real notarization needs an
  Apple Developer account + days of lead time), and known pydantic/langgraph
  bundling friction. Too risky for a 1-week timeline.
- **Do** bootstrap via **`uv`** (Astral's single static binary; same trusted
  `install.sh` / `install.ps1` pattern as rustup/Deno/Bun) which can provision
  its own Python with zero pre-existing Python. `uv tool install
  git+https://github.com/Judgernaut777/CEI-Labs-Agent` installs the harness and
  exposes the `ctf-agent` command — repo must stay **public** so this needs no auth.
- **Mac/Linux:** single `curl -fsSL <bootstrap.sh> | sh` — chains Ollama's
  official `install.sh`, a **disk-space preflight** (Ollama doesn't do one — a
  known failure mode), `uv` install, `uv tool install`, then launches `ctf-agent`.
- **Windows:** single PowerShell one-liner (`irm <bootstrap.ps1> | iex`) — Ollama's
  Windows install is per-user (no admin/UAC), auto-starts on login. Try
  `OllamaSetup.exe /VERYSILENT /SUPPRESSMSGBOXES /NORESTART` (undocumented but
  plausible Inno Setup flags) with a **poll-based fallback** to a guided "an
  installer window opened — click Install, then press Enter here" step if the
  silent path doesn't verify within ~60–120 s. **Test against 2–3 real Windows
  laptops before the event — don't ship on faith.**
- **`TROUBLESHOOTING.md`** covering: disk space; AV/SmartScreen prompts on the
  bootstrap script itself (`-ExecutionPolicy Bypass` scoped to the process only);
  corporate-locked-down laptops (documented non-goal — loaner laptops + a live
  help channel are the real mitigation); "close and reopen your terminal" for PATH
  refresh.

## Critical files to create

```
CEI-Labs-Agent/
  README.md                    — non-technical setup guide, single command per OS
  TROUBLESHOOTING.md
  pyproject.toml               — [project.scripts] ctf-agent = "cei_labs_agent.cli:main"
  bootstrap.sh                 — Mac/Linux one-liner target
  bootstrap.ps1                — Windows one-liner target
  src/cei_labs_agent/
    cli.py                     — entry point: launch web server, open browser
    server.py                  — FastAPI: chat endpoint, model/context selectors, SSH form, RAM preflight
    config.py                  — local config (~/.cei-labs-agent/config.json): SSH creds, model, context length
    models.py                  — NEW: curated model registry (tier, ollama tag, download, min RAM, thinking-capable flag)
    model_source.py            — ModelSource impl vs Ollama's OpenAI-compatible endpoint; enforces thinking-off
    actions.py                 — forked from agentconnect-runtime, KNOWN_ACTIONS + "ssh_exec"
    graph.py                   — forked loop, ssh_exec wired in as a new gated tool
    state.py, workspace.py     — forked, trimmed
    tools/
      ssh.py                   — NEW: paramiko-based ssh_exec
      notes.py                 — local scratch read/write, sandboxed
    prompts.py                 — NEW CTF-copilot system prompt (explain > solve, never state exact flag directly)
    static/                    — minimal HTML/JS/CSS chat UI with model + context dropdowns
  tests/
    test_actions.py            — port existing tests, add ssh_exec cases (mocked)
    test_models.py             — NEW: registry integrity, RAM-tier selection, thinking-off enforced
```

## Verification

- **Unit tests** for the `actions.py` / `graph.py` fork (mock `ModelSource`, mock
  SSH) — port existing test patterns from agentconnect-runtime. Add registry +
  RAM-tier + thinking-off tests.
- **Local smoke test:** run the CTFd stack already deployed on this box
  (`https://127.0.0.1`) against one live Bandit level with real SSH creds from an
  actual instance-launcher panel; confirm the loop reads output, explains, and
  doesn't blurt the flag verbatim. **Also confirm thinking-off holds** for a
  hybrid model (Gemma 4 / Qwen3.5-4B) — one clean JSON action per turn.
- **Cross-platform installer dry run:** actually run `bootstrap.sh` /
  `bootstrap.ps1` on real Linux/Mac/Windows machines before the event — this is the
  one area with genuine unknowns (undocumented Ollama silent-install flag).

---

### Sources (model verification, July 2026)

- Ollama library — [qwen3](https://ollama.com/library/qwen3),
  [qwen3.5](https://ollama.com/library/qwen3.5),
  [qwen3.6](https://ollama.com/library/qwen3.6)
- [Gemma 4 update: tool calling, vision (July 2026)](https://explainx.ai/blog/gemma-4-updates-flash-attention-tool-calling-july-2026)
- [Gemma 4 specs & sizes (2026)](https://aurigait.com/blog/gemma-4-features-benchmarks-guide/)
- [Qwen3.5 — Unsloth docs](https://unsloth.ai/docs/models/qwen3.5)

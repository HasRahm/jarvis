<p align="center">
  <img src="https://img.shields.io/badge/python-3.11+-3776AB?style=flat-square&logo=python&logoColor=white" alt="Python 3.11+" />
  <img src="https://img.shields.io/badge/license-BSL_1.1-blue?style=flat-square" alt="License" />
  <img src="https://img.shields.io/github/actions/workflow/status/HasRahm/jarvis/ci.yml?branch=master&style=flat-square&label=CI" alt="CI Status" />
  <img src="https://img.shields.io/badge/tests-323%20passed-brightgreen?style=flat-square" alt="Tests" />
</p>

<p align="center">
  <code>▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓  Phase 25/25 — SUPABASE BRAIN UNLOCKED</code>
</p>

<h1 align="center">
  Jarvis OS — Open Source Computer Use for Windows
</h1>

<p align="center">
  The first open source computer use system for Windows that controls real applications<br/>
  through the Win32 accessibility tree — no screenshots, no cloud sandbox, no API costs.<br/>
  Runs Gemma4 locally via Ollama, routes coding tasks to specialized AI agents,<br/>
  and lets you control your entire PC from your phone.<br/><br/>
  🕹️ <strong>44 phases shipped. 500 tests. Your PC is the controller.</strong>
</p>

<p align="center">
  <a href="#-quick-start--begin-your-quest"><strong>Quick Start</strong></a> ·
  <a href="#%EF%B8%8F-how-the-braille-system-works"><strong>Braille System</strong></a> ·
  <a href="#%EF%B8%8F-jarvis-vs-claude-computer-use"><strong>vs Claude CU</strong></a> ·
  <a href="#%EF%B8%8F-architecture"><strong>Architecture</strong></a> ·
  <a href="#%EF%B8%8F-quest-log"><strong>Quest Log</strong></a> ·
  <a href="#-skills-library"><strong>419+ Skills</strong></a>
</p>

---

## Why Jarvis?

```
╔══════════════════════════════════════════╗
║  JARVIS OS  ·  LOCAL AI AGENT  ·  v25   ║
╠══════════════════════════════════════════╣
║  🧠 Memory        Supabase (async)       ║
║  👁️  Vision        Win32 tree + Claude   ║
║  💰 API cost      $0 for most tasks      ║
║  ⚡ Click speed   ~80 ms (braille probe) ║
║  📱 Phone ctrl    Yes — voice PWA        ║
║  🌐 Runs offline  Yes — Gemma4 + Ollama  ║
╚══════════════════════════════════════════╝
```

Most AI coding tools give you **a chatbot**. Jarvis gives you **a team**.

When you describe a task in plain English, Jarvis doesn't just ask a single LLM. It decomposes your request into subtasks and dispatches them to specialized agents — Frontend, Backend, QA, and Infrastructure — that run in dependency order, verify each other's output, and stream progress to your phone as synthesized voice.

> **Self-hosted first.** Your keys, your data, your machine. No cloud account required beyond the AI provider APIs you already use.

---

## ⚔️ Jarvis vs Claude Computer Use

| Round | Jarvis | Claude Computer Use |
|-------|--------|---------------------|
| **Location method** | Win32 accessibility tree (~1 ms) | Screenshot → vision model (~3 s) |
| **Cost per action** | $0 (local Ollama) | ~$0.003 / screenshot |
| **Works offline** | ✅ Gemma4 via Ollama | ❌ |
| **WebGL / canvas apps** | Vision fallback (`visual_click`) | Always vision |
| **Phone + voice control** | ✅ PWA + TTS | ❌ |
| **Open source** | ✅ BSL 1.1 | ❌ |
| **Winner** | 🏆 | — |

---

## 🕵️ How the Braille System Works

Instead of taking a screenshot and asking a vision model "where is the button?", Jarvis's **Braille System** probes the screen like a finger reading braille — it calls Win32's `ControlFromPoint(x, y)` at a grid of points inside the target window's pixel bounds. Each probe returns the exact accessibility element at that coordinate in ~1 ms with no network call.

**200 grid probes = ~80 ms. One vision API screenshot call = 2–4 s.**

The probe grid scans in two passes:
1. **Coarse pass (60 px step, top 40% of window)** — fast path for toolbars and nav bars
2. **Fine pass (25 px step, full window)** — catches anything lower or tighter

When the target element is found under a probe point, the cursor is already there — click immediately without a separate movement step. Since probes are clamped to the window's pixel rectangle, the Windows taskbar and other windows can never be accidentally matched.

**Canvas fallback:** WebGL apps (Figma canvas, Blender, 3D views) return the canvas container from `ControlFromPoint`, not the element inside it. For these, `visual_click` sends a screenshot to Claude Vision which returns `FOUND x y` coordinates in the resized image, scaled back to screen coordinates.

→ [`tools/hybrid_cursor.py`](tools/hybrid_cursor.py) · [`tools/visual_click.py`](tools/visual_click.py)

---

## 🚀 Quick Start — Begin Your Quest

### 1. Clone & bootstrap

```bash
git clone https://github.com/HasRahm/jarvis.git
cd jarvis
bash scripts/bootstrap.sh     # installs Bun, GBrain, Python venv, Playwright
```

### 2. Configure

```bash
cp .env.example .env
# Fill in your API keys:
#   ANTHROPIC_API_KEY=sk-ant-...
#   GEMINI_API_KEY=...
#   OPENAI_API_KEY=sk-...
#   HERMES_SECRET=choose-a-strong-random-secret
```

### 3. Pull the local model

```bash
ollama pull gemma4:31b-cloud
```

### 4. Start Jarvis

```bash
# Linux / macOS
uvicorn core.hermes.server:app --host 0.0.0.0 --port 9000

# Windows
powershell -ExecutionPolicy Bypass -File scripts/start_local.ps1
```

### 5. Connect your phone

Open `https://<tunnel-url>/phone` on your phone. Enter your `HERMES_SECRET` in Settings. Tap **Connect**.

The start script launches a Cloudflare quick tunnel — the URL appears in the terminal.

---

## 💡 How It Works

```
 You say: "Build a REST API with auth and a dashboard"
```

**Step 1 → Decompose.** Gemma-4 (running locally via Ollama) parses your request and builds a dependency graph of atomic subtasks.

**Step 2 → Route.** Each subtask is assigned to the best agent for the job. The [model router](agents/model_router.py) picks the optimal LLM per role, with automatic fallback chains.

**Step 3 → Execute.** Agents run in topological order. The Backend agent (Claude) writes migrations and API endpoints. The Frontend agent (Gemini) builds the UI. The QA agent (GPT) verifies contracts and writes tests. They coordinate through [`AGENTS.md`](AGENTS.md) — a shared markdown file. No agent calls another agent's API directly.

**Step 4 → Stream.** Voice updates stream to your phone PWA over WebSocket in real-time. Tap any element in the live preview to trigger **visual self-correction** — the DAG heals itself automatically.

**Step 5 → Remember.** Results are stored in Supabase (Phase 25: no more Bun cold-start). Next session starts with full context of everything you've built before.

<details>
<summary><strong>📺 Example terminal output</strong></summary>

```
$ jarvis "Build a SaaS REST API with JWT auth and user management"

════════════════════════════════════════════════════
  Jarvis Multi-Agent Orchestrator
  Task: Build a SaaS REST API with JWT auth...
  ID:   task_20260521_143022
════════════════════════════════════════════════════

[1/3] Decomposing task with Gemma-4...
[2/3] Building execution DAG (4 subtasks)...
[3/3] Executing agents...

--- Step 1/4: [backend] ---
    Design users table + JWT auth endpoints
    [PASS] migrations/001_users.sql, app/auth.py, app/users.py

--- Step 2/4: [frontend] ---
    Build login + dashboard UI wired to auth API
    [PASS] index.html, app.js, styles.css

--- Step 3/4: [qa] ---
    Verify contracts and write integration tests
    [PASS] tests/test_auth.py (12 tests)

--- Step 4/4: [iac] ---
    Generate Terraform for deployment
    [PASS] terraform/main.tf, terraform/variables.tf

════════════════════════════════════════════════════
  Result: COMPLETED · Files: 9 · Cost: $0.0042
════════════════════════════════════════════════════
```

</details>

---

## ⚙️ Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  Phone PWA / Console (phone/index.html)                     │
│  WebSocket :9000                                            │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│  Hermes Bridge (core/hermes/server.py)                      │
│  FastAPI + asyncio broadcaster + voice synthesis             │
│                                                             │
│  ┌──────────────────┐  ┌─────────────────────────────────┐  │
│  │ Intent Classifier │  │ DAG Orchestrator                │  │
│  │ (gemma4:31b)     │  │ (core/orchestrator/dag.py)      │  │
│  └──────────────────┘  │                                 │  │
│                        │  ┌───────────┐ ┌──────────────┐ │  │
│                        │  │ Frontend  │ │ Backend      │ │  │
│                        │  │ (Gemini)  │ │ (Claude)     │ │  │
│                        │  └───────────┘ └──────────────┘ │  │
│                        │  ┌───────────┐ ┌──────────────┐ │  │
│                        │  │ QA        │ │ IaC          │ │  │
│                        │  │ (GPT)     │ │ (Claude)     │ │  │
│                        │  └───────────┘ └──────────────┘ │  │
│                        └─────────────────────────────────┘  │
└─────────────────────────────┬───────────────────────────────┘
                              │
                 ┌────────────┼────────────┐
                 ▼            ▼            ▼
          ┌──────────┐ ┌──────────┐ ┌──────────┐
          │ Supabase │ │ Tools    │ │ Skills   │
          │ (memory) │ │ (shell,  │ │ (419+    │
          │          │ │ browser, │ │ loadable │
          │          │ │ desktop) │ │ prompts) │
          └──────────┘ └──────────┘ └──────────┘
```

### Agent Coordination via AGENTS.md

Agents don't call each other's APIs. Instead, they read and write a shared [`AGENTS.md`](AGENTS.md) file — a markdown-based protocol that tracks:

| Section | Purpose |
|---------|---------|
| **Current Task** | Task ID, description, status |
| **Agent Assignments** | Which agent runs which model, current status |
| **Task Log** | Timestamped entries from each agent |

This design is inspectable, debuggable, and version-controllable. You can read `AGENTS.md` at any time to see exactly what happened.

---

## 🗺️ Quest Log

<details>
<summary><strong>Phase 25 — SUPABASE BRAIN</strong> ✅ <em>Unlocked: async memory, no Bun cold-start, 323 tests green</em></summary>

`brain_get` / `brain_write` now talk directly to Supabase via PostgREST (supabase-py). Fire-and-forget write queue via a daemon thread — writes return instantly. The 45 s blocking Bun subprocess is gone. Ordering-critical callers (session checkpoints, contract handoff) use the synchronous `mem_upsert` path. Postgres FTS + ILIKE fallback replaces the vector search hot path.

</details>

<details>
<summary><strong>Phase 24 — AGENT VIEW + VIRTUAL CURSOR</strong> ✅ <em>Unlocked: annotated screenshots, click-through overlay ring, smart_fill</em></summary>

Graph-first routing: locate via Win32 tree, verify via vision. A click-through overlay ring shows exactly where the agent is acting. Every locate/click op saves an annotated PNG (`scratch/agent_view/`) with window rects, braille probe dots, match boxes, OCR boxes, and vision crops. `smart_fill` scores cached elements by token overlap and routes to UIA patterns before touching the physical mouse.

</details>

<details>
<summary><strong>Phase 23 — INLINE STREAMING REPL</strong> ✅ <em>Unlocked: Claude Code-style terminal, Ctrl-C works, double-Ctrl-C to exit</em></summary>

Replaced the blocking subprocess runner with a chunked streaming REPL. Each tool response streams token-by-token in the terminal. Ctrl-C cancels the current tool call without killing the process. UTF-8 streams, stderr sunk separately, resilient loop that doesn't crash on tool timeout.

</details>

<details>
<summary><strong>Phase 22h — SECURITY HARDENING</strong> ✅ <em>Unlocked: no token in public gist, QR out-of-band pairing, fail-closed auth</em></summary>

Closed a High-severity RCE vector: `--remote` was publishing the live tunnel token in a world-readable GitHub gist. Token now delivered out-of-band via QR fragment (never transmitted to a server). Auto-generate + persist `HERMES_SECRET` to `.env`. `core/auth.py` fail-closes when secret is unset. HTTP + WS auth unified through one call-time validator.

</details>

<details>
<summary><strong>Phase 22g — AUTOMATION SPEED</strong> ✅ <em>Unlocked: batch WebGL flows, vocab cheatsheet, sleep trimming</em></summary>

`desktop_batch_actions` now supports `visual_click` and `visual_inspect` — an entire focus→click→type→verify sequence in one LLM turn. The 48 KB vocab block injected every turn was replaced with a 3 KB cheatsheet; full tables available via `vocab_lookup` tool. `desktop_smooth_click` default duration 1.5 s → 0.4 s. `desktop_focus_window` skips the titlebar bypass click when the window is already foreground.

</details>

<details>
<summary><strong>Phase 22f — VISUAL VOCABULARY</strong> ✅ <em>Unlocked: universal UI symbol grammar, self-learning vocab_learn tool</em></summary>

300+ icon shapes, 200+ app logos, 50+ UI patterns loaded into the Hermes system prompt. Each logo entry carries a `ui_type` flag (`electron_webgl`, `native_win32`, `html`) that tells the agent which automation tool to use without per-app guides. `vocab_learn` appends discovered patterns to `visual-vocab/learned/` — the agent teaches itself.

</details>

<details>
<summary><strong>Phase 22e — VISUAL CLICK</strong> ✅ <em>Unlocked: vision-guided clicking for WebGL/canvas UIs</em></summary>

`visual_click(description)` takes a screenshot, sends it to Claude Vision with a strict coordinate extraction prompt (`FOUND x y` format), scales the coordinates back to screen resolution, and clicks. Fixes the Figma Community search loop where `ControlFromPoint` returned the canvas container instead of the search input.

</details>

<details>
<summary><strong>Phase 22d — VISUAL INSPECT</strong> ✅ <em>Unlocked: eyes for Jarvis — Claude Vision as a perception bridge</em></summary>

`visual_inspect(question)` captures the screen with mss, resizes to 1280 px, sends to Claude Vision (Gemini fallback), and returns a natural-language description with approximate pixel coordinates. Breaks the OCR loop on WebGL / Electron / SPA UIs where pytesseract returns only sidebar text.

</details>

<details>
<summary><strong>Phase 22c — MOUSE BRAILLE + VERIFY LOOP</strong> ✅ <em>Unlocked: window-bounded probing, no more taskbar misfire</em></summary>

Replaced `WalkControl` (bleeds across windows) with `ControlFromPoint` grid probes clamped to the target window's pixel rect. The taskbar can never be returned because its y-coordinate is outside the probe range. Added `_verify_outcome` (imprint delta + OCR check) and `max_retries` to `hybrid_locate_click`.

</details>

<details>
<summary><strong>Phases 1–22b</strong> ✅ <em>Foundation: DAG orchestrator, multi-agent routing, voice streaming, skills engine, phone PWA, Spatial Cortex, session recovery, desktop automation...</em></summary>

The full build history is in the git log. Each phase added one concrete capability. Phase 1 was a single-agent prototype. Phase 22b was the first working desktop automation. The braille probe technique emerged from debugging why the taskbar kept getting clicked instead of the target window.

</details>

---

## 📚 Skills Library

Jarvis ships with **419+ dynamically-loadable skill modules** covering engineering, product, marketing, compliance, and more. Skills are injected into agent system prompts at runtime based on task relevance.

<details>
<summary><strong>View skill categories</strong></summary>

| Category | Examples |
|----------|---------|
| **Engineering** | `karpathy-coder`, `senior-backend`, `senior-frontend`, `code-reviewer`, `tdd`, `ci-cd-pipeline-builder` |
| **Product** | `product-manager`, `prd`, `user-story`, `agile-product-owner`, `sprint-plan` |
| **Marketing** | `growth-marketer`, `seo-audit`, `content-strategist`, `landing-page-generator` |
| **Infrastructure** | `aws-solution-architect`, `kubernetes-operator`, `terraform-patterns`, `devops-engineer` |
| **Security** | `red-team`, `security-pen-testing`, `soc2-audit-prep`, `gdpr-audit-prep` |
| **Finance** | `financial-analyst`, `pricing-strategist`, `cfo-advisor`, `revenue-operations` |
| **Leadership** | `ceo-advisor`, `cto-advisor`, `founder-mode`, `board-deck-builder` |

Each skill is a self-contained directory with prompts, templates, and context. See [`skills/`](skills/) for the full list.

</details>

---

## 🏗️ Project Structure

```
jarvis/
├── core/
│   ├── hermes/              # WebSocket server, voice streaming, intent classifier
│   │   ├── server.py        # FastAPI + asyncio broadcaster (731 lines)
│   │   ├── intent_classifier.py
│   │   └── bridge.py        # Telegram integration
│   ├── orchestrator/        # DAG engine, task parser, distributed sync
│   │   ├── dag.py           # Core DAG builder & executor
│   │   ├── task_parser.py   # Gemma-4 powered task decomposition
│   │   └── context_sync.py  # Cross-agent context sharing
│   └── system/              # Skills engine, auth
├── agents/
│   ├── base_agent.py        # Abstract agent with retry, telemetry, AGENTS.md protocol
│   ├── frontend_agent.py    # Gemini-powered UI generation
│   ├── backend_agent.py     # Claude-powered API/DB generation
│   ├── qa_agent.py          # GPT-powered verification + test writing
│   ├── iac_agent.py         # Claude-powered Terraform/infra
│   ├── model_router.py      # Role → model mapping with env overrides
│   └── adaptive_router.py   # Learns best model per role from outcomes
├── brain/                   # Memory layer — Supabase direct + async queue
│   ├── supabase_store.py    # Lazy singleton, timeout executor, drain queue
│   ├── get.py / write.py / query.py
├── tools/                   # Shell, browser (Playwright), desktop automation
│   ├── hybrid_cursor.py     # Braille System — ControlFromPoint grid probe
│   ├── visual_click.py      # Vision-guided clicking for WebGL/canvas
│   └── agent_view.py        # Annotated screenshot capture
├── phone/                   # Mobile PWA, console, telemetry dashboard, landing page
├── skills/                  # 419+ dynamically-loaded skill modules
├── tests/                   # 323 offline unit tests (JARVIS_CI=true stubs all external calls)
├── scripts/                 # bootstrap.sh, start_local.ps1, deploy_linux.sh
├── visual-vocab/            # Icon dictionary, app logos, UI patterns, learned/
├── .env.example             # All configurable env vars documented
├── docker-compose.yml       # Sandboxed agent execution
└── AGENTS.md                # Shared agent coordination protocol
```

---

## 🔧 Configuration

### Prerequisites

| Requirement | Version | Purpose |
|---|---|---|
| Python | 3.11+ | Runtime |
| [Ollama](https://ollama.ai) | latest | Local AI model (Gemma-4 31B) |
| [Bun](https://bun.sh) | latest | GBrain knowledge graph runtime |
| Docker Desktop | latest | *Optional* — sandboxed agent execution |

### API Keys

You need at least one AI provider API key. Jarvis uses multi-provider routing:

| Provider | Model | Role | Required? |
|----------|-------|------|-----------|
| **Anthropic** | Claude Sonnet 4.6 | Backend, IaC | Recommended |
| **Google** | Gemini 3.1 Pro | Frontend | Recommended |
| **OpenAI** | GPT-5.4 | QA | Recommended |
| **Ollama** | Gemma-4 31B | Orchestrator (local) | Required |

> **Tip:** You can override model assignments per role via environment variables: `AGENT_MODEL_BACKEND=gpt-5.4` swaps the backend agent to GPT.

### Key Environment Variables

| Variable | Description | Default |
|---|---|---|
| `HERMES_SECRET` | Shared secret for phone WebSocket auth | *required* |
| `SUPABASE_URL` | Supabase project URL for async memory | optional |
| `SUPABASE_SERVICE_ROLE_KEY` | Supabase service role key | optional |
| `JARVIS_AGENT_TIMEOUT_SEC` | Max seconds per agent execution | `300` |
| `JARVIS_SANDBOX_MODE` | Code execution sandbox: `local`, `docker`, `e2b` | `local` |
| `JARVIS_CI` | Set to `true` to stub all external calls (for testing) | `false` |

See [`.env.example`](.env.example) for the complete list with descriptions.

---

## 🧪 Testing

All 323 tests run fully offline — no API keys, no network, no Docker required:

```bash
JARVIS_CI=true python -m pytest tests/ -v
```

`JARVIS_CI=true` stubs all LLM calls, Supabase queries, and browser automation with deterministic mock responses. CI runs automatically on every push via [GitHub Actions](.github/workflows/ci.yml).

---

## 🖥️ Web Interfaces

Jarvis ships with multiple web interfaces, all served from the same port:

| Path | Interface |
|------|-----------|
| `/phone` | Mobile PWA — glassmorphic voice interface |
| `/landing` | Marketing landing page |
| `/telemetry` | Real-time cost & performance dashboard |
| `/architecture` | Interactive system architecture diagram |

---

## 🚢 Deployment

### Linux VPS (one command)

```bash
sudo bash scripts/deploy_linux.sh
```

Creates a `jarvis` system user, installs to `/opt/jarvis`, and configures two systemd services with `Restart=on-failure`. Then set up a named Cloudflare tunnel for a stable domain:

```bash
cloudflared tunnel login
cloudflared tunnel create jarvis
cloudflared tunnel route dns jarvis your-subdomain.your-domain.com
cloudflared tunnel run jarvis
```

### Docker

```bash
docker-compose up -d
```

---

## 💰 Cost Awareness

Each agent invocation calls real AI APIs. The telemetry dashboard at `/telemetry` shows:

- **Cumulative spend** across all models
- **Token usage** (input/output) per call
- **Per-model call counts** and latency
- **Cost per task** breakdown

Set `JARVIS_AGENT_TIMEOUT_SEC` to limit runaway costs from hung agents. The adaptive router learns which models give the best results at the lowest cost for each role.

---

## 🤝 Contributing

We welcome contributions! Here's how to get started:

1. **Fork** and clone the repo
2. **Bootstrap**: `bash scripts/bootstrap.sh`
3. **Configure**: `cp .env.example .env` and fill in API keys
4. **Test**: `JARVIS_CI=true python -m pytest tests/ -v` (all 323 tests should pass)
5. **Submit a PR** — CI runs the full suite automatically

See [CONTRIBUTING.md](CONTRIBUTING.md) for detailed guidelines.

---

## 📄 License

[Business Source License 1.1](LICENSE.txt) — free for non-competitive use. Converts to MPL 2.0 after 4 years.

---

<p align="center">
  <sub>Built with ❤️ by humans and agents working together.</sub>
</p>

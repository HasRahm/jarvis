<p align="center">
  <img src="https://img.shields.io/badge/python-3.11+-3776AB?style=flat-square&logo=python&logoColor=white" alt="Python 3.11+" />
  <img src="https://img.shields.io/badge/license-BSL_1.1-blue?style=flat-square" alt="License" />
  <img src="https://img.shields.io/github/actions/workflow/status/HasRahm/jarvis/ci.yml?branch=master&style=flat-square&label=CI" alt="CI Status" />
  <img src="https://img.shields.io/badge/tests-127%20passed-brightgreen?style=flat-square" alt="Tests" />
  <img src="https://img.shields.io/badge/agents-4%20specialized-blueviolet?style=flat-square" alt="Agents" />
  <img src="https://img.shields.io/badge/skills-419+-orange?style=flat-square" alt="Skills" />
</p>

<h1 align="center">
  Jarvis — AI Operating System
</h1>

<p align="center">
  <strong>Turn plain English into production-ready apps.</strong><br/>
  A self-hosted AI OS that decomposes your tasks into a DAG of specialized agents,<br/>
  streams voice updates to your phone, and remembers everything across sessions.
</p>

<p align="center">
  <a href="#-quick-start"><strong>Quick Start</strong></a> ·
  <a href="#-how-it-works"><strong>How It Works</strong></a> ·
  <a href="#%EF%B8%8F-architecture"><strong>Architecture</strong></a> ·
  <a href="#-features"><strong>Features</strong></a> ·
  <a href="#-skills-library"><strong>419+ Skills</strong></a> ·
  <a href="#-contributing"><strong>Contributing</strong></a>
</p>

---

## Why Jarvis?

Most AI coding tools give you **a chatbot**. Jarvis gives you **a team**.

When you describe a task in plain English, Jarvis doesn't just ask a single LLM. It decomposes your request into subtasks and dispatches them to specialized agents — Frontend, Backend, QA, and Infrastructure — that run in dependency order, verify each other's output, and stream progress to your phone as synthesized voice.

> **Self-hosted first.** Your keys, your data, your machine. No cloud account required beyond the AI provider APIs you already use.

---

## 🚀 Quick Start

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

**Step 5 → Remember.** Results are stored in GBrain (local knowledge graph). Next session starts with full context of everything you've built before.

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
          │ GBrain   │ │ Tools    │ │ Skills   │
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

## ✨ Features

### 🧠 Multi-Agent DAG Execution
Tasks are decomposed into subtasks and executed in dependency order by specialized agents — not a single monolithic prompt.

### 🎙️ Voice-First Phone Interface
Agent status updates stream as synthesized speech to a glassmorphic phone PWA. Speak commands, hear results, no terminal required.

### 🔄 Visual Self-Correction
Tap any element on the live browser preview from your phone. The DAG injects a corrective subtask, rolls back the stale agent's work, and re-executes with your feedback.

### 🗄️ Persistent Cross-Session Memory
GBrain knowledge graph stores every agent outcome, API contract, and learning. Next session starts with full context.

### 📊 Cost Transparency & Adaptive Routing
Real-time telemetry tracks token usage, latency, and spend per model. The [adaptive router](agents/adaptive_router.py) learns which models deliver best results per role and overrides defaults after enough data.

### 🛡️ Sandboxed Execution
Run agent code in Docker containers, E2B cloud sandboxes, or local — configurable via `JARVIS_SANDBOX_MODE`.

### 🏠 Fully Self-Hostable
Your keys, your data, your models. No cloud required. A single bootstrap script gets you running in minutes.

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
├── tools/                   # Shell, browser (Playwright), desktop automation, filesystem
├── phone/                   # Mobile PWA, console, telemetry dashboard, landing page
├── skills/                  # 419+ dynamically-loaded skill modules
├── tests/                   # 127 offline unit tests (JARVIS_CI=true stubs all external calls)
├── scripts/                 # bootstrap.sh, start_local.ps1, deploy_linux.sh
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
| `JARVIS_AGENT_TIMEOUT_SEC` | Max seconds per agent execution | `300` |
| `JARVIS_SANDBOX_MODE` | Code execution sandbox: `local`, `docker`, `e2b` | `local` |
| `JARVIS_CI` | Set to `true` to stub all external calls (for testing) | `false` |

See [`.env.example`](.env.example) for the complete list with descriptions.

---

## 🧪 Testing

All 127 tests run fully offline — no API keys, no network, no Docker required:

```bash
JARVIS_CI=true python -m pytest tests/ -v
```

`JARVIS_CI=true` stubs all LLM calls, GBrain queries, and browser automation with deterministic mock responses. CI runs automatically on every push via [GitHub Actions](.github/workflows/ci.yml).

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
4. **Test**: `JARVIS_CI=true python -m pytest tests/ -v` (all 127 tests should pass)
5. **Submit a PR** — CI runs the full suite automatically

See [CONTRIBUTING.md](CONTRIBUTING.md) for detailed guidelines.

---

## 📄 License

[Business Source License 1.1](LICENSE.txt) — free for non-competitive use. Converts to MPL 2.0 after 4 years.

---

<p align="center">
  <sub>Built with ❤️ by humans and agents working together.</sub>
</p>

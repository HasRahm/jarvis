# Jarvis — Personal AI Operating System

A Jarvis-style, always-on AI OS that decomposes complex tasks into a directed acyclic graph (DAG) of specialized agents, streams voice responses to your phone, and remembers everything across sessions via a local knowledge graph.

> **Self-hosted.** Your keys, your data, your machine. No cloud account required beyond the AI provider APIs you already use.

---

## What it does

- **Speaks to your phone** — streams synthesized voice over WebSocket to a glassmorphic phone PWA
- **Runs multi-agent workflows** — Frontend (Gemini), Backend (Claude), QA (GPT), IaC (Claude) agents collaborate on tasks you describe in plain English
- **Remembers across sessions** — GBrain knowledge graph stores every agent outcome, API contract, and learning
- **Self-corrects visually** — tap an element on the phone preview; the DAG heals itself automatically
- **Learns which models work** — adaptive router tracks success rates per role and overrides defaults after enough data

---

## Architecture

```
Phone PWA (phone/index.html)
    │  WebSocket :9000
    ▼
Hermes Bridge (core/hermes/server.py)   ← FastAPI + asyncio broadcaster
    │
    ├── Intent Classifier (gemma4:31b via Ollama)
    │
    └── DAG Orchestrator (core/orchestrator/dag.py)
            │
            ├── Frontend Agent  → gemini-3.1-pro-preview
            ├── Backend Agent   → claude-sonnet-4-6
            ├── QA Agent        → gpt-5.4  (fallback: claude, gemini)
            └── IaC Agent       → claude-sonnet-4-6
                    │
                    └── GBrain (local knowledge graph via Bun)
```

Agent coordination happens through `AGENTS.md` — a shared markdown file each agent reads and writes. No agent calls another agent's API directly.

---

## Prerequisites

| Requirement | Version | Notes |
|---|---|---|
| Python | 3.11+ | |
| [Ollama](https://ollama.ai) | latest | For `gemma4:31b-cloud` (the core brain) |
| [Bun](https://bun.sh) | latest | To run GBrain |
| Docker Desktop | latest | Optional — for sandboxed agent execution |
| API keys | — | Anthropic, Google Gemini, OpenAI |

---

## Quick Start

### 1. Clone and bootstrap

```bash
git clone https://github.com/YOUR_USERNAME/jarvis.git
cd jarvis
bash scripts/bootstrap.sh
```

This installs Bun, clones GBrain to `~/tools/gbrain`, creates a Python venv, installs all dependencies, and installs the Playwright Chromium browser.

### 2. Configure

```bash
cp .env.example .env
```

Edit `.env` and fill in:

```env
ANTHROPIC_API_KEY=sk-ant-...
GEMINI_API_KEY=...
OPENAI_API_KEY=sk-...
HERMES_SECRET=choose-a-strong-random-secret
JARVIS_PROJECT_ROOT=/absolute/path/to/this/repo
```

You also need to initialize GBrain:

```bash
cd ~/tools/gbrain
gbrain init        # follow the prompts (choose pglite for local-only)
cd -
```

### 3. Pull the Ollama model

```bash
ollama pull gemma4:31b-cloud
# or use any model supported by Ollama — update OLLAMA_HOST in .env
```

### 4. Start Jarvis

**Windows:**
```powershell
powershell -ExecutionPolicy Bypass -File scripts/start_local.ps1
```

**Linux / macOS:**
```bash
uvicorn core.hermes.server:app --host 0.0.0.0 --port 9000
```

### 5. Connect your phone

The start script launches a Cloudflare quick tunnel. The URL appears in the terminal. Open `https://<tunnel-url>/phone` on your phone, enter your `HERMES_SECRET` in Settings, and tap Connect.

---

## Run a task

From the phone PWA or any WebSocket client:

```json
{ "type": "auth", "token": "your-hermes-secret" }
```

Then send text:

```json
{ "text": "Build a REST API for a todo list with frontend" }
```

Jarvis decomposes this into agent subtasks, executes them in dependency order, streams voice updates to your phone, and stores the results in GBrain for future sessions.

---

## Run the tests

```bash
JARVIS_CI=true python -m pytest tests/ -v
```

All 37 tests pass offline — no API keys needed. `JARVIS_CI=true` stubs all LLM, GBrain, and browser calls.

---

## Project structure

```
jarvis/
├── core/
│   ├── hermes/          # WebSocket server, voice streaming, intent classifier
│   ├── orchestrator/    # DAG engine, task parser, context sync, distributed sync
│   ├── sync/            # Heartbeat watcher, GBrain migrate daemon
│   └── logging_config.py
├── agents/              # Base agent, specialized agents, model router, adaptive router
├── brain/               # GBrain query/write wrappers
├── tools/               # Shell, browser (Playwright), filesystem helpers
├── phone/               # Mobile PWA (index.html) + telemetry dashboard
├── scripts/             # bootstrap.sh, start_local.ps1, deploy_linux.sh, systemd units
├── tests/               # 37 offline unit tests
├── .env.example         # All configurable env vars documented
├── docker-compose.yml   # Sandboxed agent execution
├── Dockerfile           # Python + Bun + Playwright + Terraform image
└── requirements.txt
```

---

## Environment variables

See [`.env.example`](.env.example) for the full list with descriptions. Key ones:

| Variable | Description |
|---|---|
| `HERMES_SECRET` | Shared secret for phone WebSocket auth |
| `ANTHROPIC_API_KEY` | Claude API key |
| `GEMINI_API_KEY` | Google Gemini API key |
| `OPENAI_API_KEY` | OpenAI API key |
| `OLLAMA_HOST` | Ollama endpoint (default: `http://localhost:11434`) |
| `JARVIS_PROJECT_ROOT` | Absolute path to this repo (for Docker volume mount) |
| `JARVIS_CI` | Set to `true` to stub all external calls (for testing) |
| `JARVIS_DEBUG` | Set to `true` for DEBUG-level logs |
| `JARVIS_AGENT_TIMEOUT_SEC` | Max seconds a single agent.run() can take (default: 300) |
| `JARVIS_MAX_WS_MSG_BYTES` | Max WebSocket message size (default: 1 MB) |

---

## Linux VPS deployment

```bash
sudo bash scripts/deploy_linux.sh
```

This creates a `jarvis` system user, rsyncs the project to `/opt/jarvis`, installs the Python venv, and sets up two systemd services (`jarvis.service` + `jarvis-watcher.service`) with `Restart=on-failure`.

Then set up a named Cloudflare tunnel for a stable domain:

```bash
cloudflared tunnel login
cloudflared tunnel create jarvis
cloudflared tunnel route dns jarvis your-subdomain.your-domain.com
cloudflared tunnel run jarvis
```

---

## Phone PWA auth

The phone connects over WebSocket. The token is sent as the **first message** (never in the URL):

```js
ws.onopen = () => ws.send(JSON.stringify({ type: 'auth', token: HERMES_SECRET }));
```

The server responds with `{"type": "auth_ok"}`. Token storage in `localStorage` is separate from the URL so it never appears in browser history or proxy logs.

---

## Cost awareness

Each agent invocation calls real AI APIs that cost money. The telemetry dashboard at `http://localhost:9000/telemetry` shows cumulative spend, token usage, and per-model call counts. Set `JARVIS_AGENT_TIMEOUT_SEC` to limit runaway costs from hung agents.

---

## Contributing

1. Fork and clone
2. `bash scripts/bootstrap.sh`
3. `cp .env.example .env` and fill in keys
4. Run tests: `JARVIS_CI=true python -m pytest tests/ -v`
5. Open a PR — CI runs the full test suite automatically

---

## License

MIT

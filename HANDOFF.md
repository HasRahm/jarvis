# Jarvis Multi-Agent AI OS: Project Handoff & Architecture

> **Notice to future contributors/agents:** Read this entire file before making any changes. This documents the current state, architectural decisions, and next steps for the Jarvis OS project.

---

## What we are building
A Jarvis-style, always-on AI operating system that:
- Runs primarily using **`gemma4:31b-cloud`** (using an external endpoint/proxy) as the on-device brain.
- Has specialized agents per task domain (frontend, backend, database, QA, IaC), each using the best model for that job.
- Coordinates agents through a shared **`AGENTS.md`** protocol.
- Persists everything in **GBrain** (knowledge graph + hybrid vector search) so it remembers across sessions.
- Synced and accessible via phone via the Hermes protocol (Cloud VM fallback).

## Current Project State
The project is currently being developed on a **Windows** environment, meaning scripts are tailored for PowerShell and Git Bash compatibility.

### Phase 1: Core Loop (COMPLETED)
- **Directory**: `C:/Users/hasin/jarvis`
- **Virtual Environment**: Isolated `.venv` established.
- **Core Loop**: `core/gemma4_loop.py` serves as the CLI interface, parsing user text, determining tool calls, and maintaining context. 
- **Tooling**: Implementations for `filesystem.py`, `shell.py`, and a stub for `browser.py` are mapped to JSON schemas in `dispatcher.py`.
- **Model**: Hardcoded to utilize `gemma4:31b-cloud`. 

### Phase 2: Memory Layer (COMPLETED)
- **GBrain Setup**: `scripts/bootstrap.sh` handles installing `bun` natively on Windows and clones the third-party GBrain repository to `C:/Users/hasin/tools/gbrain` to avoid nested git repository issues.
- **Brain Tools**: `brain/query.py` and `brain/write.py` are built. They safely resolve the `gbrain` binary using `shutil.which` and fallback to `$USERPROFILE/.bun/bin/gbrain`.
- **Context Injection**: The core loop's system prompt strictly instructs the model to call `brain_query` before answering user prompts to guarantee persistent memory.
- **Maintenance**: Nightly consolidation is handled by `scripts/cron_dream.ps1`. A helper script, `scripts/register_cron.ps1`, hooks this into the native Windows Task Scheduler to run at 2:00 AM daily

### Phase 3: Hermes Bridge & Phone Access (COMPLETED)
- **Hermes Server**: `core/hermes/server.py` implements a FastAPI WebSocket server on port 9000, managing authenticated real-time voice and text streams.
- **Cloudflare Tunneling**: Fully automated quick tunnels via `cloudflared` to expose the local session securely without requiring domains or accounts.
- **Sync Daemons**: `core/sync/watcher.py` (60s heartbeats) and `core/sync/migrate.py` (utilizing robocopy and `gbrain migrate` to cleanly sync databases without corruption).
- **Phone UI**: Vanilla single-file PWA with robust Speech-to-Text and Text-to-Speech handling at `phone/index.html`.

### Phase 4: Multi-Agent IDE & Orchestrator (COMPLETED)
- **Task Decomposer & DAG Engine**: `core/orchestrator/task_parser.py` decomposes complex user tasks using `gemma4:31b-cloud` into atomic steps. `core/orchestrator/dag.py` builds the execution dependency graph, sorts subtasks topologically, and executes them in order.
- **Specialized Multi-Agent Suite**: Custom agents inheriting from `agents/base_agent.py` perform task domains: Frontend (`gemini-3.1-pro-preview`), Backend/DB (`claude-sonnet-4-6`), and QA/Verifier (`gpt-5.4` falling back dynamically to Claude/Gemini).
- **Hallucination Verification Layer**: Integrated a real-time verification loop using `gemini-2.5-flash-lite` in the QA Agent to review all generated test assertions against actual implementation contracts, filtering out hallucinated functions or endpoints.
- **Cross-Platform Resilience**: Optimized python imports to be fully **lazy**, resolved all Windows CP1252 code page print encoding crashes by utilizing ASCII status markers (`[PASS]`/`[FAIL]`), and built regex-based (`re.DOTALL`) JSON decorators to handle Windows CRLF newlines seamlessly.
- **Model Adaptations**: Configured OpenAI endpoints to dynamically map to `max_completion_tokens` on newer reasoning models, and scaled output token boundaries to `8192` to avoid truncation.

### Phase 5: Containerization & Sandboxed Tool Access (COMPLETED)
- **Docker Sandbox**: Built a custom Python, Bun, and Playwright debian-based container mapping the WSL2 native ext4 repository directly to `/workspace`.
- **Automatic Command Redirection**: Configured `tools/shell.py` to seamlessly detect host execution versus container execution (via `.dockerenv` and `JARVIS_SANDBOX_MODE='docker'`) and transparently delegate commands to the container environment securely.
- **Offline CI/CD Engine**: Configured integration tests to run with zero-cost offline mock handlers under `JARVIS_CI=true`, intercepting and stubbing downstream LLMs.
- **Automated Verification**: Established a fully functional GitHub Actions workflow in `.github/workflows/agent-ci.yml` that boots the container and verifies the orchestrator pipeline.

### Phase 6: Cloud-Native Infrastructure & Speech Upgrades (COMPLETED)
- **Model Router & IaC Agent:** Mapped `"iac": "claude-sonnet-4-6"` inside `agents/model_router.py` and created a dedicated `IacAgent` deploying sandboxed Terraform resources inside `/workspace`.
- **Terraform Integration:** Automatically unzipped and transferred the Linux Terraform CLI binary directly into the running sandbox container `/usr/local/bin/terraform` and granted execute bits.
- **Registry Concurrency Locks:** Engineered an atomic cross-platform `agents_md_lock` using Python's `fcntl` (WSL/Linux) and `msvcrt` (Windows) in `distributed_sync.py` to coordinate all `AGENTS.md` registry modifications.
- **Real-Time Voice Streaming:** Refactored the Hermes websocket to dynamically synthesize pop-free melodic PCM audio WAV frames mapped dynamically to textual response word segments.
- **Futuristic Glassmorphic PWA:** Upgraded the mobile interface with a custom sci-fi concentric canvas soundwave visualizer powered by `AnalyserNode` and sample-accurate browser-side queue playback scheduling.

### Phase 7: Operational Telemetry & Headless Visual Verification (COMPLETED)
- **Closed-Loop Visual Audits**: Integrated native Playwright headless browser screenshots and visual auditing using **`gemini-2.5-flash-lite`** (with automated fallback escalation to **`gemini-3.1-pro-preview`** for confidence scores `< 0.8`).
- **Telemetry Logger**: Wraps all LLM provider calls, capturing prompt/completion token usage and execution latency. All costs are mapped using current USD pricing structures, saved atomically under a local platform-agnostic file lock to `workspaces/telemetry.json` with an estimated freshness warning.
- **Glassmorphic Terminal Dashboard**: Exposes an elegant live `/telemetry` FastAPI endpoint serving metric widgets, animated progress bars, Outfit typography, and dynamic utilization doughnuts.
- **Robust Integration Test Suite**: Includes tests in `tests/test_telemetry_visual.py` verifying model pricing warning logs, visual audit mock triggers, and high-concurrency lock data integrity.

---

## Tech Stack
| Layer | Technology | Why |
|---|---|---|
| Core Brain | `gemma4:31b-cloud` | Fast, heavily adopted in prior (Anchor) evaluations. |
| Coordination | `AGENTS.md` (Protocol) | Markdown file each agent reads/writes for shared state. |
| Memory | GBrain | Hybrid search, knowledge graph. Runs locally via Bun. |
| Browser Tool | Playwright (Python) | Full browser automation (Chromium installed via bootstrap). |
| Specialized Models | Gemini 3.1 Pro, Claude 3.5 Sonnet, GPT-5 | Tailored performance per engineering domain. |
| Fact-Checker | Gemini 2.5 Flash Lite | Blazing fast, low-cost code review verification. |
| Sandbox | Docker Compose | Complete container-level execution isolation. |
| Speech Engine | Web Audio API / PCM wav | Low latency (zero-dependencies), browser-scheduled streaming. |
| Telemetry | Chart.js & Glassmorphic CSS | Futuristic operational insight & spend tracking terminal. |

---

## What Needs to be Built Next

### Phase 8: Multi-Modal Context-Aware Visual Interaction & Speech Sync (COMPLETED)
- **Interactive Visual Grounding**: Allow users to click/tap elements on the phone visualizer preview frame. Maps the relative click `(x, y)` coordinate ratios to precise CSS selectors in the DOM (with robust `nth-of-type` fallback pathing to prevent silent failures).
- **Unified Speech & Text Sync Queue**: Implemented `HermesEventManager` with a Python `asyncio.Queue` backend utilizing thread-safe event queuing from parallel agent worker threads to dispatch voice streaming alerts natively over the main websocket runner.
- **150ms Graceful Interrupt UX**: Re-engineered client audio queues to schedule Web Audio buffers with custom `GainNode` hooks, enabling a polished 150ms exponential volume fade-out instead of digital pops or raw clipping.
- **Visual Grounding Context Cap**: Maintains a sliding-window context history of the last 5 visual taps to feed pin-point coordinate targets directly into the frontend styling loops while avoiding context window bloat.

---

## What Needs to be Built Next

### Phase 9: Unified Context Sync & Model Self-Correction (COMPLETED)
- **Vocalized Agent Status History**: `HermesEventManager` now maintains a capped (10-entry) `speech_history` log. Each `enqueue_speech_sync` call accepts a `role_hint` parameter and timestamps the entry. Exposed via `get_speech_history()`.
- **Unified Model Attention Prompt**: `compile_converged_context()` in `context_sync.py` now blends all four signals — visual grounding tap history, vocalized speech history, telemetry spend, and AGENTS.md snapshot — into every agent's task prompt.
- **Speech Intent Detection & Auto-Healing**: `core/hermes/intent_classifier.py` classifies free-form user speech for correction intent using `gemma4:31b-cloud`. When intent is detected in the main WebSocket text handler, the DAG's `inject_corrective_subtask` is triggered automatically — no corrective popup required.
- **Workspace Rollback on STALE**: `ActiveOrchestrator` captures a workspace file snapshot before each agent runs (`_capture_snapshot`). In Case B (STALE re-queue), `_restore_snapshot` deletes all files the stale agent created before the corrective re-run starts. Rollback is logged to AGENTS.md.
- **Phone Auto-Heal Toast**: Phone PWA handles `auto_heal_detected` WebSocket messages with a 3-second glassmorphic toast overlay showing the healing intent and target element — no user action required.
- **Dead-Code Fix**: Added missing `_reset_agents_md()` definition in `dag.py` (was called but never defined).

### Phase 10: Adaptive Learning & Cross-Session Knowledge Persistence (COMPLETED)
- **GBrain Outcome Indexing**: `dag.py` writes two GBrain entries per run: a per-subtask record (`dag/<id>/<role>`) immediately after each successful agent step, and a full-run summary (`dag/<id>/summary`) upon COMPLETED status. Both are lazy-imported, CI-guarded, and wrapped in try/except.
- **Telemetry-Driven Adaptive Model Routing**: `agents/adaptive_router.py` tracks per-(role, model) success/failure counts in `workspaces/learned_preferences.json`. After `min_samples=5` calls with `success_rate > 0.6`, the router automatically overrides the default model for that role. File writes use `agents_md_lock` for TOCTOU safety. `base_agent.py` checks the adaptive override in `__init__` and records outcomes (success/failure) in `_raw_call`, all CI-guarded.
- **Contract Persistence to GBrain**: `backend_agent.py` writes the generated API contract to `contract/<task_id>` in GBrain after each successful run. `frontend_agent.py` queries GBrain for historical contracts (`brain_query("API contract endpoints for: {task}")`) before building its prompt, injecting matches as additional context for cross-session continuity.
- **Nightly Self-Improvement Pass**: `scripts/dream_analyze.py` reads `learned_preferences.json`, generates a CP1252-safe ASCII score summary, and stores it under `daily-summary/<date>` in GBrain. `scripts/cron_dream.ps1` now calls `dream_analyze.py` after `gbrain dream` completes. `scripts/register_cron.ps1` schedules this nightly at 2:00 AM.
- **Fallback Chains Populated**: `agents/model_router.py` now has fully-specified `_FALLBACKS` chains for all roles (previously empty lists), enabling multi-tier fallback when primary models are rate-limited.
- **7 New Tests**: `tests/test_phase10_adaptive.py` covers preference defaults, score accumulation, override threshold, below-minimum-samples guard, CI always-None guarantee, CP1252 summary safety, and DAG CI smoke test. All 32 unit tests pass.

### Phase 13: Multi-Tenancy Foundation (COMPLETED)
- **Per-Task Orchestrator Registry**: `dag.py` replaces the module-level `active_orchestrator` singleton with a thread-safe dict (`_orchestrators: dict[str, ActiveOrchestrator]` + `threading.Lock`). `register_orchestrator(task_id, orch)`, `get_orchestrator(task_id)`, and `unregister_orchestrator(task_id)` provide safe concurrent access. The module-level `active_orchestrator` is kept as a backward-compat pointer (always the most recently created instance) for single-user self-hosted mode.
- **Dual-Mode Auth**: New `core/auth.py` provides `authenticate(token) -> (bool, user_id | None)`. When `SUPABASE_JWT_SECRET` is set, validates Supabase JWTs and extracts `sub` as `user_id`. When unset, compares against `HERMES_SECRET` and returns `user_id=None` (self-hosted). `get_workspace_path(role, user_id)` and `get_agents_md_path(user_id)` return user-scoped paths in SaaS mode, plain paths in self-hosted mode.
- **User-Scoped Workspaces**: `BaseAgent.__init__` now accepts `user_id: str | None` and uses `get_workspace_path` / `get_agents_md_path` from `core.auth`. All AGENTS.md reads/writes go through `self._md_path` (a property that falls back to the module-level `AGENTS_MD_PATH` when `_agents_md_path` is not set, preserving backward compat for test subclasses that bypass `__init__`). `BackendAgent`, `FrontendAgent`, `QAAgent` each accept and forward `user_id=`.
- **User_id Propagation**: `run_dag(user_id=None)` threads `user_id` into `_get_agent_instance(role, user_id)` so each agent writes to an isolated `workspaces/<user_id>/<role>/` directory in SaaS mode.
- **WebSocket Auth Upgrade**: `hermes_endpoint()` now calls `core.auth.authenticate(token)` instead of comparing against `HERMES_SECRET` directly. `ConnectionState` gains `user_id: str | None` and `active_task_id: str | None` fields. Both corrective action handlers (`corrective_action` msg type and auto-heal) use `get_orchestrator(state.active_task_id)` instead of the global `active_orchestrator`.
- **E2B Sandbox Option**: New `tools/sandbox.py` wraps the `e2b-code-interpreter` SDK with `create_sandbox(task_id)` / `destroy_sandbox(sandbox, task_id)` / `run_in_sandbox(sandbox, cmd)`. All return `None` / no-op under `JARVIS_CI=true` or when `JARVIS_SANDBOX_MODE != "e2b"`. `run_dag()` provisions and destroys an E2B sandbox around the execution loop. `ActiveOrchestrator.sandbox` stores the sandbox object. `tools/shell.py` has a new `sandbox=` parameter and E2B execution branch before the existing Docker branch.
- **13 New Tests**: `tests/test_phase13_multitenant.py` — self-hosted auth (valid/invalid), Supabase JWT rejection, default secret fallback, workspace scoping (4 cases), concurrent orchestrator isolation, registry cleanup, E2B noop (3 cases). All 50 unit tests pass, 2 skipped (playwright).
- **Dependencies**: `requirements.txt` gains `PyJWT>=2.8.0` and `e2b-code-interpreter>=0.0.10`. `.env.example` gains `SUPABASE_JWT_SECRET`, `JARVIS_SANDBOX_MODE`, `E2B_API_KEY`.

### Phase 12: Multi-Client Robustness (COMPLETED)
- **Per-Connection State**: Added `ConnectionState` dataclass (`conn_id`, `event_queue`, `speech_history`, `visual_context_history`, `loop`) to `core/hermes/server.py`. Each WebSocket connection gets its own isolated instance.
- **Broadcaster Registry**: Refactored `HermesEventManager` from a single-queue singleton into a thread-safe registry (`_connections: dict[str, ConnectionState]`). `enqueue_speech_sync()` now broadcasts to **all** active connections simultaneously. Backward-compatible: `speech_history` is still a direct list attribute (Phase 9 tests use it); `set_loop()` is a documented no-op.
- **Per-Connection WebSocket Handler**: `hermes_endpoint` now creates a `ConnectionState`, calls `register()` at session start and `unregister()` in a `finally` block. `client_listener()` uses `state.visual_context_history` (isolated); `event_listener()` drains `state.event_queue` (isolated). `conn_id` prefix added to all log lines.
- **Input Size Protection**: `client_listener()` reads `JARVIS_MAX_WS_MSG_BYTES` (default 1 MB) per connection and immediately returns `{"type": "error"}` for oversized messages; connection stays open.
- **Agent Task Timeouts**: `core/orchestrator/dag.py` wraps both `agent.run()` calls (main loop + visual-retry loop) in a module-level `ThreadPoolExecutor`. A `FuturesTimeoutError` produces `{"status": "error", "output": "[TIMEOUT] …"}` rather than blocking forever. Configurable via `JARVIS_AGENT_TIMEOUT_SEC` (default 300 s).
- **Health Endpoint Extended**: `/health` now returns `active_connections` count alongside `status` and `service`.
- **5 New Tests**: `tests/test_phase12_robustness.py` — two-concurrent-auth, visual-history-isolation, broadcast-all-clients, agent-timeout, oversized-message-rejected. All 37 unit tests pass.
- **Import Cleanup**: Removed stale `_visual_context_history` from `test_hermes_sync.py` import (module-level global was replaced by per-connection state).

### Phase 11: Production Hardening (COMPLETED)
- **Dead Code Removed**: Deleted unreachable block in `dag.py` (lines 565–583) left from a prior refactor that referenced undefined variables after the real `return` statement.
- **Hardcoded Paths Eliminated**: `JARVIS_WSL_DISTRO`, `JARVIS_WSL_PROJECT_ROOT`, `JARVIS_WIN_PROJECT_ROOT` env vars now control WSL distro name and project root paths in `dag.py` and `tools/shell.py`. Defaults preserve existing behavior. `.env.example` updated.
- **WebSocket Auth Hardened**: Token moved from URL query string (`/ws?token=...`) to a first-message JSON handshake (`{"type":"auth","token":"..."}` → `{"type":"auth_ok"}`). Token never appears in server logs, browser history, or proxy access logs. Server closes with 1008 on bad token or 5s auth timeout.
- **HTTP Endpoint Auth**: `/api/telemetry` and `/api/browser/screenshot` now require `Authorization: Bearer <token>` header via a FastAPI `Depends` dependency. `/health`, `/phone`, `/telemetry` stay open.
- **CORS Configurable**: `JARVIS_CORS_ORIGINS` env var controls allowed origins. Defaults to `*` for local dev; set to your Cloudflare domain in production.
- **Unified Structured Logging**: `core/logging_config.py` provides `configure_logging(service_name)` — `RotatingFileHandler` (10 MB / 5 backups) + console handler with consistent format. All four startup modules (hermes, dag, watcher, migrate) now call it. `JARVIS_DEBUG=true` enables DEBUG level.
- **DAG Correlation IDs**: Each `run_dag()` call logs `[run_id]` prefix (last 8 chars of task_id) on start and per-subtask dispatch, enabling cross-log tracing.
- **Graceful Shutdown (Windows)**: `start_local.ps1` now uses `CloseMainWindow()` + 8s drain before force-kill for all three background processes.
- **Hermes Restart Loop (Windows)**: `start_local.ps1` retries Hermes startup up to 3 times with health-check polling (`/health` every 2s for up to 30s) before aborting.
- **Linux Deployment**: `scripts/jarvis.service` + `scripts/jarvis-watcher.service` (systemd units with `Restart=on-failure`, `SIGTERM` + 15s drain, append-mode log files) + `scripts/deploy_linux.sh` (idempotent setup: rsync, venv, systemd install, health check, Cloudflare named tunnel instructions).
- **Phone PWA Updated**: `connectWs()` now sends auth as the first WebSocket message. Settings panel has a dedicated password token field. Token stored in `localStorage['jarvis_token']`, separate from the URL.

### Phase 14: Mission Control HUD — Frontend Design System (COMPLETED)
- **Design System**: Three-page frontend built on a unified dark design system — `#060A14` background, `#3B82F6` blue / `#06B6D4` cyan / `#8B5CF6` purple accents, Inter + Space Grotesk typography, glassmorphism cards. All pages served from `phone/` on port 7890 via Python `http.server`.
- **SaaS Landing Page** (`phone/landing.html`): Full marketing page — fixed nav, hero with gradient headline + terminal preview block, stats row, 6-card feature grid, How It Works steps, 3-tier pricing (self-hosted / Pro / Team), final CTA, footer. Mobile breakpoint at 768px. Nav links to HUD and phone app.
- **Phone PWA** (`phone/index.html`): Complete UI overhaul — `#060A14` bg, topbar with settings + viewport toggle + Mission Control `⊞` link + animated status pill, slide-down settings drawer, 200×200 canvas visualizer, inline preview panel, chat with role labels, rounded-rect controls, auto-heal pill toast. All JS logic (WebSocket auth handshake, audio pipeline, speech recognition, corrective actions, visualizer) preserved unchanged.
- **Mission Control Design Canvas** (`phone/mission-control.html`): Claude Design export — three 1440×920 artboards in a scrollable design canvas with a Tweaks panel (5 palettes, 3 visualizer modes, 3 density levels, Live Mode toggle). All artboards run independent `useMissionControl` simulation engines with real-time DAG execution, auto-heal, and voice animation. Files: `mc-engine.jsx`, `mc-shared.jsx`, `mc-hud.jsx`, `mc-console.jsx`, `mc-spatial.jsx`, `mc-app.jsx`, `design-canvas.jsx`, `tweaks-panel.jsx`, `ios-frame.jsx`.
- **Production HUD** (`phone/hud.html`): Standalone Option A — HUD Cinematic — extracted from the design canvas, fills the full browser viewport via `window.innerWidth/Height` with a resize listener. First-time setup overlay captures server URL + HERMES_SECRET into `localStorage`. Settings gear (⚙) in bottom-right reopens config. Nav pill (top-right) links to landing, phone app, and design canvas. Live mode always ON after setup.
- **Real Backend Wiring** (`mc-engine.jsx`): `useMissionControl({ live })` — when `live=true`: (1) polls `/api/telemetry` every 5 s with Bearer auth, overlays real cost/calls/latency on HUD header metrics; (2) opens Hermes WebSocket with first-message auth handshake, maps `agent_speech` → transcript + voice visualizer, `auto_heal_detected` → heal toast. `wsStatus` state (`offline/connecting/online/error`) drives the connection dot in the HUD header. ENGAGE button dispatches real tasks via `wsRef.current.send({ text })` when WS is open — falls back to simulation otherwise.
- **Launch URL**: `http://localhost:7890/hud.html` (local) · `https://<tunnel>/hud.html` (remote).


### Phase 15: Intelligent Disk Cleanup (COMPLETED)
- **4-Stage Pipeline**: `tools/disk_cleanup.py` implements scan → safe_clean → judgment_scan → delete_judgment_item. Each stage is independent and idempotent.
- **Never-touch Guard**: `never_touch_check()` hard-blocks `C:\Windows`, `C:\Program Files`, the Jarvis project root, and Roaming\Microsoft from any deletion. Called before every removal.
- **Safe Auto-Clean** (`safe_clean(dry_run=True/False)`): Temp folders, INet/browser cache, Windows Update download cache, and Jarvis rotated log backups. `dry_run=True` is the default. Directory list is injectable via `_SAFE_CLEAN_DIRS` for test isolation. `PermissionError` on system dirs is caught and silently skipped.
- **Judgment Scan** (`judgment_scan()`): Flags (a) files >500 MB in user home, (b) Downloads items >90 days old, (c) stale `node_modules`/`.venv` dirs in projects with no recent git activity. Each candidate gets a one-sentence AI suggestion from Gemma via Ollama (`JARVIS_CI=true` skips LLM calls).
- **API Endpoints** (protected by `_require_token`): `GET /api/cleanup/scan`, `POST /api/cleanup/safe`, `GET /api/cleanup/judge`, `POST /api/cleanup/delete` (body: `{"path": "..."}` — rejects never-touch with 403).
- **CLI Script** (`scripts/cleanup.ps1`): Interactive menu (scan / safe / judge / delete <path>). Also callable as `.\scripts\cleanup.ps1 scan|safe|judge|delete <path>`.
- **Tests**: 19 tests in `tests/test_phase15_cleanup.py`, all passing. Covers never-touch guards, scan keys, dry_run safety, actual deletion, judgment list structure, and API rejection of never-touch paths.
- **Quick start**: `powershell -ExecutionPolicy Bypass -File scripts\cleanup.ps1`

## Important Architectural Rules

1. **`AGENTS.md` is the only shared state between agents.** Agents must not call each other's APIs directly.
2. **GBrain query before every response.** The system prompt enforces this. Do not remove it. Cold-start answers without memory context are considered a bug.
3. **External GBrain Dependency:** `gbrain` is a Bun-based CLI. It MUST remain outside the `jarvis` repository (`C:/Users/hasin/tools/gbrain`). 
4. **Environment Variables**: Managed in `.env.example`. Anthropic, Google, and OpenAI keys must be set to access downstream domain agents.
5. **Hermes Port**: Standardized on port **9000**. Do not use 8000 or 8080 (historically caused zombie process issues on Windows).
6. **GBrain CLI**: Use `gbrain put <slug> --content "<text>"` (the `--content` flag is mandatory). Use `gbrain migrate --to pglite` for database sync (never raw file copy — it corrupts PGLite).
7. **Cross-Platform Print Safety**: Never output Unicode icons like checkmarks (`✓`, `✗`) to stdout in orchestrator scripts. Keep all output strictly CP1252-safe.

## Bootstrapping Instructions for New Contributors
1. Run `bash scripts/bootstrap.sh` to install Bun, install GBrain globally, and setup Python dependencies.
2. Run `powershell -ExecutionPolicy Bypass -File scripts/register_cron.ps1` to schedule nightly memory grooming.
3. Configure your API keys in the `.env` file (Google Gemini, Anthropic Claude, OpenAI, and Gemma4 endpoints).
4. Start the system via `powershell -ExecutionPolicy Bypass -File scripts/start_local.ps1`.
5. Check `tunnel_err.log` for the Cloudflare tunnel URL, then open `https://<tunnel-url>/phone` on your phone.

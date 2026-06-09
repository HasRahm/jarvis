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

### Phase 16: Warp-Inspired Capability Handshake & Safety Monitor (COMPLETED)
- **Directory**: `core/system/` and `tests/`
- **Singleton Handshake Scanner**: `core/system/system_handshake.py` implements a thread-safe singleton `EnvironmentHandshake` that scans local platforms (Windows, Linux, WSL2), container sandboxing states, and target development binaries (`git`, `docker`, `npm`, `python3`, etc.).
- **Plan9 WSL2 Path Optimization**: To prevent massive Plan9 mount latencies or hangs when walking paths in WSL2, `shutil.which` filters out all `/mnt/` mounted paths under WSL/Linux, bringing scanning speed down to under **1 millisecond** (native speed).
- **Self-Deadlock RLock Resolution**: Configured cache access to utilize `threading.RLock()`. This resolved a critical self-deadlock where prompt injections and capability queries tried to re-acquire a standard, non-reentrant lock nestedly.
- **On-Demand Stat Verification**: Eliminated active background threading/watchdog observers, replacing them with a lazy stat check (`os.path.getmtime` on binary directories) only evaluated when `scan()` is called.
- **Output Safety Guardrails**: `core/system/safety_monitor.py` wraps terminal commands with real-time stream scanning (`select.select` and non-blocking `O_NONBLOCK` descriptors), auto-resolving port conflicts (PID termination of Jarvis-owned processes), pip/npm cache corruptions, and Playwright crashes, while immediately escalating Git authentication failures, DB locks, and permission violations outside `/workspace/`.
- **Decoupled Automated Tests**: Parametrized unit tests inside `tests/test_agent_enhancements.py` split into Tier A (static unit checks/handshake singleton verification) and Tier B (live integrations). Verified **100% green test passes** in WSL2 in **0.08 seconds** with zero API dependency or remote costs.
- **Console Slash Commands Integration**: Refactored `core/gemma4_loop.py` CLI to replicate every AI slash command in Warp (`/ask`, `/explain`, `/command`, `/edit`, `/clear`, `/help`). Added our unique performance commands: `/cleanup` (reclaims temp space), `/pc` or `/optimize` (auto-terminates duplicate background developer zombie processes to instantly free RAM and ports), `/telemetry` (tracks LLM spend), and `/agents` (shows active assignments).
- **Claude-Style Global CLI (`jarvis`)**: Created `scripts/register_cli.ps1` to register `jarvis` globally in the user's PowerShell profile. Typing `jarvis` from **any directory** automatically boots up all required background services (FastAPI Hermes server on port 9000, Cloudflare Tunnel, Sync Watcher) in unshaded mode before dropping the user directly into the interactive loop, managing graceful service termination on exit!
- **PowerShell Encoding & Format Sanitization**: Fully hardened `scripts/cleanup.ps1` with 100% ASCII compliance, single-quoted string formatting variables (preventing brace parser collisions), and environment variable piping (eliminating backslash escapes). Successfully ran auto-clean, clearing **6.47 GB of disk space** with 100% safety.

### Phase 17: Modular Skills Engine & Closed-Loop Visual Servo Controller (COMPLETED)
- **Modular Skills System:** Recursively scanned and extracted **2,233 files** and **407 skills** from the dynamic developer skills catalog into `skills/`. Developed `core/system/skills.py` (the dynamic keywords matching engine) which tokenizes user tasks, calculates word intersections against skill metadata, and transparently appends the top 3 matching skills' instructions directly to the system prompt of all specialized execution agents.
- **Closed-Loop Visual Servo Controller:** Designed a real-time proportional trajectory controller in `tools/visual_servo.py` (`pyautogui` + OpenCV + Pillow) that continuously calculates course-correcting cursor coordinates down to **$< 1.0\text{px}$ convergence thresholds**, resisting screen offsets, scroll shifting, and layout jitter.
- **Robust Hover-State & High-DPI Scaling Failsafes:** Engineered a last-known target coordinate buffer memory to glide safely through visual color changes during hover-state transitions (e.g., close buttons turning red on hover) and window-maximization routines (`Win+Up`) to completely eliminate High-DPI display scaling discrepancies.
- **Systems Hardening & Defect Mitigation:** 
  - **Ollama Decomposer Robustness:** Hardened `core/orchestrator/task_parser.py` with dynamic `re.search` bracket matching to cleanly extract JSON arrays from conversational Ollama preambles and bypassed dynamic skills injection on the `orchestrator` parser to prevent prompt clutter.
  - **Model Fallbacks:** Added model overrides to `.env` (like `AGENT_MODEL_FRONTEND=claude-sonnet-4-6`) to bypass gRPC hanging and rate-limiting issues on the Gemini SDK.
  - **Namespace Collision Fix:** Resolved a critical package namespace collision inside `workspaces/qa/tests/test_api_top_stories.py` by aliasing the imported Hacker News scraper submodule to `top_stories_module`, allowing integration tests to pass 100% green.
  - **CLI EOFError Guard:** Added comprehensive `EOFError` handling to the core CLI shell `core/gemma4_loop.py` to prevent infinite logging loops on piped stdin streams.
- **Core Desktop Automation Toolset:** Created `tools/desktop_automation.py` containing human-like smooth mouse glides, natural cadence typing, hotkey execution, and smooth wheel scrolling. Natively integrated `visual_servo_click` and all four desktop automation tools directly into the core `tools/dispatcher.py` (`TOOL_DEFINITIONS` and `dispatch`), equipping all Jarvis CLI shells and execution agents with native, built-in capabilities to execute closed-loop GUI automation on the host desktop for any task.

### Phase 18: End-to-End GUI Automation Verification & CLI Robustness (COMPLETED)
- **Direct CLI Path Resolution:** Inserted parent directory path resolution into `sys.path` within `core/gemma4_loop.py` to allow the Jarvis interactive loop to resolve the `tools` namespace flawlessly when launched directly or piped via external commands.
- **Closed-Loop GUI Verification:** Successfully verified and executed automated end-to-end integration tests using local Ollama (`gemma4:31b-cloud`) and native GUI automation tools (`pyautogui`). Piped live prompts directly through the Jarvis OS terminal CLI loop, launching Notepad, dynamically typing text with human-like cadence pauses, and executing smooth scrolling actions on the host Windows desktop without generating transient/custom Python scripts.
- **Piped Mode Stability:** Hardened EOF handles to cleanly terminate interactive sessions on end-of-file, enabling pipeline script validation and high-reliability headless script auditing.
- **Target Location Verification & Window Focusing:** Integrated native window management tools (`desktop_get_active_window` and `desktop_focus_window` utilizing `pygetwindow`) into `tools/desktop_automation.py` and the dispatcher registry. Fully equipped the AI brain with the ability to safely query active foreground applications, restore/maximize minimized targets, and focus overlapping or stacked windows, preventing target collision and blind-typing corruption.
- **CP1252-Safe Terminal Print Encoding:** Hardened the window detection tools to filter out non-ASCII/CP1252 character maps (e.g. zero-width spaces `\u200b` and emojis) to prevent terminal print crashes on Windows.
- **Visual Validation Suite:** Added robust test cases in `tests/test_desktop_windows.py` achieving 100% green coverage for graphical context verification, window matching, and focus transitions.
- **Startup Deadlock Resilience:** Completely refactored core imports (`ollama` and `playwright.sync_api` headless tools) to be localized and lazily evaluated at runtime. This prevents silent background thread deadlocks (e.g., hung `ollama` local servers or native Win32 `greenlet` thread crashes during headless browser init) from permanently freezing the `jarvis-cli.py` interactive shell or API runner on initialization.
- **Contextual On-the-Fly Skills Injection:** Natively integrated the dynamic `SkillsEngine` directly into `core/gemma4_loop.py`. Whenever the user enters a prompt, Jarvis tokenizes it on-the-fly, matches keywords against all 407 custom developer skills, and injects the top 3 corresponding skill instruction manuals directly into the loop's system context, preventing agent confusion or stuck states.
- **Lossless System-Wide Unicode Escape Failsafes:** Wrapped all dynamic console prints inside `core/gemma4_loop.py` (both final responses and tool-call variables) with dynamic system encoding maps and `'replace'` fallback handlers. This prevents complex emojis (`🎨`), special shapes (`🎯`), or foreign character sets matched from skill files or computed by LLMs from throwing fatal CP1252 / `charmap` crashes in the Windows command line, achieving 100% execution resilience.

### Phase 19: Zero-Config Auto-Connect & Vercel Deployment (COMPLETED)
- **Vercel Deployment**: All frontend pages deployed to https://jarvis-henna-nu.vercel.app — auto-deploys on every `git push` to master. Pages: `/` (landing), `/hud` (Mission Control), `/phone` (PWA), `/console` (Console 2.0).
- **GitHub Gist as Discovery Beacon**: `scripts/start_jarvis.ps1` publishes `{url, token, status}` to Gist `e99532bb52fd6b67e77f759d9921d5d8` on every startup. Frontend reads Gist on every load — phone or desktop opens the HUD and auto-connects with zero manual config.
- **Token in Gist**: Startup script reads `$env:HERMES_SECRET` (falls back to `"jarvis_hermes_2026"`) and includes it in the Gist payload. Frontend uses `data.token || 'jarvis_hermes_2026'` fallback so it auto-connects even before the first restart publishes the token.
- **`discoverConfig()` in both frontends**: `phone/hud.html` and `phone/index.html` both call the Gist on load, auto-save `hermesUrl` + `hermesToken` to `localStorage`, and connect silently. Setup overlay only appears as a last resort (PC offline + no localStorage).
- **WSS conversion**: `phone/index.html` converts the HTTP tunnel URL to `wss://...` for the WebSocket connection automatically.
- **Startup script** (`scripts/start_jarvis.ps1`): Hermes health-check loop (15×2s), cloudflared tunnel URL extraction from stderr log, Gist update via `gh gist edit`, offline payload on Ctrl+C.
- **Auto-start**: `jarvis.bat` in Windows Startup folder runs the script on every login automatically.

### Phase 20: useApi Constructor & HUD Storage Panel (COMPLETED)
- **`useApi(method, path)` hook** in `phone/mc-engine.jsx`: Reusable REST event-caller constructor. Returns `{ data, loading, error, call, setData, reset }`. Reads `hermesUrl`/`hermesToken` from localStorage on every `call()` so credentials are always fresh. Sets `Authorization: Bearer` header automatically. Catches both network errors and non-2xx HTTP responses. Exported via `Object.assign(window, {..., useApi})`.
- **HUD Storage Panel** (Panel 07 in `phone/mc-hud.jsx`): Auto-scans `/api/cleanup/scan` on mount and displays TEMP / CACHE / SAFE disk totals. `SAFE CLEAN` button shows a confirmation dialog then calls `POST /api/cleanup/safe` and displays freed MB. `SCAN ITEMS` button calls `GET /api/cleanup/judge` and renders a scrollable candidate list with per-item `DEL` buttons (inline loading state, optimistic list removal). Re-scans disk totals after every action. All errors shown inline in red without affecting the rest of the HUD.
- **Bottom strip extended**: HUD bottom strip changed from 2 columns (`1.4fr 1fr`) to 3 columns (`1.2fr 0.8fr 1fr`) — DAG · LOG · STORAGE.

### Phase 21: Jarvis Console 2.0 Redesign (COMPLETED)
- **Design source**: Implemented from a Claude Design bundle (`hXz3WaJBNGlQDx4W6SwOuA`) — warm Claude/Manus-inspired aesthetic replacing the neon-blue HUD as the primary daily-driver console.
- **Design system** (`phone/console.html`): Warm ivory canvas (`#ECE9E0`) + clay accent (`#C2603C`), near-monochrome. Three fonts: Newsreader (serif display), Hanken Grotesk (UI), JetBrains Mono (code). Light + dark mode, 3 density levels, 3 accent options via Tweaks panel. Fully responsive (rail collapses to icons, workspace hides on mobile).
- **Component files** (all prefixed `j2-` to avoid conflicts with `mc-*` HUD files):
  - `j2-shared.jsx` — icons, Logo, Pulse dot, `greeting()` helper
  - `j2-data.jsx` — mock domain data + scripted run timeline (simulation fallback)
  - `j2-dag.jsx` — animated agent execution DAG: SVG bezier edges recomputed via `ResizeObserver`, per-node running/done states with glow
  - `j2-workspace.jsx` — Plan / Files / Preview / Activity tabbed right panel
  - `j2-thread.jsx` — streaming conversation thread with word-by-word typing animation + composer
  - `j2-home.jsx` — greeting + composer + suggestion chips + recent runs
  - `j2-pages.jsx` — Runs history, Memory (GBrain), Storage (live Hermes cleanup endpoints), Settings (reads real localStorage creds)
  - `j2-app.jsx` — nav rail + router + run simulation engine + Tweaks panel wiring
- **Live Hermes integration**: Storage page calls `/api/cleanup/scan`, `/api/cleanup/safe` directly. Settings page shows real `hermesUrl`/`hermesToken` from localStorage.
- **Navigation**: Landing page and HUD nav both link to `console.html`. Nav pill on console links back to landing + HUD + phone.
- **Live URL**: https://jarvis-henna-nu.vercel.app/console

### Phase 22: API Hardening, Streaming & LinkedIn Outreach Tools (COMPLETED)
- **pyautogui lazy import fix** (`tools/desktop_ui_tree.py`): Removed module-level `import pyautogui` that caused dispatcher to hang on startup when `desktop_automation` was already loaded in `sys.modules`. Import now happens lazily inside `desktop_interact_with_element()` only.
- **`.env` auto-load in `jarvis-cli.py`**: Added pre-subprocess `.env` parsing so all API keys are available to Hermes subprocesses regardless of launch context.
- **Streaming + tool chunking in `llm_adapter.py`** (user-rewritten): Replaced all LLM HTTP calls with `httpx.stream()` for chunked request bodies and SSE stream parsing — eliminates silent 600s hangs on slow/unavailable models. Added `_select_relevant_tools()` that caps tool definitions at `MAX_TOOLS=32` per request using keyword scoring.
- **LinkedIn outreach script** (`scratch/linkedin_outreach.py`): Uses non-headless Playwright (`headless=False`, `slow_mo=120ms`) with anti-webdriver flag and natural mouse scrolling to bypass LinkedIn bot detection. Uses Google `site:linkedin.com/in` search to avoid login walls. Streaming `gpt-4o` for all message generation. Output: `workspaces/outreach/tampa-engineers.json` (3 Tampa AI/ML engineers, personalized <300 char messages).
- **Full codebase API hardening** (5 files patched):
  - `agents/base_agent.py`: Added `timeout=90.0` to OpenAI + Anthropic clients; added `http_options=HttpOptions(timeout=90000)` to Google genai client; added streaming (`stream=True`) to OpenAI calls; switched ollama to `ollama.Client(timeout=90)`.
  - `agents/qa_agent.py`: Added `HttpOptions(timeout=90000)` to genai client in visual verifier.
  - `core/system/llm_adapter.py`: Removed hardcoded NVIDIA API key fallback (security fix); added OpenRouter routing branch for `openrouter/` prefix models and `OPENROUTER_MODEL` env var.
  - `agents/model_router.py`: `get_provider()` now logs a warning instead of silently returning `"unknown"` for unmapped models.
  - `core/hermes/hermes_cli_runner.py`: Added `.env` self-load at top so runner works standalone (not just via jarvis-cli.py subprocess).

### Phase 22d: visual_inspect — Vision AI Screen Reading (COMPLETED)
- **Problem solved**: `screen_ocr` (pytesseract) is blind to WebGL/canvas-rendered UIs. Figma Community, Electron app main content, and browser SPA content return zero useful text — only the HTML sidebar nav is readable. This caused an infinite retry loop where the agent retyped "pokemon app theme" 5 times because OCR kept returning unchanged sidebar text.
- **Solution**: `tools/visual_inspect.py` (new) — captures screen via mss, resizes to 1280px wide (cost control), base64-encodes, POSTs to **Anthropic Vision API** (`claude-sonnet-4-6`). Falls back to **Gemini 2.0 Flash** vision if `ANTHROPIC_API_KEY` is missing. Returns natural-language description with approximate `(x, y)` coordinates for UI elements.
- **How Claude Computer Use / Codex Operator solve this**: They are multimodal — screenshots go directly to the vision model. `visual_inspect` is the same bridge for Jarvis: local text model (gemma4) acts as the brain, Claude Vision acts as the eyes.
- **Usage**: `visual_inspect("What Pokemon designs are shown in the Figma Community search results?")` → Claude Vision returns: "I can see 6 design cards: 'Pokémon GO UI Kit' at (180,320), 'Pokemon App Design Kit' at (420,320)..."
- **`modes/desktop.md` updated**: Added `visual_inspect` to tool table + "When OCR Fails" section with critical rule: "If `screen_ocr` returns only sidebar/nav text after an action, do NOT retry. Call `visual_inspect` instead."
- **`tools/dispatcher.py` updated**: Added tool schema (27 tools total), `_CORTEX_EXEMPT`, dispatch case.
- **Live test confirmed**: Claude Vision correctly described the Cursor IDE screen, active chat session title, model being used, and files being edited — proving canvas/electron content is fully readable.

### Phase 22c: Mouse Braille Cursor + Verification Loop (COMPLETED)
- **Root cause fixed — wrong window bug**: UIAutomation `WalkControl()` bleeds across window boundaries — with Figma focused, it still returned the Windows Taskbar's `SearchButton` (AutoID=SearchButton, y=1008) because the accessibility tree is not scoped to the foreground HWND. Confirmed via `scratch/desktop_ui_cache.json` index 0.
- **Layer 2 replaced — Mouse Braille** (`tools/hybrid_cursor.py`): Old `_layer2_braille()` (WalkControl UIAutomation tree) replaced by `_layer2_mouse_braille(target, window_node)`. Uses `auto.ControlFromPoint(x, y)` to probe a grid of points **inside the target window's pixel bounds** — like a finger reading braille. Probe coordinates are clamped to `[wx+5..wx+ww-5, wy+35..wy+wh-5]`, so the taskbar (y≈1008) can never be probed. Two-pass scan: coarse (60px step, top 40% of window) then fine (25px step, full window). On match, cursor is already at target — click immediately.
- **Layer 1 extended**: `_layer1_graph_focus()` now returns 3-tuple `(ok, msg, window_node)`. `window_node` carries `{x, y, w, h}` from the Win32 window graph for use by Layer 2b bounds.
- **Verification loop added** (`tools/hybrid_cursor.py`): `hybrid_locate_click()` now accepts `verify_text` and `max_retries` params. After each successful click, `_verify_outcome()` checks: (1) `ScreenImprintGraph` density delta vs. pre-click baseline (fast, ~100ms/frame), (2) `_check_text_on_screen()` OCR scan for expected text. On failure: retries the full Layer 1→2b→3 sequence up to `max_retries` times.
- **Pre-click baseline**: `hybrid_locate_click` captures a screen imprint snapshot before each click attempt and passes it as `pre_action_imprint` to `_verify_outcome`, ensuring changes during the click itself are detected (not just post-seeding).
- **`_check_text_on_screen(text, min_conf)`**: New helper — OCR screen check without clicking; used by verification loop.
- **Speed improvement**: ControlFromPoint (~1ms/call) vs full WalkControl tree (2-5s). Coarse pass finds top-of-window elements (toolbars, search bars) typically in <10 probes.
- **`tools/dispatcher.py`**: Updated `hybrid_locate_click` tool definition to add `verify_text` and `max_retries` params; updated `description` to reflect Mouse Braille; updated dispatch call to pass new params.

### Phase 22b: Hybrid Cursor Location System & Dispatcher Bug Fixes (COMPLETED)
- **`tools/hybrid_cursor.py`** (new): `hybrid_locate_click(target, window_hint)` — 3-layer cursor system:
  - **Layer 1 (Graph)**: `get_3d_window_graph()` verifies the target window exists in the Win32 stack; `desktop_focus_window()` brings it to front; `desktop_get_active_window()` confirms focus succeeded. On focus failure, **skips Layer 2 entirely** (UIAutomation on wrong window causes infinite loops) and jumps to Layer 3.
  - **Layer 2 (Braille)**: `desktop_get_ui_tree(search_query=target)` queries UIAutomation on the now-confirmed foreground window; reads freshly-written `scratch/desktop_ui_cache.json`; finds exact then partial name match; calls `desktop_interact_with_element(index)`.
  - **Layer 3 (OCR)**: `mss` screenshot (bypasses `/workspace` Docker path issue of `desktop_screenshot()`) + `pytesseract.image_to_data(DICT)`; supports single-word (exact conf>50, partial conf>30) and multi-word targets (adjacent same block+line tokens, min conf>30, click bounding-box center).
- **`screen_ocr` bug fixed** (`tools/dispatcher.py`): Was calling async `JarvisScreenReader().read_all_text()` synchronously — returned a coroutine object. Replaced with direct `mss` + `pytesseract` sync implementation returning `{raw_text, words[]}`.
- **`get_window_stack` bug fixed** (`tools/dispatcher.py`): Was calling async `JarvisScreenReader().read_window_stack()`. Replaced with `tools.windows.get_window_stack()` (existing sync ctypes Win32 implementation).
- **Tool registered**: `hybrid_locate_click` added to `TOOL_DEFINITIONS`, `_CORTEX_EXEMPT`, and `_dispatch_raw()` in `dispatcher.py`.

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

---

## Agent Handoff (Claude Code)
If you are picking up this workspace context, here are the immediate next steps and context:
1. **Figma Design System:** Screen 1 (`Phone Main`) was successfully drawn via `gpt-5.4` desktop automation. **Screens 2-5 (`Phone Agents`, `Phone Voice Active`, `Desktop Terminal`, `Design Tokens`) are pending.** Please assist the user in completing these designs.
2. **Desktop Automation Blockers Fixed:** The background `jarvis-cli.py` thread deadlocks (caused by `ollama` local routing hanging on headless browser tool imports) have been fully fixed and decoupled. Desktop tooling can now run safely.
3. **Current Active Run:** Jarvis is currently executing a live LinkedIn outreach generation script in the background. Do not kill or restart `jarvis-cli.py` while the mouse is moving!

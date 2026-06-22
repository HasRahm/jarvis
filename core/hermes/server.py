import sys
from core.trace import trace as _jtrace
import os
import json
import logging
import math
import struct
import io
import wave
import asyncio
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from dotenv import load_dotenv

from core.logging_config import configure_logging
configure_logging("hermes")
logger = logging.getLogger(__name__)

# Load environment variables
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
load_dotenv(os.path.join(project_root, ".env"))

app = FastAPI(title="Jarvis Hermes Bridge")

def print_qr_code(tunnel_url: str):
    """Print QR code for instant phone pairing."""
    try:
        import qrcode
        qr = qrcode.QRCode(border=1)
        qr.add_data(tunnel_url)
        qr.make(fit=True)
        
        print("\n⚡ JARVIS — scan to connect from phone\n")
        qr.print_ascii(invert=True)
        print(f"\n  URL: {tunnel_url}\n")
    except ImportError:
        _jtrace(f"[TRACE] core.hermes.server.print_qr_code: except ImportError")
        logger.warning("[Server] qrcode package not installed, skipping terminal QR.")
        print(f"\n⚡ JARVIS Connection URL: {tunnel_url}\n")

# Initialize and run the GoalScheduler background daemon
goal_scheduler = None

@app.on_event("startup")
async def startup_event():
    _jtrace(f"[TRACE] core.hermes.server.startup_event: enter")
    global goal_scheduler
    try:
        from core.system.goal_scheduler import GoalScheduler
        goal_scheduler = GoalScheduler(check_interval_sec=60.0)
        goal_scheduler.start()
        logger.info("[Server] GoalScheduler started successfully.")
    except Exception as e:
        _jtrace(f"[TRACE] core.hermes.server.startup_event: except {str(e)[:80]}")
        logger.error(f"[Server] Failed to start GoalScheduler: {e}")

    # Generate QR Code on startup
    tunnel_url = os.getenv("CLOUDFLARE_TUNNEL_URL")
    if not tunnel_url:
        import httpx
        try:
            # Fallback to gist discovery
            resp = httpx.get("https://gist.githubusercontent.com/HasRahm/e99532bb52fd6b67e77f759d9921d5d8/raw/jarvis-url.json", timeout=3)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("status") == "online":
                    tunnel_url = data.get("url")
        except Exception as e:
            _jtrace(f"[TRACE] core.hermes.server.startup_event: except {str(e)[:80]}")
            logger.debug(f"[Server] Gist discovery failed: {e}")
            
    if tunnel_url:
        # Convert http(s) to ws(s) if we are connecting from a phone websocket client
        ws_url = tunnel_url.replace("http", "ws") + "/ws"
        print_qr_code(ws_url)

@app.on_event("shutdown")
async def shutdown_event():
    _jtrace(f"[TRACE] core.hermes.server.shutdown_event: enter")
    global goal_scheduler
    if goal_scheduler:
        try:
            goal_scheduler.stop()
            logger.info("[Server] GoalScheduler stopped successfully.")
        except Exception as e:
            _jtrace(f"[TRACE] core.hermes.server.shutdown_event: except {str(e)[:80]}")
            logger.error(f"[Server] Error stopping GoalScheduler: {e}")

# Auth is enforced via core.auth.authenticate() (call-time, fail-closed) in both
# _require_token (HTTP) and the /ws handler — no module-level secret constant.

# CORS — restrict origins in production via JARVIS_CORS_ORIGINS env var
_raw_origins = os.getenv("JARVIS_CORS_ORIGINS", "*")
_cors_origins = [o.strip() for o in _raw_origins.split(",")] if _raw_origins != "*" else ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=(_raw_origins != "*"),
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type"],
)

# Mount Slack channel spoke
from core.hermes.channels.slack import router as slack_router
app.include_router(slack_router, prefix="/api/channels/slack", tags=["slack"])



async def _require_token(authorization: str = Header(default="")) -> None:
    """FastAPI dependency: enforces Bearer token auth on protected HTTP endpoints.

    Routes through core.auth.authenticate so HTTP and the WebSocket handler share
    one fail-closed, call-time validator (reads HERMES_SECRET fresh each request).
    """
    _jtrace(f"[TRACE] core.hermes.server._require_token: enter")
    token = authorization.removeprefix("Bearer ").strip()
    if not token:
        raise HTTPException(status_code=401, detail="Authorization header required")
    from core.auth import authenticate
    ok, _ = authenticate(token)
    if not ok:
        raise HTTPException(status_code=403, detail="Forbidden")


def generate_voice_chunk(word: str, duration: float = 0.18, sample_rate: int = 16000) -> bytes:
    """
    Synthesize a clean, high-fidelity scicentric/melodic WAV soundwave
    for a specific word, avoiding pop noises and utilizing frequency modulation.
    """
    # A pleasant pentatonic scale for melodic futuristic synth feedback
    _jtrace(f"[TRACE] core.hermes.server.generate_voice_chunk: enter")
    frequencies = [261.63, 293.66, 329.63, 392.00, 440.00, 523.25, 587.33, 659.25]
    idx = len(word.strip(".,!?\"'()")) % len(frequencies)
    frequency = frequencies[idx]

    num_samples = int(sample_rate * duration)
    samples = []

    for i in range(num_samples):
        t = i / sample_rate
        # Smooth exponential amplitude decay envelope to prevent pops or clicks
        if t < 0.015:
            envelope = t / 0.015
        else:
            envelope = math.exp(-5.0 * (t - 0.015) / duration)

        # Subtle frequency wobble (vibrato) for a more premium organic synth tone
        vibrato = 1.0 + 0.02 * math.sin(2 * math.pi * 9 * t)

        # Scale to 16-bit integer, capping amplitude at 25% to prevent clipping distortion
        val = int(32767 * 0.25 * envelope * math.sin(2 * math.pi * frequency * vibrato * t))
        samples.append(val)

    wav_io = io.BytesIO()
    with wave.open(wav_io, "wb") as wav_file:
        wav_file.setnchannels(1)     # Mono channel
        wav_file.setsampwidth(2)     # 16-bit depth
        wav_file.setframerate(sample_rate)
        # Pack PCM integers as little-endian short structures
        binary_data = struct.pack(f"<{len(samples)}h", *samples)
        wav_file.writeframes(binary_data)

    return wav_io.getvalue()


async def get_jervis_voice_response(user_text: str) -> str:
    """Resolve text response from Ollama cloud/local model or return robust fallback."""
    _jtrace(f"[TRACE] core.hermes.server.get_jervis_voice_response: enter")
    if os.environ.get("JARVIS_CI") == "true":
        return f"Greetings. I am Jarvis. I have processed your input: '{user_text}'. All voice telemetry links are fully operational."

    system_content = "You are Jarvis, a helpful, ultra-concise assistant. You are integrated into Jarvis OS and have direct access to local files and system commands via agentic pipelines. For instance, you can perform disk cleanup (scanning C:\\Windows\\Temp, user downloads, and caches) using the Storage HUD panel. Answer in one or two sentences max, friendly voice."

    try:
        from core.system.llm_adapter import call_llm
        import asyncio
        messages = [
            {"role": "system", "content": system_content},
            {"role": "user", "content": user_text}
        ]
        loop = asyncio.get_running_loop()
        response = await loop.run_in_executor(
            None,
            lambda: call_llm(messages, model="gemma4:31b-cloud")
        )
        return response.get("content", "") if isinstance(response, dict) else str(response)
    except Exception as e:
        _jtrace(f"[TRACE] core.hermes.server.get_jervis_voice_response: except {str(e)[:80]}")
        logger.warning(f"Voice response model execution failed: {e}. Executing fast synth offline fallback.")
        return f"Telemetry received. Connection established and running smoothly. Awaiting next command."


# ---------------------------------------------------------------------------
# Phase 12: Per-connection state + broadcaster registry
# ---------------------------------------------------------------------------

@dataclass
class ConnectionState:
    """Holds all mutable state for a single active WebSocket client."""
    conn_id: str
    event_queue: asyncio.Queue = field(default_factory=asyncio.Queue)
    speech_history: list = field(default_factory=list)
    visual_context_history: list = field(default_factory=list)
    loop: asyncio.AbstractEventLoop = None
    user_id: str | None = None          # None in self-hosted mode; set in SaaS mode
    active_task_id: str | None = None   # tracks which DAG run this connection is watching


class HermesEventManager:
    """
    Thread-safe broadcaster registry.  Maintains one ConnectionState per active
    WebSocket client and broadcasts speech events to all of them simultaneously.

    Backward-compatibility guarantees (Phase 9 tests rely on these):
      * self.speech_history  — module-level fallback list written on every
                               enqueue_speech_sync() call, so context_sync.py
                               and tests that access the attribute directly keep working.
      * self.loop            — settable no-op attribute (test code does
                               ``mgr.loop = mock.MagicMock()``; no AttributeError).
      * set_loop(loop)       — kept as an explicit no-op; loop is now stored
                               per-ConnectionState, not on the manager.
    """

    def __init__(self):
        self._connections: dict = {}          # conn_id -> ConnectionState
        self._lock = threading.Lock()
        # Backward-compat legacy speech history (always updated, even with no connections)
        self.speech_history: list = []
        self.loop = None                       # legacy no-op attribute

    # --- Registry ---

    def register(self, state: ConnectionState) -> None:
        with self._lock:
            self._connections[state.conn_id] = state

    def unregister(self, conn_id: str) -> None:
        with self._lock:
            self._connections.pop(conn_id, None)

    def get_active_count(self) -> int:
        with self._lock:
            return len(self._connections)

    # --- Backward-compat no-op ---

    def set_loop(self, loop) -> None:
        """No-op: retained for backward compatibility. Loop is now per-ConnectionState."""
        pass

    # --- Broadcast to all active connections ---

    def enqueue_speech_sync(self, text: str, interrupt: bool = False, role_hint: str = "system") -> None:
        """Thread-safe: push a speech event to every active connection's asyncio queue."""
        _jtrace(f"[TRACE] core.hermes.server.HermesEventManager.enqueue_speech_sync: enter")
        entry = {
            "text": text,
            "role": role_hint,
            "ts": datetime.now(tz=timezone.utc).isoformat(),
            "interrupt": interrupt,
        }
        event = {"type": "agent_speech", "text": text, "interrupt": interrupt}

        # Update manager-level history (backward compat + headless / no-phone mode)
        self.speech_history.append(entry)
        if len(self.speech_history) > 10:
            self.speech_history.pop(0)

        with self._lock:
            targets = list(self._connections.values())

        for state in targets:
            if state.loop is None:
                continue
            # Per-connection history
            state.speech_history.append(entry)
            if len(state.speech_history) > 10:
                state.speech_history.pop(0)
            try:
                asyncio.run_coroutine_threadsafe(state.event_queue.put(event), state.loop)
            except Exception as _e:
                _jtrace(f"[TRACE] core.hermes.server.HermesEventManager.enqueue_speech_sync: except {str(_e)[:80]}")
                logger.warning(f"[hermes] Failed to enqueue speech for {state.conn_id}: {_e}")

    # --- Generic event broadcast (DAG lifecycle, screenshot, etc.) ---

    def enqueue_event(self, event: dict) -> None:
        """Broadcast any arbitrary event dict to all active connections.
        Used by dag.py to push dag_update / task_status events in real-time.
        Thread-safe; no-op when no clients are connected."""
        _jtrace(f"[TRACE] core.hermes.server.HermesEventManager.enqueue_event: enter")
        with self._lock:
            targets = list(self._connections.values())
        for state in targets:
            if state.loop is None:
                continue
            try:
                asyncio.run_coroutine_threadsafe(state.event_queue.put(event), state.loop)
            except Exception as _e:
                _jtrace(f"[TRACE] core.hermes.server.HermesEventManager.enqueue_event: except {str(_e)[:80]}")
                logger.warning(f"[hermes] enqueue_event failed for {state.conn_id}: {_e}")


hermes_event_manager = HermesEventManager()


# ---------------------------------------------------------------------------
# DAG dispatch backpressure (review finding #7)
# ---------------------------------------------------------------------------
# Without a cap, each `run_task` WebSocket message spawns an unbounded daemon thread, so a client
# (or a reconnect storm) can launch overlapping orchestrations that exhaust CPU/memory and corrupt
# each other's state. We enforce a per-user concurrency cap and a global ceiling; over-limit
# dispatches are rejected with a clear status instead of silently piling up.
class _DagDispatchLimiter:
    def __init__(self):
        self._lock = threading.Lock()
        self._per_user: dict = {}     # user_id (or conn id) -> active count
        self._total = 0

    @property
    def per_user_cap(self) -> int:
        return max(1, int(os.getenv("JARVIS_MAX_CONCURRENT_DAGS_PER_USER", "1")))

    @property
    def global_cap(self) -> int:
        return max(1, int(os.getenv("JARVIS_MAX_CONCURRENT_DAGS", "8")))

    def try_acquire(self, key: str) -> tuple[bool, str]:
        """Reserve a slot for `key` (a user_id or connection id). Returns (ok, reason)."""
        with self._lock:
            if self._total >= self.global_cap:
                return False, f"server at capacity ({self._total}/{self.global_cap} tasks running)"
            cur = self._per_user.get(key, 0)
            if cur >= self.per_user_cap:
                return False, (f"you already have {cur} task(s) running "
                               f"(limit {self.per_user_cap}); wait for it to finish")
            self._per_user[key] = cur + 1
            self._total += 1
            return True, ""

    def release(self, key: str) -> None:
        with self._lock:
            if self._per_user.get(key, 0) > 0:
                self._per_user[key] -= 1
                if self._per_user[key] == 0:
                    self._per_user.pop(key, None)
            if self._total > 0:
                self._total -= 1


_dag_limiter = _DagDispatchLimiter()


def get_visual_context_history() -> list:
    """Returns the most-recently-authenticated client's visual tap history (or [] if none)."""
    _jtrace(f"[TRACE] core.hermes.server.get_visual_context_history: enter")
    with hermes_event_manager._lock:
        if hermes_event_manager._connections:
            return list(hermes_event_manager._connections.values())[-1].visual_context_history
    return []


def get_speech_history() -> list:
    """Retrieve vocalized agent status history (last 10 entries, manager-level fallback)."""
    return hermes_event_manager.speech_history


# ---------------------------------------------------------------------------
# HTTP endpoints
# ---------------------------------------------------------------------------

@app.get("/api/browser/screenshot")
async def get_browser_screenshot(_: None = Depends(_require_token)):
    """Returns the current full-page Playwright screenshot as an image."""
    _jtrace(f"[TRACE] core.hermes.server.get_browser_screenshot: enter")
    from fastapi.responses import JSONResponse
    # Check both Docker container path and local Windows workspace path
    candidate_paths = [
        "/workspace/workspaces/browser/screenshot.png",
        os.path.join(project_root, "workspaces", "browser", "screenshot.png"),
    ]
    for screenshot_path in candidate_paths:
        if os.path.exists(screenshot_path):
            return FileResponse(screenshot_path, media_type="image/png")
    return JSONResponse({"error": "No screenshot available"}, status_code=404)


@app.get("/health")
async def health_check():
    """Health check endpoint for watcher.py and cloud load balancers."""
    return {
        "status": "ok",
        "service": "jarvis-hermes",
        "active_connections": hermes_event_manager.get_active_count(),
    }


# ---------------------------------------------------------------------------
# WebSocket endpoint
# ---------------------------------------------------------------------------

@app.websocket("/ws")
async def hermes_endpoint(websocket: WebSocket):
    """Bidirectional streaming WebSocket endpoint for Hermes voice protocol."""
    _jtrace(f"[TRACE] core.hermes.server.hermes_endpoint: enter")
    await websocket.accept()

    # First-message auth handshake — token never travels in the URL
    try:
        raw = await asyncio.wait_for(websocket.receive_text(), timeout=5.0)
        msg = json.loads(raw)
        # Phase 13: dual-mode auth (Supabase JWT in SaaS, HERMES_SECRET in self-hosted)
        from core.auth import authenticate
        _ok, _user_id = authenticate(msg.get("token", ""))
        if msg.get("type") != "auth" or not _ok:
            logger.warning("Rejected WebSocket: invalid auth token.")
            await websocket.close(code=1008, reason="Unauthorized")
            return
    except asyncio.TimeoutError:
        _jtrace(f"[TRACE] core.hermes.server.hermes_endpoint: except TimeoutError")
        logger.warning("Rejected WebSocket: auth handshake timed out.")
        await websocket.close(code=1008, reason="Auth timeout")
        return
    except Exception as _e:
        _jtrace(f"[TRACE] core.hermes.server.hermes_endpoint: except {str(_e)[:80]}")
        logger.warning(f"Rejected WebSocket: auth parse error: {_e}")
        await websocket.close(code=1008, reason="Auth error")
        return

    await websocket.send_text(json.dumps({"type": "auth_ok"}))

    # Per-connection state (Phase 12: multi-client isolation; Phase 13: user identity)
    conn_id = str(uuid.uuid4())[:8]
    state = ConnectionState(
        conn_id=conn_id,
        loop=asyncio.get_running_loop(),
        user_id=_user_id,
    )
    hermes_event_manager.register(state)
    logger.info(
        f"[{conn_id}] Authenticated user_id={_user_id or 'self-hosted'}. "
        f"Active: {hermes_event_manager.get_active_count()}"
    )

    async def client_listener():
        # Input size limit (Phase 12): configurable via JARVIS_MAX_WS_MSG_BYTES
        _jtrace(f"[TRACE] core.hermes.server.hermes_endpoint.client_listener: enter")
        _MAX_MSG_BYTES = int(os.environ.get("JARVIS_MAX_WS_MSG_BYTES", str(1 * 1024 * 1024)))
        try:
            while True:
                data = await websocket.receive_text()

                # Reject oversized messages before any JSON parsing
                if len(data.encode()) > _MAX_MSG_BYTES:
                    logger.warning(f"[{conn_id}] Oversized message rejected: {len(data)} chars")
                    await websocket.send_text(json.dumps({"type": "error", "message": "Message too large"}))
                    continue

                try:
                    payload = json.loads(data)
                    msg_type = payload.get("type")
                except Exception:
                    _jtrace(f"[TRACE] core.hermes.server.hermes_endpoint.client_listener: except Exception")
                    payload = {}
                    msg_type = None

                if msg_type == "visual_interaction":
                    coords = payload.get("coords", {})
                    x_ratio = coords.get("x", 0.5)
                    y_ratio = coords.get("y", 0.5)

                    # Import browser tools to resolve the element selector pathway
                    from tools.browser import browser_resolve_element_at_coords
                    result = browser_resolve_element_at_coords(x_ratio, y_ratio)

                    # Manage active visual grounding context per connection (sliding window of 5)
                    record = {
                        "selector": result.get("selector", "body"),
                        "tag_name": result.get("tag_name", "BODY"),
                        "classes": result.get("classes", []),
                        "inner_text": result.get("inner_text", "")
                    }
                    state.visual_context_history.append(record)
                    if len(state.visual_context_history) > 5:
                        state.visual_context_history.pop(0)

                    logger.info(f"[{conn_id}] Visual grounding updated: {state.visual_context_history}")

                    # Interrupt active playback
                    await websocket.send_text(json.dumps({"type": "interrupt", "interrupt": True}))

                    # Queue a helpful spoken selection acknowledgment
                    target_selector = result.get("selector", "element")
                    announcement = f"I've grounded my focus to the UI element at {target_selector}."

                    await websocket.send_text(json.dumps({"type": "text_start"}))
                    await websocket.send_text(json.dumps({"type": "text", "content": announcement}))
                    words = announcement.split()
                    for word in words:
                        audio_frame = generate_voice_chunk(word)
                        await websocket.send_bytes(audio_frame)
                        await asyncio.sleep(0.16)
                    await websocket.send_text(json.dumps({"type": "done"}))

                elif msg_type == "corrective_action":
                    coords = payload.get("coords", {})
                    x_ratio = coords.get("x", 0.5)
                    y_ratio = coords.get("y", 0.5)
                    instruction = payload.get("instruction", "")

                    # BROWSER NAMING Comment (Correction #3):
                    # NOTE: "client_browser" = phone PWA Web Audio API
                    # "playwright_browser" = headless Chromium in sandbox
                    # Never confuse these two contexts.

                    # Pause PWA client playback (send audio_interrupt frame to client_browser)
                    await websocket.send_text(json.dumps({"type": "audio_interrupt", "interrupt": True}))

                    # Resolve coordinates to structural selectors via playwright_browser
                    from tools.browser import browser_resolve_element_at_coords
                    result = browser_resolve_element_at_coords(x_ratio, y_ratio)
                    selector = result.get("selector", "body")

                    # Manage active visual grounding context per connection (sliding window of 5)
                    record = {
                        "selector": selector,
                        "tag_name": result.get("tag_name", "BODY"),
                        "classes": result.get("classes", []),
                        "inner_text": result.get("inner_text", "")
                    }
                    state.visual_context_history.append(record)
                    if len(state.visual_context_history) > 5:
                        state.visual_context_history.pop(0)

                    # Phase 13: look up this connection's orchestrator (falls back to most-recent)
                    from core.orchestrator.dag import get_orchestrator
                    _orch = get_orchestrator(state.active_task_id)
                    if _orch:
                        _orch.inject_corrective_subtask(selector, instruction)

                    # Queue spoken acknowledgment of interruption/self-correction
                    announcement = f"Self correction triggered for element {selector}. Pivot execution started."
                    await websocket.send_text(json.dumps({"type": "text_start"}))
                    await websocket.send_text(json.dumps({"type": "text", "content": announcement}))
                    words = announcement.split()
                    for word in words:
                        audio_frame = generate_voice_chunk(word)
                        await websocket.send_bytes(audio_frame)
                        await asyncio.sleep(0.16)
                    await websocket.send_text(json.dumps({"type": "done"}))

                elif msg_type == "run_task":
                    # HUD / Mission Control dispatches a DAG task here
                    user_text = payload.get("text", "").strip()
                    if not user_text:
                        continue
                    logger.info(f"[{conn_id}] DAG task dispatch: '{user_text[:80]}'")
                    import uuid as _uuid
                    from core.orchestrator.dag import run_dag
                    _task_id = _uuid.uuid4().hex
                    _user_id_capture = state.user_id
                    # Backpressure: cap concurrent orchestrations per user (and globally) so a
                    # client can't spawn overlapping run_dag threads. Key by user_id in SaaS mode,
                    # else by connection id for self-hosted.
                    _limit_key = _user_id_capture or conn_id
                    _ok, _reason = _dag_limiter.try_acquire(_limit_key)
                    if not _ok:
                        logger.warning(f"[{conn_id}] DAG dispatch rejected (backpressure): {_reason}")
                        await websocket.send_text(json.dumps({
                            "type": "task_status",
                            "status": "REJECTED",
                            "reason": _reason,
                        }))
                        continue
                    state.active_task_id = _task_id

                    def _run_dag_thread(_text=user_text, _tid=_task_id, _uid=_user_id_capture, _key=_limit_key):
                        try:
                            run_dag(_text, task_id=_tid, user_id=_uid)
                        except Exception as _exc:
                            _jtrace(f"[TRACE] core.hermes.server.hermes_endpoint.client_listener._run_dag_thread: except {str(_exc)[:80]}")
                            logger.error(f"[{conn_id}] run_dag error: {_exc}")
                            hermes_event_manager.enqueue_event({
                                "type": "task_status",
                                "status": "FAILED",
                                "error": str(_exc),
                            })
                        finally:
                            _dag_limiter.release(_key)

                    threading.Thread(target=_run_dag_thread, daemon=True, name=f"dag-{_task_id[:8]}").start()

                else:
                    user_text = payload.get("text", data) if payload else data
                    logger.info(f"[{conn_id}] Received PWA transmission: '{user_text}'")

                    # Check for correction intent before answering conversationally
                    from core.hermes.intent_classifier import classify_correction_intent
                    heal = classify_correction_intent(user_text, state.visual_context_history)
                    if heal:
                        selector = heal["selector"]
                        instruction = heal["instruction"]
                        from core.orchestrator.dag import get_orchestrator
                        _orch = get_orchestrator(state.active_task_id)
                        if _orch:
                            _orch.inject_corrective_subtask(selector, instruction)
                        await websocket.send_text(json.dumps({
                            "type": "auto_heal_detected",
                            "element": selector,
                            "intent": instruction
                        }))
                        hermes_event_manager.enqueue_speech_sync(
                            f"Detected a correction request. Healing {selector} now.",
                            interrupt=True,
                            role_hint="system"
                        )
                        # Skip normal conversational response — correction acknowledged via voice
                        continue

                    # Asynchronously fetch Jarvis textual response
                    response_text = await get_jervis_voice_response(user_text)
                    words = response_text.split()

                    # Signal stream start
                    await websocket.send_text(json.dumps({"type": "text_start"}))

                    # Stream words and coordinate synthesized audio frames
                    for word in words:
                        clean_word = word.strip()
                        if not clean_word:
                            continue

                        # Stream text word chunk
                        await websocket.send_text(json.dumps({"type": "text", "content": word + " "}))

                        # Synthesize corresponding melodic binary frame
                        audio_frame = generate_voice_chunk(clean_word)
                        await websocket.send_bytes(audio_frame)

                        # Smooth pacing sleep to align stream chunk playback pacing
                        await asyncio.sleep(0.16)

                    # Signal stream end
                    await websocket.send_text(json.dumps({"type": "done"}))

        except WebSocketDisconnect:
            _jtrace(f"[TRACE] core.hermes.server.hermes_endpoint.client_listener: except WebSocketDisconnect")
            logger.info(f"[{conn_id}] PWA client disconnected.")
            raise

    async def event_listener():
        try:
            while True:
                event = await state.event_queue.get()
                event_type = event.get("type", "")

                if event_type == "agent_speech":
                    # Speech events: stream word-by-word with synthesised audio
                    text = event.get("text", "")
                    interrupt = event.get("interrupt", False)
                    if interrupt:
                        await websocket.send_text(json.dumps({"type": "interrupt", "interrupt": True}))
                    words = text.split()
                    await websocket.send_text(json.dumps({"type": "text_start"}))
                    for word in words:
                        clean_word = word.strip()
                        if not clean_word:
                            continue
                        await websocket.send_text(json.dumps({"type": "text", "content": word + " "}))
                        audio_frame = generate_voice_chunk(clean_word)
                        await websocket.send_bytes(audio_frame)
                        await asyncio.sleep(0.16)
                    await websocket.send_text(json.dumps({"type": "done"}))
                else:
                    # DAG lifecycle events (task_status, dag_update, auto_heal_detected, etc.)
                    # Forward directly as JSON — the HUD/phone react to these in onmessage
                    await websocket.send_text(json.dumps(event))

                state.event_queue.task_done()
        except asyncio.CancelledError:
            _jtrace(f"[TRACE] core.hermes.server.hermes_endpoint.event_listener: except CancelledError")
            pass
        except Exception as e:
            _jtrace(f"[TRACE] core.hermes.server.hermes_endpoint.event_listener: except {str(e)[:80]}")
            logger.error(f"[{conn_id}] Hermes event listener exception: {e}")

    try:
        await asyncio.gather(client_listener(), event_listener())
    except WebSocketDisconnect:
        _jtrace(f"[TRACE] core.hermes.server.hermes_endpoint: except WebSocketDisconnect")
        logger.info(f"[{conn_id}] Phone disconnected from Hermes Bridge.")
    except Exception as e:
        _jtrace(f"[TRACE] core.hermes.server.hermes_endpoint: except {str(e)[:80]}")
        logger.error(f"[{conn_id}] WebSocket session exception: {e}")
        try:
            await websocket.close(code=1011)
        except Exception:
            _jtrace(f"[TRACE] core.hermes.server.hermes_endpoint: except Exception")
            pass
    finally:
        hermes_event_manager.unregister(conn_id)
        logger.info(f"[{conn_id}] Connection cleaned up. Active: {hermes_event_manager.get_active_count()}")


@app.post("/api/notify")
async def post_notification(body: dict, _: None = Depends(_require_token)):
    """Allows posting a system speech/text notification to all connected clients."""
    _jtrace(f"[TRACE] core.hermes.server.post_notification: enter")
    text = body.get("text", "").strip()
    if not text:
        raise HTTPException(status_code=422, detail="Missing 'text' in request body")
    hermes_event_manager.enqueue_speech_sync(text, role_hint="system")
    return {"status": "success", "notified_text": text}


# ---------------------------------------------------------------------------
# Cleanup API endpoints (Phase 15)
# ---------------------------------------------------------------------------

@app.get("/api/cleanup/scan")
async def cleanup_scan(_: None = Depends(_require_token)):
    """Stage 1 — Return disk usage survey by category."""
    _jtrace(f"[TRACE] core.hermes.server.cleanup_scan: enter")
    from tools.disk_cleanup import scan
    return scan()


@app.post("/api/cleanup/safe")
async def cleanup_safe(_: None = Depends(_require_token)):
    """Stage 2 — Run safe auto-clean (dry_run=False, no confirmation needed for always-safe dirs)."""
    _jtrace(f"[TRACE] core.hermes.server.cleanup_safe: enter")
    from tools.disk_cleanup import safe_clean
    return safe_clean(dry_run=False)


@app.get("/api/cleanup/judge")
async def cleanup_judge(_: None = Depends(_require_token)):
    """Stage 3 — Return judgment-needed candidates with AI suggestions."""
    _jtrace(f"[TRACE] core.hermes.server.cleanup_judge: enter")
    from tools.disk_cleanup import judgment_scan
    return judgment_scan()


@app.post("/api/cleanup/delete")
async def cleanup_delete(body: dict, _: None = Depends(_require_token)):
    """Stage 4 — Delete a single path approved by the user from /api/cleanup/judge.

    Body: {"path": "C:\\...\\something"}
    Never-touch paths are rejected with 403.
    """
    _jtrace(f"[TRACE] core.hermes.server.cleanup_delete: enter")
    from fastapi import HTTPException
    from tools.disk_cleanup import delete_judgment_item, never_touch_check
    path = body.get("path", "").strip()
    if not path:
        raise HTTPException(status_code=422, detail="Missing 'path' in request body")
    if never_touch_check(path):
        raise HTTPException(status_code=403, detail="Path is in the never-touch list and cannot be deleted.")
    result = delete_judgment_item(path)
    if not result["deleted"] and result["error"]:
        raise HTTPException(status_code=500, detail=result["error"])
    return result


# ---------------------------------------------------------------------------
# Telemetry & phone endpoints
# ---------------------------------------------------------------------------

# Serve the phone PWA
phone_dir = os.path.join(project_root, "phone")


@app.get("/api/telemetry")
async def get_telemetry_api(_: None = Depends(_require_token)):
    """Returns aggregated agent execution telemetry and costs."""
    _jtrace(f"[TRACE] core.hermes.server.get_telemetry_api: enter")
    import json
    from core.orchestrator.distributed_sync import agents_md_lock

    # Check both Docker container path and local Windows workspace path
    for _candidate in [
        "/workspace/workspaces/telemetry.json",
        os.path.join(project_root, "workspaces", "telemetry.json"),
    ]:
        if os.path.exists(_candidate):
            telemetry_path = _candidate
            break
    else:
        telemetry_path = None
    if not telemetry_path:
        return {
            "total_calls": 0,
            "total_cost": 0.0,
            "avg_latency": 0.0,
            "models": {},
            "history": []
        }

    with agents_md_lock(telemetry_path + ".lock"):
        try:
            with open(telemetry_path, "r", encoding="utf-8") as f:
                records = json.load(f)
        except Exception as e:
            _jtrace(f"[TRACE] core.hermes.server.get_telemetry_api: except {str(e)[:80]}")
            logger.error(f"Error loading telemetry records: {e}")
            records = []

    total_calls = len(records)
    total_cost = sum(r.get("cost_usd", 0.0) for r in records)
    avg_latency = sum(r.get("latency_sec", 0.0) for r in records) / total_calls if total_calls > 0 else 0.0

    model_counts = {}
    for r in records:
        m = r.get("model", "unknown")
        model_counts[m] = model_counts.get(m, 0) + 1

    return {
        "total_calls": total_calls,
        "total_cost": round(total_cost, 4),
        "avg_latency": round(avg_latency, 3),
        "models": model_counts,
        "history": records[-50:]
    }


@app.get("/telemetry")
async def serve_telemetry():
    """Serve the telemetry dashboard directly to run on same origin."""
    return FileResponse(os.path.join(phone_dir, "telemetry.html"))


@app.get("/phone")
async def serve_phone():
    """Serve the phone PWA directly to run on same origin."""
    return FileResponse(os.path.join(phone_dir, "index.html"))


@app.get("/hud")
async def serve_hud():
    """Serve the Mission Control HUD."""
    return FileResponse(os.path.join(phone_dir, "hud.html"))


@app.get("/design")
async def serve_design():
    """Serve the Mission Control design canvas."""
    return FileResponse(os.path.join(phone_dir, "mission-control.html"))


@app.get("/landing")
async def serve_landing():
    """Serve the landing page."""
    return FileResponse(os.path.join(phone_dir, "landing.html"))


@app.get("/architecture")
async def serve_architecture():
    """Serve the full system architecture diagram."""
    return FileResponse(os.path.join(phone_dir, "architecture.html"))


# Mount phone directory at root so relative asset paths (mc-engine.jsx, etc.) resolve correctly.
# FastAPI evaluates explicit routes first, so /ws /api/* /health etc. are unaffected.
app.mount("/", StaticFiles(directory=phone_dir), name="phone-static")


if __name__ == "__main__":
    import uvicorn
    # For dev, run with port 9000
    uvicorn.run("core.hermes.server:app", host="0.0.0.0", port=9000, reload=False)

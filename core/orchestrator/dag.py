"""
DAG Orchestrator — builds and executes a directed acyclic graph of agent tasks.

Uses gemma4:31b-cloud (via task_parser) to decompose user tasks,
then executes agents in topological order respecting dependencies.
Updates AGENTS.md at each step.
"""

import sys
import os
import json
import logging
import argparse
import threading
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from datetime import datetime
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from core.orchestrator.task_parser import parse_task
from agents.base_agent import AGENTS_MD_PATH
from core.auth import get_agents_md_path, get_workspace_path
from core.logging_config import configure_logging
from core.cli import run_events as ev


def _agents_md_path(user_id: str | None = None) -> str:
    """Resolve the AGENTS.md coordination file, scoped per-user in SaaS mode.

    user_id=None → the project-root AGENTS.md (self-hosted; identical to AGENTS_MD_PATH).
    user_id set  → workspaces/<user_id>/AGENTS.md so concurrent SaaS users never share state.
    """
    return get_agents_md_path(user_id)

configure_logging("dag")
logger = logging.getLogger(__name__)

# Phase 12: Agent task timeout — prevents a hung LLM/Playwright call from blocking the DAG
_agent_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="jarvis-agent")
_AGENT_TIMEOUT_SEC = int(os.environ.get("JARVIS_AGENT_TIMEOUT_SEC", "300"))  # 5 min default


def _push_hermes_event(event: dict) -> None:
    """Push a DAG lifecycle event to all live Hermes connections.
    CI-safe (no-op when JARVIS_CI=true). Non-fatal on any error."""
    if os.environ.get("JARVIS_CI") == "true":
        return
    try:
        from core.hermes.server import hermes_event_manager
        hermes_event_manager.enqueue_event(event)
    except Exception as _he:
        logger.debug(f"[dag] Hermes event push skipped: {_he}")


def _topological_sort(subtasks: list[dict]) -> list[dict]:
    """Sort subtasks in dependency order (topological sort)."""
    graph = {st["id"]: st["depends_on"] for st in subtasks}
    task_map = {st["id"]: st for st in subtasks}

    in_degree = defaultdict(int)
    for task_id in graph:
        in_degree[task_id] = len(graph[task_id])

    # Start with tasks that have no dependencies
    queue = [tid for tid in graph if in_degree[tid] == 0]
    result = []

    while queue:
        current = queue.pop(0)
        result.append(task_map[current])

        # Reduce in-degree for dependents
        for tid, deps in graph.items():
            if current in deps:
                in_degree[tid] -= 1
                if in_degree[tid] == 0:
                    queue.append(tid)

    if len(result) != len(subtasks):
        remaining = [st["id"] for st in subtasks if st not in result]
        raise ValueError(f"Circular dependency detected! Unresolved: {remaining}")

    return result


def _get_agent_instance(role: str, user_id: str | None = None):
    """Instantiate the right agent class for a role.

    user_id is passed to the agent so it can scope its workspace and AGENTS.md
    to the correct user directory in SaaS mode (Phase 13).
    """
    if role == "backend" or role == "database":
        # Phase 41: the database role reuses the BackendAgent (it already writes SQL migrations +
        # publishes the contract); the DB-focused subtask text steers it. Its model is resolved
        # per-role via model_router, so 'database' can route differently from 'backend'.
        from agents.backend_agent import BackendAgent
        agent = BackendAgent(user_id=user_id)
        if role == "database":
            from agents.model_router import get_model, get_provider, get_api_key
            agent.role = "database"
            agent.model = get_model("database")
            agent.provider = get_provider(agent.model)
            agent.api_key = get_api_key(agent.provider)
        return agent
    elif role == "frontend":
        from agents.frontend_agent import FrontendAgent
        return FrontendAgent(user_id=user_id)
    elif role == "qa":
        from agents.qa_agent import QAAgent
        return QAAgent(user_id=user_id)
    elif role == "research":
        # Research routes to a SkillAgent (research skill) when available, else the backend agent.
        try:
            from agents.skill_agent import SkillAgent
            from core.system.skills import SkillsEngine
            name = next((s["name"] for s in SkillsEngine().skills
                         if "research" in (s.get("name") or "").lower()), None)
            if name:
                return SkillAgent(name, user_id=user_id)
        except Exception as e:
            logger.warning(f"[dag] research SkillAgent unavailable ({e}); using backend agent")
        from agents.backend_agent import BackendAgent
        return BackendAgent(user_id=user_id)
    else:
        raise ValueError(f"Unknown agent role: {role}")


def _reset_agents_md(task_id: str, user_task: str, user_id: str | None = None):
    """Initialize AGENTS.md for a fresh task run (per-user in SaaS mode)."""
    # Single source of truth (Phase 46): the per-agent model column is built from the SAME router
    # as /agents (model_router.get_model), so AGENTS.md and /agents can never disagree.
    from agents.model_router import get_model
    rows = "".join(
        f"| {role} | {get_model(role)} | IDLE | --- |\n"
        for role in ("frontend", "backend", "qa", "iac")
    )
    content = (
        "# AGENTS.md - Shared Agent State\n\n"
        "## Current Task\n"
        "| Field | Value |\n"
        "|-------|-------|\n"
        f"| Task ID | {task_id} |\n"
        f"| Description | {user_task[:120]} |\n"
        "| Status | IN_PROGRESS |\n"
        "| Requested By | orchestrator |\n\n"
        "## Agent Assignments\n"
        "| Agent | Model | Status | Current Step |\n"
        "|-------|-------|--------|-------------|\n"
        f"{rows}\n"
        "## Task Log\n"
    )
    try:
        with open(_agents_md_path(user_id), "w", encoding="utf-8") as f:
            f.write(content)
    except Exception as e:
        logger.warning(f"Could not reset AGENTS.md: {e}")


def log_to_agents_md(message: str, user_id: str | None = None):
    """Appends a log line to AGENTS.md Task Log (per-user in SaaS mode)."""
    path = _agents_md_path(user_id)
    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception:
        content = ""

    log_line = f"- [{datetime.now().strftime('%Y-%m-%d %H:%M')}] {message}\n"
    if "## Task Log" in content:
        content = content.replace("## Task Log\n", f"## Task Log\n{log_line}")
    else:
        content += f"\n## Task Log\n{log_line}"

    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
    except Exception:
        pass

class ActiveOrchestrator:
    def __init__(self):
        self.reset()
        
    def reset(self):
        self.active_agent = None
        self.active_subtask = None
        self.execution_list = []
        self.current_index = -1
        self.is_running = False
        self.is_interrupted = False
        self.results = []
        self.all_files = []
        self.user_task = ""
        self.task_id = ""
        self.snapshots = {}  # subtask_id -> set of file paths that existed before the agent ran
        self.sandbox = None  # Phase 13: E2B sandbox object (None in local/docker modes)
        self.user_id = None

    def inject_corrective_subtask(self, selector: str, instruction: str):
        """
        Dynamically mutates the execution graph based on visual-voice self-correction.
        Handles three explicit execution state cases:
        Case (a): Target agent currently running -> Interrupt and re-run.
        Case (b): Target agent completed, downstream running -> Mark STALE, rollback, and re-queue.
        Case (c): DAG idle -> Append and dispatch.
        """
        import time
        _push_hermes_event({"type": "task_status", "status": "HEALING",
                            "selector": selector, "instruction": instruction[:120]})
        target_agent = "frontend"
        
        if self.is_running and self.active_agent is not None:
            # Case (a): Target agent currently running
            if self.active_agent == target_agent:
                reason = f"orchestrator: USER INTERRUPT on '{self.active_agent}' at selector '{selector}'. Instruction: '{instruction}'. Interrupted and rolling back."
                log_to_agents_md(reason, self.user_id)

                # Mark target agent status as INTERRUPTED in AGENTS.md
                try:
                    _amp = _agents_md_path(self.user_id)
                    with open(_amp, "r", encoding="utf-8") as f:
                        content = f.read()
                    import re
                    content = re.sub(
                        rf"(\| {self.active_agent} \| [^|]+ \|)[^|]+",
                        rf"\1 INTERRUPTED",
                        content,
                        count=1
                    )
                    with open(_amp, "w", encoding="utf-8") as f:
                        f.write(content)
                except Exception:
                    pass
                    
                # Inject corrective task BEFORE current index
                corr_subtask = {
                    "id": f"corrective_{self.active_agent}_{int(time.time())}",
                    "agent": self.active_agent,
                    "task": f"Self-Correction target: '{selector}'. Instruction: {instruction}",
                    "depends_on": []
                }
                self.execution_list.insert(self.current_index, corr_subtask)
                self.is_interrupted = True
                
            # Case (b): Target completed, downstream running (e.g. backend or qa running)
            else:
                reason = f"orchestrator: USER INTERRUPT visual correction at selector '{selector}'. Instruction: '{instruction}'. Marking '{target_agent}' as STALE and re-queueing dependents."
                log_to_agents_md(reason, self.user_id)

                # Interrupt downstream agent
                self.is_interrupted = True

                # Rollback stale agent's workspace files before re-running
                stale_result = next(
                    (r for r in reversed(self.results) if r["agent"] == target_agent),
                    None
                )
                if stale_result:
                    self._restore_snapshot(stale_result["subtask_id"], target_agent)
                    from core.hermes.server import hermes_event_manager
                    hermes_event_manager.enqueue_speech_sync(
                        f"Rolling back stale {target_agent} workspace before correction.",
                        interrupt=False,
                        role_hint="system"
                    )

                # Mark completed agent target as STALE in AGENTS.md
                try:
                    _amp = _agents_md_path(self.user_id)
                    with open(_amp, "r", encoding="utf-8") as f:
                        content = f.read()
                    import re
                    content = re.sub(
                        rf"(\| {target_agent} \| [^|]+ \|)[^|]+",
                        rf"\1 STALE",
                        content,
                        count=1
                    )
                    with open(_amp, "w", encoding="utf-8") as f:
                        f.write(content)
                except Exception:
                    pass

                # Inject corrective task at current index
                corr_subtask = {
                    "id": f"corrective_{target_agent}_{int(time.time())}",
                    "agent": target_agent,
                    "task": f"Self-Correction target: '{selector}'. Instruction: {instruction}",
                    "depends_on": []
                }
                
                # Target retry task to re-run target agent logic
                target_retry_task = {
                    "id": f"{target_agent}_retry_{int(time.time())}",
                    "agent": target_agent,
                    "task": f"Re-execute step to integrate visual correction '{selector}': {instruction}",
                    "depends_on": []
                }
                
                self.execution_list.insert(self.current_index, corr_subtask)
                self.execution_list.insert(self.current_index + 1, target_retry_task)
                
        else:
            # Case (c): DAG idle
            reason = f"orchestrator: USER FEEDBACK idle visual correction at selector '{selector}'. Instruction: '{instruction}'. Appending corrective subtask."
            log_to_agents_md(reason, self.user_id)

            corr_subtask = {
                "id": f"corrective_{target_agent}_{int(time.time())}",
                "agent": target_agent,
                "task": f"Self-Correction target: '{selector}'. Instruction: {instruction}",
                "depends_on": []
            }
            self.execution_list.append(corr_subtask)

    # --- Workspace snapshot helpers ---

    def _capture_snapshot(self, subtask_id: str, role: str):
        """Record file paths currently in the agent's workspace before it runs."""
        # Scope to the running user's workspace so SaaS users never snapshot each other's files.
        workspace_dir = get_workspace_path(role, self.user_id)
        existing = set()
        if os.path.exists(workspace_dir):
            for dirpath, _, filenames in os.walk(workspace_dir):
                for fname in filenames:
                    existing.add(os.path.join(dirpath, fname))
        self.snapshots[subtask_id] = existing

    def _restore_snapshot(self, subtask_id: str, role: str):
        """Delete files the stale agent created (files not present at snapshot time)."""
        if subtask_id not in self.snapshots:
            logger.warning(f"[HEAL] No snapshot for {subtask_id}. Skipping rollback.")
            return
        pre_run = self.snapshots[subtask_id]
        workspace_dir = get_workspace_path(role, self.user_id)
        if not os.path.exists(workspace_dir):
            return
        removed = 0
        for dirpath, _, filenames in os.walk(workspace_dir):
            for fname in filenames:
                full_path = os.path.join(dirpath, fname)
                if full_path not in pre_run:
                    try:
                        os.remove(full_path)
                        log_to_agents_md(f"orchestrator: Rolled back stale file: {full_path}", self.user_id)
                        removed += 1
                    except Exception as e:
                        logger.warning(f"[HEAL] Could not remove {full_path}: {e}")
        print(f"    [HEAL] Workspace rollback: removed {removed} stale file(s) from '{role}'.")

# ---------------------------------------------------------------------------
# Phase 13: Per-task orchestrator registry — supports concurrent multi-user sessions
# ---------------------------------------------------------------------------
_orchestrators: dict = {}          # task_id -> ActiveOrchestrator
_orchestrators_lock = threading.Lock()

# Backward-compat pointer: the most recently created orchestrator.
# Server.py imports this for self-hosted single-user mode (corrective actions).
# Multi-user callers should use get_orchestrator(task_id) instead.
active_orchestrator: "ActiveOrchestrator | None" = None


def register_orchestrator(task_id: str, orch: "ActiveOrchestrator") -> None:
    """Register a per-task orchestrator instance. Updates backward-compat pointer."""
    global active_orchestrator
    with _orchestrators_lock:
        _orchestrators[task_id] = orch
    active_orchestrator = orch


def get_orchestrator(task_id: str | None = None) -> "ActiveOrchestrator | None":
    """Look up an active orchestrator by task_id; falls back to most-recent if None."""
    if task_id is None:
        return active_orchestrator
    with _orchestrators_lock:
        return _orchestrators.get(task_id)


def unregister_orchestrator(task_id: str) -> None:
    """Remove a finished orchestrator from the registry."""
    with _orchestrators_lock:
        _orchestrators.pop(task_id, None)


def run_dag(user_task: str, dry_run: bool = False, task_id: str = None, user_id: str | None = None) -> dict:
    """
    Decompose a user task into subtasks, build a DAG, and execute in order.

    Args:
        user_task: Natural language task description
        dry_run: If True, print the plan without executing API calls
        task_id: Optional task ID (auto-generated if not provided)

    Returns:
        dict with overall status, results per subtask, and files created
    """
    from core.orchestrator.session import SessionManager
    session_manager = SessionManager()

    # Check if there is an incomplete session to recover
    recovered_data = None
    if not task_id:
        try:
            recovered_data = session_manager.recover()
        except Exception as re_err:
            logger.warning(f"Failed to check session recovery: {re_err}")
            
    is_recovered = False
    if recovered_data:
        state = recovered_data["state"]
        task_id = recovered_data["session_id"]
        user_task = state["user_task"]
        ordered = state["execution_list"]
        is_recovered = True
        run_id = task_id[-8:]
        print(f"\n[RECOVERY] Found incomplete session '{task_id}'. Resuming execution plan...")
    else:
        task_id = task_id or f"task_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        run_id = task_id[-8:]  # short correlation ID for log lines

    # Phase 13: each run_dag() call gets its own isolated orchestrator instance.
    # Concurrent users no longer share state.
    orchestrator = ActiveOrchestrator()
    orchestrator.user_id = user_id
    register_orchestrator(task_id, orchestrator)

    print(f"[TRACE] {__name__}.run_dag: enter task={user_task[:60]} task_id={task_id} dry_run={dry_run} recovered={is_recovered}", file=sys.stderr, flush=True)
    logger.info(f"[{run_id}] Starting DAG: {user_task[:80]}")
    _push_hermes_event({"type": "task_status", "status": "PLANNING", "task_id": task_id, "task": user_task[:120]})

    print(f"\n{'='*60}")
    print(f"  Jarvis Multi-Agent Orchestrator" + (" (RECOVERED)" if is_recovered else ""))
    print(f"  Task: {user_task}")
    print(f"  ID:   {task_id}")
    print(f"{'='*60}\n")

    if not is_recovered:
        # Step 0 (Phase 36C): produce a reviewable SPEC artifact before any coding, so every
        # agent builds against one coherent blueprint (data model + contract + design + criteria).
        print(f"[0/3] Architecting SPEC...")
        spec = None
        try:
            from core.orchestrator.architect import produce_spec, SPEC_MD_PATH
            spec = produce_spec(user_task, user_id=user_id)
            print(f"      SPEC: {spec.get('title', 'untitled')} — "
                  f"{len(spec.get('api_contract', []))} endpoints, "
                  f"{len(spec.get('acceptance_criteria', []))} acceptance criteria "
                  f"(written to {os.path.basename(SPEC_MD_PATH)})")
        except Exception as _se:
            logger.warning(f"[{run_id}] architect step skipped: {_se}")

        # Step 1: Decompose into subtasks (grounded in the SPEC when available)
        print(f"[1/3] Decomposing task with orchestrator...")
        subtasks = parse_task(user_task, spec=spec)

        # Step 2: Topological sort
        print("[2/3] Building execution DAG...")
        ordered = _topological_sort(subtasks)
        ev.emit("plan_ready", subtasks=[{"desc": st["task"], "agent": st["agent"]} for st in ordered])
    else:
        print("[1/3] Decomposing task... (Skipped - Session Recovered)")
        print("[2/3] Building execution DAG... (Skipped - Session Recovered)")

    print(f"\nExecution plan ({len(ordered)} steps):")
    for i, st in enumerate(ordered):
        deps = ", ".join(st["depends_on"]) if st["depends_on"] else "none"
        print(f"  {i+1}. [{st['agent']}] {st['task']}")
        print(f"     ID: {st['id']} | Depends on: {deps}")
    print()

    if dry_run:
        print("DRY RUN — no API calls made. Exiting.")
        unregister_orchestrator(task_id)
        return {
            "status": "dry_run",
            "plan": ordered,
            "results": [],
        }

    # Import destroy here so it's in scope for the finally-style cleanup below
    if os.environ.get("JARVIS_SANDBOX_MODE") == "mxc":
        from core.system.mxc_adapter import destroy_sandbox
    else:
        from tools.sandbox import destroy_sandbox

    # Step 3: Execute
    print("[3/3] Executing agents...\n")
    _push_hermes_event({"type": "task_status", "status": "EXECUTING", "task_id": task_id,
                        "plan": [{"id": s["id"], "role": s["agent"], "label": s["task"][:60]} for s in ordered]})
    
    if not is_recovered:
        _reset_agents_md(task_id, user_task, user_id)

    # Phase 13: provision E2B cloud or MXC sandbox
    if os.environ.get("JARVIS_SANDBOX_MODE") == "mxc":
        from core.system.mxc_adapter import create_sandbox
    else:
        from tools.sandbox import create_sandbox
    orchestrator.reset()
    orchestrator.sandbox = create_sandbox(task_id)
    orchestrator.user_task = user_task
    orchestrator.task_id = task_id
    orchestrator.is_running = True
    orchestrator.execution_list = list(ordered)

    if is_recovered:
        orchestrator.current_index = state["current_index"]
        orchestrator.results = state.get("results", [])
        orchestrator.all_files = state.get("all_files", [])
        print(f"[RECOVERY] Resuming from Step {orchestrator.current_index+1}/{len(orchestrator.execution_list)}")
    else:
        orchestrator.current_index = 0

    while orchestrator.current_index < len(orchestrator.execution_list):
        st = orchestrator.execution_list[orchestrator.current_index]
        
        # Write checkpoint before executing this subtask
        session_manager.checkpoint(task_id, {
            "current_index": orchestrator.current_index,
            "status": "incomplete",
            "execution_list": ordered,
            "user_task": user_task,
            "results": orchestrator.results,
            "all_files": orchestrator.all_files
        })

        orchestrator.active_subtask = st
        orchestrator.active_agent = st["agent"]
        agent_role = st["agent"]
        subtask_desc = st["task"]

        print(f"--- Step {orchestrator.current_index+1}/{len(orchestrator.execution_list)}: [{agent_role}] ---")
        print(f"    {subtask_desc}")
        logger.info(f"[{run_id}] Subtask {st['id']} -> {agent_role}: {subtask_desc[:60]}")

        agent = _get_agent_instance(agent_role, user_id=user_id)
        
        # Freshly compile converged context (Correction #1)
        from core.orchestrator.context_sync import compile_converged_context
        converged_context = compile_converged_context()
        subtask_desc = f"{converged_context}\n\n## Your Task\n{subtask_desc}"
            
        # Hook agent startup execution voice alert
        from core.hermes.server import hermes_event_manager
        if agent_role == "frontend":
            hermes_event_manager.enqueue_speech_sync(
                "Inspecting the element you tapped. Adjusting layout rules now.",
                interrupt=True,
                role_hint="frontend"
            )

        # Check interruption check right before runner
        if orchestrator.is_interrupted:
            print(f"    [INTERRUPT] Interrupted before task execution. Pivoting...")
            orchestrator.is_interrupted = False
            continue

        # Snapshot workspace state before agent runs (enables rollback on STALE)
        orchestrator._capture_snapshot(st["id"], agent_role)

        # Broadcast agent start to HUD
        _push_hermes_event({"type": "dag_update", "node_id": st["id"], "role": agent_role,
                            "status": "active", "label": st["task"][:80]})

        # Phase 12: Run agent in thread pool with timeout to prevent indefinite blocking
        print(f"[TRACE] {__name__}.run_dag: submit subtask id={st['id']} agent={agent_role} desc={subtask_desc[:60]}", file=sys.stderr, flush=True)
        _future = _agent_executor.submit(agent.run, subtask_desc)
        try:
            result = _future.result(timeout=_AGENT_TIMEOUT_SEC)
            print(f"[TRACE] {__name__}.run_dag: subtask done id={st['id']} agent={agent_role} status={result.get('status') if isinstance(result, dict) else type(result).__name__}", file=sys.stderr, flush=True)
        except FuturesTimeoutError:
            print(f"[TRACE] {__name__}.run_dag: subtask TIMEOUT id={st['id']} agent={agent_role} after={_AGENT_TIMEOUT_SEC}s", file=sys.stderr, flush=True)
            result = {
                "status": "error",
                "output": f"[TIMEOUT] {agent_role} agent timed out after {_AGENT_TIMEOUT_SEC}s",
                "files": [],
            }
            logger.warning(f"[{run_id}] {agent_role} timed out after {_AGENT_TIMEOUT_SEC}s on: {subtask_desc[:60]}")

        # Broadcast agent completion to HUD
        _dag_status = "done" if result["status"] == "success" else "error"
        _push_hermes_event({"type": "dag_update", "node_id": st["id"], "role": agent_role,
                            "status": _dag_status, "label": st["task"][:80],
                            "files": result.get("files", [])})

        # Interruption check right after execution
        if orchestrator.is_interrupted:
            print(f"    [INTERRUPT] Interrupted after task execution. Pivoting...")
            orchestrator.is_interrupted = False
            continue

        # Closed-loop Visual Verification for Frontend Agent
        if agent_role == "frontend" and result["status"] == "success":
            html_files = [f for f in result.get("files", []) if f.endswith(".html")]
            if html_files:
                html_file = html_files[0]
                html_path = os.path.join(agent.workspace, html_file)
                
                from tools.browser import browser_navigate, browser_screenshot, shutdown_browser
                from agents.qa_agent import QAAgent
                qa = QAAgent()
                
                max_visual_retries = 3
                for attempt in range(max_visual_retries):
                    # Check interrupt inside the retry loop
                    if orchestrator.is_interrupted:
                        break
                        
                    print(f"    [VISUAL AUDIT] Visual Verification Iteration {attempt + 1}/{max_visual_retries}...")
                    nav_res = browser_navigate(html_path)
                    if "[ERROR]" in nav_res:
                        print(f"    [WARNING] Navigation failed: {nav_res}. Skipping visual audit.")
                        break
                        
                    shot_res = browser_screenshot()
                    if "[ERROR]" in shot_res:
                        print(f"    [WARNING] Screenshot failed: {shot_res}. Skipping visual audit.")
                        break
                        
                    screenshot_path = "/workspace/workspaces/browser/screenshot.png"
                    html_content = agent.read_workspace_file(html_file)
                    
                    # Run visual layout verifier
                    vis_res = qa.verify_ui_layout_visually(screenshot_path, html_content)
                    passed = vis_res.get("passed", True)
                    issues = vis_res.get("issues", [])
                    confidence = vis_res.get("confidence", 1.0)
                    
                    logger.info(f"Visual audit results (confidence={confidence}): passed={passed}, issues={issues}")
                    
                    if passed:
                        print(f"    [PASS] Visual layout verification successful (confidence {confidence:.2f})!")
                        hermes_event_manager.enqueue_speech_sync(
                            "I have verified the style guide and resolved all spacing overlaps.",
                            interrupt=False,
                            role_hint="qa"
                        )
                        break
                    else:
                        issue_msgs = [i.get("message", "Misaligned elements") for i in issues]
                        print(f"    [FAIL] Visual layout issues detected (confidence {confidence:.2f}):")
                        for msg in issue_msgs:
                            print(f"      - {msg}")
                            
                        if attempt == max_visual_retries - 1:
                            print("    [WARNING] Visual verification exceeded max iterations. Proceeding with defects.")
                            break
                            
                        # Voice retry notification
                        hermes_event_manager.enqueue_speech_sync(
                            f"Visual verification iteration {attempt + 1}. Spacing issues found. Correcting bugs.",
                            interrupt=False,
                            role_hint="qa"
                        )
                        
                        # Feedback correction loop
                        feedback = (
                            f"The visual verification of your previous layout detected layout defects. "
                            f"Please correct the CSS/HTML to fix these visual bugs:\n"
                            + "\n".join(f"- {msg}" for msg in issue_msgs)
                            + "\n\nReturn the entire complete workspace files inside the JSON block."
                        )
                        print(f"    [RETRY] Routing feedback to frontend agent for layout correction...")
                        _fb_future = _agent_executor.submit(agent.run, feedback)
                        try:
                            result = _fb_future.result(timeout=_AGENT_TIMEOUT_SEC)
                        except FuturesTimeoutError:
                            result = {
                                "status": "error",
                                "output": f"[TIMEOUT] frontend visual-retry timed out after {_AGENT_TIMEOUT_SEC}s",
                                "files": [],
                            }
                        if result["status"] != "success":
                            print(f"    [FAIL] Frontend agent retry failed: {result.get('output')}")
                            break
                
                # Shutdown browser to release resources
                shutdown_browser()

        if orchestrator.is_interrupted:
            print(f"    [INTERRUPT] Interrupted during visual verification. Pivoting...")
            orchestrator.is_interrupted = False
            continue

        # Phase 36A: functional self-correction for code-producing agents (backend/qa).
        # Frontend uses the visual loop above; here we run/compile backend & QA output in the
        # task sandbox (E2B when configured, else safe local checks) and feed errors back.
        if agent_role in ("backend", "qa") and result.get("status") == "success":
            try:
                from core.orchestrator.self_correct import verify_and_correct
                result = verify_and_correct(agent, result, sandbox=orchestrator.sandbox)
                _v = result.get("verification")
                if _v and _v.get("ran"):
                    print(f"    [VERIFY] {agent_role} execution check: "
                          f"{'PASS' if _v.get('passed') else 'FAIL'} after {_v.get('iterations')} iter")
            except Exception as _ve:
                logger.warning(f"[{run_id}] self-correction skipped for {agent_role}: {_ve}")

        orchestrator.results.append({
            "subtask_id": st["id"],
            "agent": agent_role,
            "task": subtask_desc,
            **result,
        })

        status_icon = "[PASS]" if result["status"] == "success" else "[FAIL]"
        print(f"    {status_icon} {result['output']}")
        if result.get("files"):
            for f in result["files"]:
                print(f"      -> {f}")
            orchestrator.all_files.extend(result["files"])

        # 10a: Index successful subtask outcome to GBrain
        if result["status"] == "success" and os.environ.get("JARVIS_CI") != "true":
            try:
                from brain.write import brain_write
                _slug = f"dag/{st['id'][-16:]}/{agent_role}"
                brain_write(_slug, json.dumps({
                    "task": subtask_desc[:500],
                    "output": result.get("output", ""),
                    "files": result.get("files", []),
                    "agent": agent_role,
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                }, indent=2))
            except Exception as _bwe:
                logger.warning(f"[dag] GBrain subtask write failed: {_bwe}")

        print()

        if result["status"] == "error":
            print(f"ERROR in step {orchestrator.current_index+1}. Stopping DAG execution.")
            break

        # Check if the successful step is a database migration
        if result["status"] == "success" and agent_role == "backend" and (
            "migration" in st["task"].lower() or 
            "table" in st["task"].lower() or 
            "schema" in st["task"].lower() or
            any(f.endswith(".sql") for f in result.get("files", []))
        ):
            print("    [SYSTEM] Database migration succeeded. Triggering automatic backend restart inside WSL...")
            try:
                import subprocess
                _wsl_distro = os.environ.get("JARVIS_WSL_DISTRO", "Ubuntu-24.04")
                _wsl_project = os.environ.get("JARVIS_WSL_PROJECT_ROOT", "")
                if not _wsl_project:
                    print("    [INFO] JARVIS_WSL_PROJECT_ROOT not set — skipping WSL container restart.")
                else:
                    if os.environ.get("JARVIS_SANDBOX_MODE") == "mxc":
                        cmd = ["mxc", "exec", "backend", "restart"]
                        restart_msg = "Automatic backend container restart succeeded via `mxc exec backend restart`."
                    else:
                        cmd = ["wsl", "-d", _wsl_distro, "--cd", _wsl_project, "docker", "compose", "restart", "backend"]
                        restart_msg = "Automatic backend container restart succeeded via `docker compose restart backend` inside WSL."
                        
                    from core.system.safety_monitor import SafetyMonitor
                    res = SafetyMonitor.run_monitored(cmd)
                    if res.returncode == 0:
                        print("    [PASS] Backend container restarted successfully.")
                        log_to_agents_md(f"orchestrator: {restart_msg}", user_id)
                    else:
                        print(f"    [WARNING] Failed to restart backend container inside WSL: {res.stderr or res.stdout}")
            except Exception as e:
                print(f"    [WARNING] Exception occurred while restarting backend container: {e}")

        orchestrator.current_index += 1

    orchestrator.is_running = False

    # Update AGENTS.md task status
    try:
        _amp = _agents_md_path(user_id)
        with open(_amp, "r", encoding="utf-8") as f:
            content = f.read()
        import re
        final_status = "COMPLETED" if all(r["status"] == "success" for r in orchestrator.results) else "FAILED"
        content = re.sub(r"(\| Status \|)[^|]+\|", rf"\1 {final_status} |", content, count=1)
        with open(_amp, "w", encoding="utf-8") as f:
            f.write(content)
    except Exception:
        final_status = "FAILED"

    # Mark the checkpoint status based on final outcome
    try:
        if final_status == "COMPLETED":
            session_manager.mark_completed(task_id, {
                "current_index": orchestrator.current_index,
                "status": "completed",
                "execution_list": ordered,
                "user_task": user_task,
                "results": orchestrator.results,
                "all_files": orchestrator.all_files
            })
        else:
            session_manager.checkpoint(task_id, {
                "current_index": orchestrator.current_index,
                "status": "failed",
                "execution_list": ordered,
                "user_task": user_task,
                "results": orchestrator.results,
                "all_files": orchestrator.all_files
            })
    except Exception as se_err:
        logger.warning(f"Failed to record final session status: {se_err}")

    # 10a: Write full run summary to GBrain on success
    if final_status == "COMPLETED" and os.environ.get("JARVIS_CI") != "true":
        try:
            from brain.write import brain_write
            brain_write(f"dag/{task_id[-16:]}/summary", json.dumps({
                "task": user_task[:800],
                "task_id": task_id,
                "status": final_status,
                "files_created": orchestrator.all_files,
                "subtask_count": len(orchestrator.results),
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }, indent=2))
        except Exception as _bws:
            logger.warning(f"[dag] GBrain summary write failed: {_bws}")

    _push_hermes_event({"type": "task_status", "status": final_status,
                        "task_id": task_id, "files": orchestrator.all_files})

    print(f"\n{'='*60}")
    print(f"  Result: {final_status}")
    print(f"  Files created: {len(orchestrator.all_files)}")
    print(f"{'='*60}\n")

    # Phase 13: tear down E2B sandbox (no-op when sandbox is None)
    destroy_sandbox(orchestrator.sandbox, task_id)
    unregister_orchestrator(task_id)
    return {
        "status": final_status,
        "results": orchestrator.results,
        "files": orchestrator.all_files,
    }


def main():
    parser = argparse.ArgumentParser(description="Jarvis Multi-Agent Orchestrator")
    parser.add_argument("task", nargs="?", help="Task to execute")
    parser.add_argument("--dry-run", action="store_true", help="Preview plan without executing")
    parser.add_argument("--task-id", default=None, help="Custom task ID")

    args = parser.parse_args()

    if not args.task:
        print("Usage: python -m core.orchestrator.dag \"Your task description\"")
        print("       python -m core.orchestrator.dag --dry-run \"Your task description\"")
        sys.exit(1)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    run_dag(args.task, dry_run=args.dry_run, task_id=args.task_id)


if __name__ == "__main__":
    main()

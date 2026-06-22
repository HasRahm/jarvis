# Force UTF-8 stdout/stderr so emoji and non-ASCII content (e.g. from browser_extract_text)
# don't crash on Windows where the default codec is cp1252.
import sys as _sys, io as _io
from core.trace import trace as _jtrace
if hasattr(_sys.stdout, "buffer"):
    _sys.stdout = _io.TextIOWrapper(_sys.stdout.buffer, encoding="utf-8", errors="replace")
if hasattr(_sys.stderr, "buffer"):
    _sys.stderr = _io.TextIOWrapper(_sys.stderr.buffer, encoding="utf-8", errors="replace")

# Auto-load .env so runner works standalone (not just via jarvis-cli.py subprocess)
import os as _os
_env_path = _os.path.join(
    _os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))),
    ".env"
)
if _os.path.isfile(_env_path):
    with open(_env_path, encoding="utf-8") as _ef:
        for _line in _ef:
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _v = _line.split("=", 1)
                _os.environ.setdefault(_k.strip(), _v.strip())

import os
import sys
import argparse
import uuid
import json
import threading
import concurrent.futures
from colorama import Fore, Style, init

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from tools.dispatcher import dispatch, TOOL_DEFINITIONS
from core.system.skills import SkillsEngine
from core.system.system_handshake import EnvironmentHandshake
from core.system.llm_adapter import call_llm, is_ollama_available

init()

PRIMARY_MODEL = os.environ.get("JARVIS_PRIMARY_MODEL", "gemma4:31b-cloud")
FALLBACK_MODEL = os.environ.get("JARVIS_FALLBACK_MODEL", "gemma4:31b-cloud")

# ── Loop safety limits ────────────────────────────────────────────────────────
MAX_TURNS = 30           # hard ceiling: never loop more than 30 LLM turns
MAX_CHALLENGES = 2       # max verify/autonomy challenges per final response
MAX_NO_CHANGE = 3        # consecutive observe-after-act "no change" before auto-break
MAX_MESSAGES = 24        # sliding window: keep system + last N messages

def get_available_model():
    try:
        if is_ollama_available():
            import ollama
            client = ollama.Client(timeout=5.0)
            models = [m.get("model") or m.get("name") for m in client.list().get("models", [])]
            if PRIMARY_MODEL in models:
                return PRIMARY_MODEL
        return FALLBACK_MODEL
    except Exception:
        return FALLBACK_MODEL

def emit_jarvis_event(event_type, session_id, **kwargs):
    """Emit Jarvis OSC 777 escape sequence to stdout."""
    payload = {
        "v": 1,
        "agent": "hermes",
        "event": event_type,
        "session_id": session_id
    }
    payload.update(kwargs)
    json_str = json.dumps(payload)
    # OSC 777 notification sequence format
    sys.stdout.write(f"\x1b]777;notify;jarvis://agent;{json_str}\x07")
    sys.stdout.flush()

# Keep backward compat for any callers still using the old name
emit_osc_777 = emit_jarvis_event

class AgentContext:
    def __init__(self, task_id):
        self.task_id = task_id
        self.allow_cortex = True


# ── Async brain prefetch ──────────────────────────────────────────────────────
# Fire brain_query in a background thread at session start so by the time the
# first LLM call finishes, the brain result is already available.
_brain_prefetch_result = None
_brain_prefetch_ready = threading.Event()

def _prefetch_brain(query: str):
    """Run brain_query in background, store result for injection."""
    global _brain_prefetch_result
    try:
        from brain.query import brain_query
        _brain_prefetch_result = brain_query(query)
    except Exception as e:
        _brain_prefetch_result = f"[brain prefetch failed: {e}]"
    finally:
        _brain_prefetch_ready.set()

def get_brain_prefetch(timeout: float = 3.0) -> str:
    """Get the prefetched brain result. Returns '' if not ready in time."""
    if _brain_prefetch_ready.wait(timeout=timeout):
        return _brain_prefetch_result or ""
    return ""


# ── Message window ────────────────────────────────────────────────────────────
def _trim_messages(messages: list, max_recent: int = MAX_MESSAGES) -> list:
    """Keep system message + the most recent `max_recent` messages.
    
    Prevents unbounded token growth that makes each LLM call slower.
    Inserts a [context trimmed] marker so the model knows history was cut.
    """
    if len(messages) <= max_recent + 1:  # +1 for system message
        return messages
    
    system_msg = messages[0]
    recent = messages[-(max_recent):]
    
    # Insert a marker so the model knows history was trimmed
    trim_marker = {
        "role": "user",
        "content": "[Earlier conversation history was trimmed to save context. "
                   "The most recent actions and results are shown below. "
                   "If you need earlier context, call brain_query.]"
    }
    return [system_msg, trim_marker] + recent


def main():
    parser = argparse.ArgumentParser(description="Hermes CLI Runner")
    parser.add_argument("-p", "--prompt", required=True, help="Path to the prompt text file")
    parser.add_argument("-m", "--model", default="gemma4:31b-cloud", help="Ollama model to use")
    args = parser.parse_args()

    if not os.path.exists(args.prompt):
        print(Fore.RED + f"Error: Prompt file not found at '{args.prompt}'" + Style.RESET_ALL, file=sys.stderr)
        sys.exit(1)

    with open(args.prompt, "r", encoding="utf-8-sig") as f:
        prompt_content = f.read().strip()

    model = args.model
    session_id = f"hermes_{uuid.uuid4().hex[:12]}"
    agent_ctx = AgentContext(session_id)
    cwd = os.getcwd()

    # 1. Emit Session Start
    emit_jarvis_event("session_start", session_id, cwd=cwd)

    # 2. Emit Prompt Submit
    emit_jarvis_event("prompt_submit", session_id, query=prompt_content)

    clean_prompt = prompt_content.encode(sys.stdout.encoding or 'ascii', errors='replace').decode(sys.stdout.encoding or 'ascii')
    print(Fore.CYAN + f"\n[Hermes] Session started: {session_id}" + Style.RESET_ALL)
    print(Fore.BLUE + f"[Prompt] {clean_prompt}\n" + Style.RESET_ALL)
    sys.stdout.flush()

    # Phase 29: physical cursor + visible ring by default so the user sees the agent act.
    os.environ.setdefault("JARVIS_AGENT_CURSOR", "1")

    # ── ASYNC: Fire brain_query in background IMMEDIATELY ─────────────────
    # Don't block — the result will be injected once ready.
    brain_thread = threading.Thread(
        target=_prefetch_brain, args=(prompt_content,),
        daemon=True, name="jarvis-brain-prefetch"
    )
    brain_thread.start()

    from datetime import datetime as _dt
    _today = _dt.now().strftime("%Y-%m-%d")

    handshake = EnvironmentHandshake()
    system_instruction = (
        "You are Jarvis, a powerful AI assistant with full access to this computer via tools. Use your tools to accomplish the user's tasks. "
        f"Today's date is {_today}. For anything that may have changed since your training (new tech, versions, prices, news, current events), use web_search first — do not rely on stale memory. "
        "Memory context from brain_query has been pre-loaded below (if available).\n\n"
        "Think adaptively: map 2-3 ways a task could succeed and try them in order — don't stop at the first failure or claim success you haven't verified. "
        "To open or use an app, prefer the open_app tool (it checks for an existing window, then the native app, then the web app in the browser). "
        "Before automating an unfamiliar app, call app_guide to learn its layout — this is faster than exploring blind.\n\n"
        "You are the Lead Orchestrator and Senior Engineering Manager. When asked to CREATE, BUILD, WRITE, DEVELOP, or MAKE any software — a game, app, script, website, tool, API, bot, CLI, or any code project — "
        "ACT AS A C-LEVEL EXECUTIVE AND PRODUCT MANAGER. First, design the complete architecture, break it down into modular tickets, and define the product specifications. "
        "DO NOT write all the boilerplate code yourself. Instead, use your available skills (like 'senior-backend', 'agile-product-owner', 'frontend', etc.) to delegate the work to specialized sub-agents. "
        "Provide each delegated agent with a strict technical specification and design blueprint, then review their work like a Senior Engineer. "
        "It should feel like an office where C-level executives, senior engineers, product managers, and engineers come together to discuss and deliver the product. "
        "Use delegate_task or invoke_subagent to coordinate a full-stack project. "
        "For SPECIALIZED engineering work (security audit, RAG pipeline, regulatory compliance, performance tuning, observability), prefer run_engineering_agent or run_skill_agent to auto-select the best expert from your 700+ skills. "
        "Start building immediately without asking for confirmation.\n\n"
        "--- OFFICE MEETING PROTOCOL ---\n"
        "Before beginning execution on any complex software task, you MUST write an <office_meeting> block. Inside this block:\n"
        "1. Classify the task across 4 dimensions: Execution Domain, Complexity Tier, Required Context, and Verification Method.\n"
        "2. Draft a complete Project Brief with Tech Stack, Design System, Agent Assignments, and Coordination Rules.\n"
        "Only after outputting the <office_meeting> block should you begin making tool calls to invoke your sub-agents.\n"
        "-------------------------------\n\n"
        "<autonomy>NEVER output 'recommended next steps' or hand back a to-do list — do every step "
        "yourself and continue until the goal is fully achieved and verified.</autonomy>\n"
        "<verification_protocol>"
        "CRITICAL: Before EVERY click/type action on a desktop app:\n"
        "(1) Call desktop_get_active_window — confirm you are in the CORRECT app (e.g. Spotify, not Windows Explorer).\n"
        "(2) Call element_graph to map the app's interactive elements INSIDE the app window.\n"
        "(3) WINDOW BOUNDS CHECK: The target element's coordinates (cx, cy) MUST be INSIDE the focused app's window rectangle. "
        "If a 'Search' element is at y < 50 or at the very bottom of the screen, it is the Windows taskbar or Start menu search — NOT the app's search. "
        "The app's own search box will be inside the app's title bar area or content area, NOT at the screen edges.\n"
        "(4) Act on the correct element using coordinates from element_graph (not guessed positions).\n"
        "(5) Verify with verify_outcome or read_screen_text that the action worked.\n"
        "(6) If verification shows it FAILED (wrong window, wrong element, no effect): DO NOT GIVE UP. "
        "Instead: call get_unstuck, re-check which window is active, re-read element_graph, and try a DIFFERENT approach. "
        "You MUST retry at least 2-3 times with different strategies before reporting failure.\n"
        "COMMON TRAP: Windows has a taskbar search (Win+S) that looks like a search box at the bottom of the screen. "
        "This is NOT the same as an app's internal search. Always verify the element belongs to the app you're working in."
        "</verification_protocol>\n"
        "<loop_safety>You have a maximum of 30 tool-call turns. If you detect you are stuck in a "
        "loop (same action repeated 3+ times with no progress), call get_unstuck or try a completely "
        "different approach. Do NOT repeat the same failing action endlessly. But also do NOT give up "
        "after just 1-2 attempts — try at least 3 different approaches before reporting failure.</loop_safety>\n"
        f"{handshake.get_system_prompt_addition()}"
    )

    skills_engine = SkillsEngine()
    skills_addition = skills_engine.get_skills_prompt_addition(prompt_content)

    # Phase 22f: Universal visual vocabulary — icon shapes, app logos, UI patterns
    try:
        from core.system.visual_vocab import get_vocab_context_addition
        vocab_addition = get_vocab_context_addition()
    except Exception as _ve:
        print(Fore.YELLOW + f"[VisualVocab] Could not load vocabulary: {_ve}" + Style.RESET_ALL)
        vocab_addition = ""

    # ── Inject prefetched brain context (non-blocking, up to 3s wait) ─────
    brain_context = get_brain_prefetch(timeout=3.0)
    brain_addition = ""
    if brain_context and "No relevant memories" not in brain_context:
        brain_addition = f"\n\n<brain_context>\n{brain_context[:2000]}\n</brain_context>\n"
        print(Fore.GREEN + "[Brain] Pre-loaded memory context (async)." + Style.RESET_ALL)
    else:
        print(Fore.CYAN + "[Brain] No prior memories found (prefetch complete)." + Style.RESET_ALL)

    messages = [
        {"role": "system", "content": system_instruction + skills_addition + vocab_addition + brain_addition},
        {"role": "user", "content": prompt_content}
    ]

    # ── REMOVED: Clarifier + Planner pre-execution gates ──────────────────
    # These added 4-16s of blocking LLM calls before any work started.
    # The clarifier almost always returned PROCEED (wasted round-trip).
    # The planner's is_complex() gate matched ~90% of real tasks due to
    # overly broad keywords ("search", "open", "click").
    # The model's own CoT reasoning + the verification protocol handle both
    # ambiguity detection and planning natively.

    # Phase 29: harness-enforced verification (UI-TARS observe-after-act).
    from core.orchestrator import exec_guard
    from core.cli.graph_renderer import ExecutionGraphRenderer
    from rich.live import Live
    from core.system import llm_adapter
    
    pending_unverified = False
    challenges = 0
    turns = 0
    tool_turns = 0             # tracks turns where the model actually called tools
    consecutive_no_change = 0

    # Set up Execution Graph TUI
    renderer = ExecutionGraphRenderer(prompt_content)
    from agents.model_router import get_model as _get_orch_model
    renderer.planner_running("orchestrating with " + _get_orch_model("orchestrator"))
    llm_adapter.QUIET_MODE = True

    # Honest run accounting (Phase 46): track which models actually answered + fallback turns, so
    # we never report a clean "success" over an error storm and can show real cost.
    run_models_used: set = set()
    run_fallback_turns = 0

    try:
        with Live(renderer.render(), refresh_per_second=4) as live:
            while turns < MAX_TURNS:
                turns += 1
                _jtrace(f"[TRACE] {__name__}.run: loop turn={turns}/{MAX_TURNS} history={len(messages)}")

                # Trim message history to prevent unbounded token growth
                messages = _trim_messages(messages)

                # Estimate token usage
                token_estimate = sum(len(str(m.get("content", ""))) // 4 for m in messages)
                renderer.set_metrics(token_estimate, token_estimate * 0.000002)
                live.update(renderer.render())

                msg = call_llm(
                    messages=messages,
                    model=model,
                    tools=TOOL_DEFINITIONS
                )
                _stats = llm_adapter.get_last_run()
                _jtrace(f"[TRACE] {__name__}.run: llm returned model_used={_stats.get('model_used')} fallbacks={_stats.get('fallbacks')} tool_calls={len(msg.get('tool_calls', []))}")
                if _stats.get("model_used"):
                    run_models_used.add(_stats["model_used"])
                if _stats.get("fallbacks", 0) > 0:
                    run_fallback_turns += 1

                messages.append(msg)
            
                # Check for <office_meeting> or <project_brief> block to extract plan
                content_str = msg.get("content", "")
                if "<assignment" in content_str or "<project_brief>" in content_str:
                    import re
                    tasks = []
                    for match in re.finditer(r'<assignment[^>]*agent="([^"]+)"[^>]*>.*?<title>(.*?)</title>', content_str, re.DOTALL):
                        tasks.append({"agent": match.group(1), "desc": match.group(2).strip()})
                    if tasks:
                        renderer.update_plan(tasks)
                        live.update(renderer.render())

                if not msg.get("tool_calls"):
                    # Final response from model — gate against premature exit, deferral, and unverified claims.
                    final_content = msg.get("content", "")
                
                    # Gate 0: Premature exit — model is giving up before making enough attempts.
                    if exec_guard.is_premature_exit(final_content, tool_turns) and challenges < MAX_CHALLENGES:
                        challenges += 1
                        print(Fore.YELLOW + f"[Retry Gate] Premature exit detected — model gave up after only {tool_turns} tool turns. Pushing to retry ({challenges}/{MAX_CHALLENGES})." + Style.RESET_ALL)
                        sys.stdout.flush()
                        messages.append({
                            "role": "user",
                            "content": ("You are giving up too early. You have only made "
                                        f"{tool_turns} tool-call attempts so far. You MUST try at least 3 different "
                                        "approaches before reporting failure. Try these strategies:\n"
                                        "1. Call desktop_get_active_window to confirm which window is focused\n"
                                        "2. Call element_graph to see ALL interactive elements and their coordinates\n"
                                        "3. Make sure your click target is INSIDE the app's window bounds (not on the Windows taskbar)\n"
                                        "4. If the element isn't visible, try scrolling or using keyboard shortcuts\n"
                                        "5. Call get_unstuck for additional recovery strategies\n"
                                        "Do NOT give up. Try a different approach NOW."),
                        })
                        continue
                
                    # Gate 1: Autonomy gate — don't let it hand back a to-do list; make it execute.
                    if exec_guard.is_deferral(final_content) and challenges < MAX_CHALLENGES:
                        challenges += 1
                        print(Fore.YELLOW + f"[Autonomy Gate] Deferral detected — pushing to continue ({challenges}/{MAX_CHALLENGES})." + Style.RESET_ALL)
                        sys.stdout.flush()
                        messages.append({
                            "role": "user",
                            "content": ("Do NOT hand back a to-do list or 'recommended next steps'. Execute the "
                                        "next step yourself NOW with your tools, following the verification protocol "
                                        "(confirm window/element, act, verify_location/verify_outcome). Continue until "
                                        "the goal is fully done and verified."),
                        })
                        continue
                
                    # Gate 2: Unverified success claim.
                    if exec_guard.should_challenge(final_content, pending_unverified) and challenges < MAX_CHALLENGES:
                        challenges += 1
                        print(Fore.YELLOW + f"[Verify Gate] Unverified success claim — challenging ({challenges}/{MAX_CHALLENGES})." + Style.RESET_ALL)
                        sys.stdout.flush()
                        messages.append({
                            "role": "user",
                            "content": ("You claim completion, but the last action has NOT been verified. "
                                        "Call verify_outcome (optionally with the text you expect to see), "
                                        "or get_unstuck if it failed. Do not claim success until verified."),
                        })
                        continue

                    clean_final = final_content.encode(sys.stdout.encoding or 'ascii', errors='replace').decode(sys.stdout.encoding or 'ascii')
                    if pending_unverified and exec_guard.should_challenge(final_content, pending_unverified):
                        clean_final = "⚠ UNVERIFIED: the agent could not confirm the last action succeeded.\n\n" + clean_final
                
                    renderer.status = "done"
                    live.update(renderer.render())

                    # Emit Stop event
                    emit_jarvis_event("stop", session_id, response=final_content)
                    break

                # Reset challenges for each new tool-calling turn (the model is working, not deferring)
                challenges = 0
                tool_turns += 1

                # Capture a screen baseline before consequential actions (observe-after-act).
                turn_has_consequential = any(
                    exec_guard.is_consequential(c["function"]["name"]) for c in msg.get("tool_calls", [])
                )
                baseline = exec_guard.capture_baseline() if turn_has_consequential else None

                # Execute tool calls
                for call in msg.get("tool_calls", []):
                    fn = call["function"]["name"]
                    fn_args = call["function"]["arguments"]

                    if fn in ["invoke_subagent", "delegate_task"]:
                        # Try to extract agent name
                        if isinstance(fn_args, dict) and "Subagents" in fn_args:
                            for sa in fn_args["Subagents"]:
                                target = sa.get("TypeName", "unknown")
                                renderer.set_agent_status(target, "working...")
                        elif isinstance(fn_args, dict) and "Agent" in fn_args:
                            renderer.set_agent_status(fn_args["Agent"], "working...")
                        
                    live.update(renderer.render())

                    # Format tool input preview for Jarvis Screen Cortex UI
                    tool_input = {"command": f"{fn}({fn_args})"}
                    if "command" in fn_args:
                        tool_input["command"] = fn_args["command"]
                    elif "file_path" in fn_args:
                        tool_input["file_path"] = fn_args["file_path"]

                    _jtrace(f"[TRACE] {__name__}.run: dispatch fn={fn} args={str(fn_args)[:80]}")
                    try:
                        result = dispatch(fn, fn_args, orch_agent=agent_ctx)
                    except Exception as e:
                        _jtrace(f"[TRACE] {__name__}.run: dispatch EXCEPTION fn={fn} err={str(e)[:80]}")
                        result = f"ERROR: {e}"

                    # Update Graph Renderer on tool return
                    if fn in ["invoke_subagent", "delegate_task"]:
                        if isinstance(fn_args, dict) and "Subagents" in fn_args:
                            for sa in fn_args["Subagents"]:
                                target = sa.get("TypeName", "unknown")
                                renderer.set_agent_status(target, "done")
                        elif isinstance(fn_args, dict) and "Agent" in fn_args:
                            renderer.set_agent_status(fn_args["Agent"], "done")
                        
                    live.update(renderer.render())
                
                    # Append tool result to messages — carry the call id so the adapter pairs
                    # this response to its tool_call by id (OpenAI-compatible correctness).
                    tool_msg = {
                        "role": "tool",
                        "name": fn,
                        "content": str(result)
                    }
                    if call.get("id"):
                        tool_msg["tool_call_id"] = call["id"]
                    messages.append(tool_msg)

                    # Track verification state.
                    if exec_guard.is_consequential(fn):
                        pending_unverified = True
                    elif exec_guard.is_verify(fn):
                        pending_unverified = False

                    result_preview = str(result)[:200]
                    # print(Fore.GREEN + f"  [Hermes Tool Result] {fn} -> {result_preview}" + Style.RESET_ALL)
                    # sys.stdout.flush()

                    # Emit Tool Complete event
                    # Observe-after-act: feed the fresh screen state back so the model
                    # reasons over ground truth instead of assuming the action worked.
                    if turn_has_consequential and baseline is not None:
                        changed, observation = exec_guard.observe_change(baseline)
                        if observation:
                            print(Fore.CYAN + f"  {observation[:160]}" + Style.RESET_ALL)
                            sys.stdout.flush()
                            messages.append({"role": "user", "content": observation})
                            if changed:
                                # A real, observed change discharges the unverified flag.
                                pending_unverified = False
                                consecutive_no_change = 0
                            else:
                                consecutive_no_change += 1
                                if consecutive_no_change >= MAX_NO_CHANGE:
                                    print(Fore.RED + f"  [Loop Guard] {MAX_NO_CHANGE} consecutive actions had NO screen effect. "
                                          "Injecting get_unstuck hint." + Style.RESET_ALL)
                                    messages.append({
                                        "role": "user",
                                        "content": (f"WARNING: Your last {MAX_NO_CHANGE} actions produced NO visible screen change. "
                                                    "You may be stuck in a loop. Either: (1) call get_unstuck to diagnose, "
                                                    "(2) try a completely different approach, or (3) report what you've accomplished so far. "
                                                    "Do NOT repeat the same action again.")
                                    })
                                    consecutive_no_change = 0  # reset so it gets one more chance
                    else:
                        # Non-consequential turns (reads/queries) don't count toward no-change
                        pass

                print(Fore.CYAN + f"  [Hermes] Turn {turns}/{MAX_TURNS} complete. Calling LLM again..." + Style.RESET_ALL)
                sys.stdout.flush()
            else:
                # while-else: MAX_TURNS reached
                print(Fore.RED + f"\n[Hermes] Hard turn limit reached ({MAX_TURNS}). Stopping." + Style.RESET_ALL)
                emit_jarvis_event("stop", session_id, response=f"Turn limit reached ({MAX_TURNS})")

        # Honest run summary (Phase 46): name the model(s) that actually answered, flag fallbacks,
        # and show a real cost estimate so a paid run is never reported as free.
        try:
            from core.cli.live_graph import estimate_cost
            models = sorted(run_models_used) or ["(none — all models unavailable)"]
            est = estimate_cost(token_estimate, models[-1]) if run_models_used else 0.0
            paid = [m for m in run_models_used if "gemma" not in m.lower()]
            parts = [f"model(s): {', '.join(models)}"]
            if run_fallback_turns:
                parts.append(f"{run_fallback_turns} turn(s) fell back from the requested model")
            if paid:
                parts.append(f"PAID model used — est. ${est:.4f}")
            else:
                parts.append("local/free only — $0.00")
            print(Fore.CYAN + "■ Run summary: " + " · ".join(parts) + Style.RESET_ALL)
            sys.stdout.flush()
        except Exception:
            pass
    except Exception as e:
        error_msg = f"Exception occurred during execution: {e}"
        print(Fore.RED + f"\n[Hermes Error] {error_msg}\n" + Style.RESET_ALL, file=sys.stderr)
        emit_jarvis_event("stop", session_id, response=error_msg)
        sys.exit(1)

if __name__ == "__main__":
    main()

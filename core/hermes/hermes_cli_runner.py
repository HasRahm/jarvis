# Force UTF-8 stdout/stderr so emoji and non-ASCII content (e.g. from browser_extract_text)
# don't crash on Windows where the default codec is cp1252.
import sys as _sys, io as _io
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
# import ollama
from colorama import Fore, Style, init

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from tools.dispatcher import dispatch, TOOL_DEFINITIONS
from core.system.skills import SkillsEngine
from core.system.system_handshake import EnvironmentHandshake
from core.system.llm_adapter import call_llm, is_ollama_available

init()

PRIMARY_MODEL = os.environ.get("JARVIS_PRIMARY_MODEL", "gemma4:31b-cloud")
FALLBACK_MODEL = os.environ.get("JARVIS_FALLBACK_MODEL", "gemma4:31b-cloud")

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

def emit_osc_777(event_type, session_id, **kwargs):
    """Emit Warp OSC 777 escape sequence to stdout."""
    payload = {
        "v": 1,
        "agent": "hermes",
        "event": event_type,
        "session_id": session_id
    }
    payload.update(kwargs)
    json_str = json.dumps(payload)
    # OSC 777 notification sequence format
    sys.stdout.write(f"\x1b]777;notify;warp://cli-agent;{json_str}\x07")
    sys.stdout.flush()

class AgentContext:
    def __init__(self, task_id):
        self.task_id = task_id
        self.allow_cortex = True

def main():
    parser = argparse.ArgumentParser(description="Hermes CLI Runner for Warp integration")
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
    emit_osc_777("session_start", session_id, cwd=cwd)

    # 2. Emit Prompt Submit
    emit_osc_777("prompt_submit", session_id, query=prompt_content)

    clean_prompt = prompt_content.encode(sys.stdout.encoding or 'ascii', errors='replace').decode(sys.stdout.encoding or 'ascii')
    print(Fore.CYAN + f"\n[Hermes] Session started: {session_id}" + Style.RESET_ALL)
    print(Fore.BLUE + f"[Prompt] {clean_prompt}\n" + Style.RESET_ALL)
    sys.stdout.flush()

    # Phase 29: physical cursor + visible ring by default so the user sees the agent act.
    os.environ.setdefault("JARVIS_AGENT_CURSOR", "1")

    from datetime import datetime as _dt
    _today = _dt.now().strftime("%Y-%m-%d")

    handshake = EnvironmentHandshake()
    system_instruction = (
        "You are Jarvis, a powerful AI assistant with full access to this computer via tools. Use your tools to accomplish the user's tasks. "
        f"Today's date is {_today}. For anything that may have changed since your training (new tech, versions, prices, news, current events), use web_search first — do not rely on stale memory. "
        "Before answering a user prompt, ALWAYS call brain_query with the user's intent to check past context or memory.\n\n"
        "Think adaptively: map 2-3 ways a task could succeed and try them in order — don't stop at the first failure or claim success you haven't verified. "
        "To open or use an app, prefer the open_app tool (it checks for an existing window, then the native app, then the web app in the browser).\n\n"
        "For complex build tasks that involve multiple components (database + API + UI), use the delegate_task tool to hand the work to the multi-agent IDE. "
        "The orchestrator will decompose the task and route subtasks to specialized agents (backend: claude-sonnet-4-6, frontend: gemini-3.1-pro-preview, QA: gpt-5.4). "
        "Use delegate_task with dry_run=true first to preview the plan.\n"
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

    messages = [
        {"role": "system", "content": system_instruction + skills_addition + vocab_addition},
        {"role": "user", "content": prompt_content}
    ]

    # Phase 28a: Clarify -> Plan gate before execution.
    # Clarifier blocks ONLY on critical ambiguity (fails open otherwise).
    try:
        from core.orchestrator.clarifier import check_ambiguity
        amb = check_ambiguity(prompt_content)
        if not amb.get("proceed", True):
            questions = amb.get("questions", [])
            emit_osc_777("needs_input", session_id, questions=questions)
            try:
                scratch_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
                    os.path.abspath(__file__)))), "scratch")
                os.makedirs(scratch_dir, exist_ok=True)
                with open(os.path.join(scratch_dir, "needs_input.json"), "w", encoding="utf-8") as f:
                    json.dump({"session_id": session_id, "questions": questions}, f, indent=2)
            except Exception:
                pass
            print(Fore.YELLOW + "[NEEDS_INPUT] Critical ambiguity — need clarification before proceeding:" + Style.RESET_ALL)
            print(Fore.YELLOW + json.dumps(questions, indent=2) + Style.RESET_ALL)
            sys.stdout.flush()
            emit_osc_777("stop", session_id, response="NEEDS_INPUT: awaiting clarification")
            return
    except Exception as _ce:
        print(Fore.YELLOW + f"[Clarifier] skipped: {_ce}" + Style.RESET_ALL)

    # Complexity-gated Chain-of-Thought planning (trivial tasks skip it).
    try:
        from core.orchestrator.planner import plan_task
        _plan = plan_task(prompt_content)
        if _plan:
            messages[0]["content"] += f"\n\n<task_plan>\n{_plan}\n</task_plan>\n"
            print(Fore.CYAN + "[Planner] Plan generated and injected into context." + Style.RESET_ALL)
            sys.stdout.flush()
    except Exception as _pe:
        print(Fore.YELLOW + f"[Planner] skipped: {_pe}" + Style.RESET_ALL)

    # Phase 29: harness-enforced verification (UI-TARS observe-after-act).
    from core.orchestrator import exec_guard
    pending_unverified = False
    challenges = 0
    MAX_CHALLENGES = 2

    try:
        while True:
            msg = call_llm(
                messages=messages,
                model=model,
                tools=TOOL_DEFINITIONS
            )

            messages.append(msg)

            if not msg.get("tool_calls"):
                # Final response from model — gate against unverified success claims.
                final_content = msg.get("content", "")
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
                print(Fore.MAGENTA + f"\n{clean_final}\n" + Style.RESET_ALL)

                # Emit Stop event
                emit_osc_777("stop", session_id, response=final_content)
                break

            # Capture a screen baseline before consequential actions (observe-after-act).
            turn_has_consequential = any(
                exec_guard.is_consequential(c["function"]["name"]) for c in msg["tool_calls"]
            )
            baseline = exec_guard.capture_baseline() if turn_has_consequential else None

            # Execute tool calls
            for call in msg["tool_calls"]:
                fn = call["function"]["name"]
                fn_args = call["function"]["arguments"]

                clean_fn_args = str(fn_args).encode(sys.stdout.encoding or 'ascii', errors='replace').decode(sys.stdout.encoding or 'ascii')
                print(Fore.YELLOW + f"  [Hermes Tool Call] {fn}({clean_fn_args})" + Style.RESET_ALL)
                sys.stdout.flush()

                # Format tool input preview for Warp Block UI
                # Warp UI looks for "command" or "file_path" inside tool_input
                tool_input = {"command": f"{fn}({fn_args})"}
                if "command" in fn_args:
                    tool_input["command"] = fn_args["command"]
                elif "file_path" in fn_args:
                    tool_input["file_path"] = fn_args["file_path"]

                try:
                    result = dispatch(fn, fn_args, orch_agent=agent_ctx)
                except Exception as e:
                    result = f"ERROR: {e}"

                # Track verification state.
                if exec_guard.is_consequential(fn):
                    pending_unverified = True
                elif exec_guard.is_verify(fn):
                    pending_unverified = False

                result_preview = str(result)[:200]
                print(Fore.GREEN + f"  [Hermes Tool Result] {fn} -> {result_preview}" + Style.RESET_ALL)
                sys.stdout.flush()

                # Emit Tool Complete event
                emit_osc_777(
                    "tool_complete",
                    session_id,
                    tool_name=fn,
                    tool_input=tool_input,
                    response=str(result)
                )

                messages.append({
                    "role": "tool",
                    "content": str(result)
                })

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

            print(Fore.CYAN + f"  [Hermes] All tool calls processed. Calling LLM again..." + Style.RESET_ALL)
            sys.stdout.flush()

    except Exception as e:
        error_msg = f"Exception occurred during execution: {e}"
        print(Fore.RED + f"\n[Hermes Error] {error_msg}\n" + Style.RESET_ALL, file=sys.stderr)
        emit_osc_777("stop", session_id, response=error_msg)
        sys.exit(1)

if __name__ == "__main__":
    main()

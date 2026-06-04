import os
import sys
import argparse
import uuid
import json
import ollama
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
    cwd = os.getcwd()

    # 1. Emit Session Start
    emit_osc_777("session_start", session_id, cwd=cwd)

    # 2. Emit Prompt Submit
    emit_osc_777("prompt_submit", session_id, query=prompt_content)

    clean_prompt = prompt_content.encode(sys.stdout.encoding or 'ascii', errors='replace').decode(sys.stdout.encoding or 'ascii')
    print(Fore.CYAN + f"\n[Hermes] Session started: {session_id}" + Style.RESET_ALL)
    print(Fore.BLUE + f"[Prompt] {clean_prompt}\n" + Style.RESET_ALL)
    sys.stdout.flush()

    handshake = EnvironmentHandshake()
    system_instruction = (
        "You are Jarvis, a powerful AI assistant with full access to this computer via tools. Use your tools to accomplish the user's tasks. "
        "Before answering a user prompt, ALWAYS call brain_query with the user's intent to check past context or memory.\n\n"
        "For complex build tasks that involve multiple components (database + API + UI), use the delegate_task tool to hand the work to the multi-agent IDE. "
        "The orchestrator will decompose the task and route subtasks to specialized agents (backend: claude-sonnet-4-6, frontend: gemini-3.1-pro-preview, QA: gpt-5.4). "
        "Use delegate_task with dry_run=true first to preview the plan.\n"
        f"{handshake.get_system_prompt_addition()}"
    )

    skills_engine = SkillsEngine()
    skills_addition = skills_engine.get_skills_prompt_addition(prompt_content)
    
    messages = [
        {"role": "system", "content": system_instruction + skills_addition},
        {"role": "user", "content": prompt_content}
    ]

    try:
        while True:
            msg = call_llm(
                messages=messages,
                model=model,
                tools=TOOL_DEFINITIONS
            )

            messages.append(msg)

            if not msg.get("tool_calls"):
                # Final response from model
                final_content = msg.get("content", "")
                clean_final = final_content.encode(sys.stdout.encoding or 'ascii', errors='replace').decode(sys.stdout.encoding or 'ascii')
                print(Fore.MAGENTA + f"\n{clean_final}\n" + Style.RESET_ALL)
                
                # Emit Stop event
                emit_osc_777("stop", session_id, response=final_content)
                break

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
                    result = dispatch(fn, fn_args)
                except Exception as e:
                    result = f"ERROR: {e}"

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
            
            print(Fore.CYAN + f"  [Hermes] All tool calls processed. Calling LLM again..." + Style.RESET_ALL)
            sys.stdout.flush()

    except Exception as e:
        error_msg = f"Exception occurred during execution: {e}"
        print(Fore.RED + f"\n[Hermes Error] {error_msg}\n" + Style.RESET_ALL, file=sys.stderr)
        emit_osc_777("stop", session_id, response=error_msg)
        sys.exit(1)

if __name__ == "__main__":
    main()

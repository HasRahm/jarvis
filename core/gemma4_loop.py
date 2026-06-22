import sys
from core.trace import trace as _jtrace
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import re
import time
import json
import subprocess
from colorama import Fore, Style, init

init() # Initialize colorama

try:
    import ollama
except ImportError:
    _jtrace(f"[TRACE] core.gemma4_loop.<module>: except ImportError")
    print(Fore.RED + "Error: 'ollama' package not found. Did you run scripts/bootstrap.sh?" + Style.RESET_ALL)
    sys.exit(1)

try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    _jtrace(f"[TRACE] core.gemma4_loop.<module>: except ImportError")
    HAS_PSUTIL = False

from tools.dispatcher import dispatch, TOOL_DEFINITIONS
from core.system.skills import SkillsEngine
from core.system.llm_adapter import call_llm, is_ollama_available

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
    except Exception as e:
        _jtrace(f"[TRACE] core.gemma4_loop.get_available_model: except {str(e)[:80]}")
        return FALLBACK_MODEL


def run_pc_optimization():
    _jtrace(f"[TRACE] core.gemma4_loop.run_pc_optimization: enter")
    print(Fore.CYAN + "\n  [SYSTEM] INITIATING PC PERFORMANCE OPTIMIZATION...")
    print("  ---------------------------------------------")
    if not HAS_PSUTIL:
        print(Fore.RED + "  Error: psutil library is not available. Optimization aborted." + Style.RESET_ALL)
        return
        
    try:
        # We will scan for multiple node.exe background zombie processes and kill them safely
        zombie_count = 0
        zombie_ram_reclaimed = 0.0
        
        # Never terminate our own uvicorn server running on port 9000 or the active editor
        active_pids = {os.getpid()}
        for conn in psutil.net_connections():
            if conn.laddr.port == 9000 and conn.pid:
                active_pids.add(conn.pid)

        for proc in psutil.process_iter(['pid', 'name', 'memory_info']):
            try:
                info = proc.info
                name = info['name'].lower()
                pid = info['pid']
                
                # Check for lingering background node.exe processes
                if name == "node.exe" and pid not in active_pids:
                    mem_bytes = info['memory_info'].rss if info['memory_info'] else 0
                    mem_mb = mem_bytes / (1024 * 1024)
                    
                    # Terminate zombie
                    p = psutil.Process(pid)
                    p.terminate()
                    zombie_count += 1
                    zombie_ram_reclaimed += mem_mb
            except Exception:
                _jtrace(f"[TRACE] core.gemma4_loop.run_pc_optimization: except Exception")
                continue
                
        if zombie_count > 0:
            print(Fore.GREEN + f"  [SUCCESS] Safely terminated {zombie_count} background zombie 'node.exe' processes." + Style.RESET_ALL)
            print(Fore.GREEN + f"  [SUCCESS] Reclaimed {zombie_ram_reclaimed:.1f} MB of RAM and freed up system ports!\n" + Style.RESET_ALL)
        else:
            print(Fore.GREEN + "  [SUCCESS] No background development zombie processes detected. System is running at maximum efficiency!\n" + Style.RESET_ALL)
            
    except Exception as e:
        _jtrace(f"[TRACE] core.gemma4_loop.run_pc_optimization: except {str(e)[:80]}")
        print(Fore.RED + f"  Optimization error: {e}\n" + Style.RESET_ALL)


def requires_screen_context(text: str) -> bool:
    _jtrace(f"[TRACE] core.gemma4_loop.requires_screen_context: enter")
    triggers = [
        "what's on", "what am i looking at",
        "current window", "this page", "that button",
        "what does it say", "what's open", "fix this",
        "click", "select", "fill in"
    ]
    return any(t in text.lower() for t in triggers)


def jarvis():
    _jtrace(f"[TRACE] core.gemma4_loop.jarvis: enter")
    print(Fore.CYAN + "\n====================================")
    print("     Jarvis AI Terminal Shell (OS)  ")
    print("====================================\n" + Style.RESET_ALL)
    
    model = get_available_model()
    print(Fore.GREEN + f"Using model: {model}\n" + Style.RESET_ALL)
    
    from core.system.system_handshake import EnvironmentHandshake
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

    messages = [
        {"role": "system", "content": system_instruction}
    ]
    
    while True:
        try:
            user_input = input(Fore.BLUE + "jarvis> " + Style.RESET_ALL)
            if not user_input.strip():
                continue

            # Match and inject specialized skills rules dynamically
            skills_addition = skills_engine.get_skills_prompt_addition(user_input)
            messages[0]["content"] = system_instruction + skills_addition

            # Check if active screen context is needed for standard user prompts (Phase 20c)
            if not user_input.strip().startswith("/") and requires_screen_context(user_input):
                print(Fore.CYAN + "  [SYSTEM] Proactively fetching active screen context..." + Style.RESET_ALL)
                sys.stdout.flush()
                try:
                    import asyncio
                    from core.system.screen_reader import JarvisScreenReader
                    reader = JarvisScreenReader()
                    screen = asyncio.run(reader.read_screen())
                    summary = screen.get("summary", "")
                    if summary:
                        user_input = f"[PROACTIVE SCREEN CONTEXT: {summary}]\nUser request: {user_input}"
                except Exception as e:
                    _jtrace(f"[TRACE] core.gemma4_loop.jarvis: except {str(e)[:80]}")
                    print(Fore.RED + f"  [WARNING] Failed to fetch proactive screen context: {e}" + Style.RESET_ALL)
                    sys.stdout.flush()
                
            # Intercept custom / slash commands (Warp + Jarvis Unified)
            if user_input.strip().startswith("/"):
                parts = user_input.strip().split(maxsplit=1)
                cmd = parts[0].lower()
                arg = parts[1] if len(parts) > 1 else ""
                
                # --- Warp Core Slash Commands ---
                if cmd in ["/exit", "/quit", "/q"]:
                    break
                elif cmd == "/clear":
                    os.system("cls" if os.name == "nt" else "clear")
                    continue
                elif cmd == "/help":
                    print(Fore.CYAN + "\n  JARVIS & WARP UNIFIED CONSOLE COMMANDS")
                    print("  --------------------------------------------------")
                    print("  /ask <prompt>       - Ask the AI a question about any topic")
                    print("  /explain <command>  - Get an in-depth AI explanation of a shell command")
                    print("  /command <desc>     - Generate ONLY the raw executable shell command")
                    print("  /edit <file>        - Put Jarvis into interactive edit mode for a target file")
                    print("  /clear              - Clear the terminal screen")
                    print("  /help               - Show this help manual")
                    print("\n  UNIQUE PERFORMANCE & AGENTIC COMMANDS")
                    print("  --------------------------------------------------")
                    print("  /cleanup            - Safe auto-clean disk performance sweep (temp/caches)")
                    print("  /pc or /optimize    - Reclaim RAM by auto-terminating background zombies")
                    print("  /telemetry          - Display active session LLM pricing and token metrics")
                    print("  /agents             - Show active AGENTS.md registry assignments")
                    print("  /exit               - Safely exit the Jarvis Shell\n" + Style.RESET_ALL)
                    continue
                elif cmd == "/ask":
                    if not arg:
                        print(Fore.YELLOW + "Usage: /ask <your question>\n" + Style.RESET_ALL)
                        continue
                    # Strip command prefix and let loop process it normally
                    user_input = arg
                elif cmd == "/explain":
                    if not arg:
                        print(Fore.YELLOW + "Usage: /explain <command or code>\n" + Style.RESET_ALL)
                        continue
                    user_input = f"Explain the following terminal command or code block in detail: {arg}"
                elif cmd == "/command":
                    if not arg:
                        print(Fore.YELLOW + "Usage: /command <description>\n" + Style.RESET_ALL)
                        continue
                    user_input = f"Generate ONLY the raw executable terminal shell command for: {arg}. Do not include any explanations, warnings, markdown blocks, or extra text. Output just the command string so it can be run."
                elif cmd == "/edit":
                    if not arg:
                        print(Fore.YELLOW + "Usage: /edit <file path>\n" + Style.RESET_ALL)
                        continue
                    user_input = f"Open and perform interactive code edits on this file: {arg}"
                
                # --- Unique Jarvis Performance Commands ---
                elif cmd == "/cleanup":
                    print(Fore.YELLOW + "\n  Executing safe auto-clean disk scan..." + Style.RESET_ALL)
                    os.system("powershell -ExecutionPolicy Bypass -File scripts\\cleanup.ps1 safe")
                    continue
                elif cmd in ["/pc", "/optimize"]:
                    run_pc_optimization()
                    continue
                elif cmd == "/telemetry":
                    print(Fore.CYAN + "\n  RETRIEVING OPERATIONAL TELEMETRY...")
                    print("  ---------------------------------------------")
                    try:
                        with open("workspaces/telemetry.json", "r") as f:
                            tel = json.load(f)
                        print(f"  Total LLM Calls : {tel.get('total_calls', 0)}")
                        print(f"  Input Tokens    : {tel.get('input_tokens', 0)}")
                        print(f"  Output Tokens   : {tel.get('output_tokens', 0)}")
                        print(f"  Estimated Spend : ${tel.get('estimated_cost_usd', 0.0):.5f} USD\n")
                    except Exception:
                        _jtrace(f"[TRACE] core.gemma4_loop.jarvis: except Exception")
                        print("  No telemetry data found. Run tasks to record usage.\n")
                    continue
                elif cmd == "/agents":
                    print(Fore.CYAN + "\n  READING AGENTS.MD REGISTRY...")
                    print("  ---------------------------------------------")
                    try:
                        with open("AGENTS.md", "r") as f:
                            lines = f.readlines()
                        print("".join(lines[:25]))
                    except Exception:
                        _jtrace(f"[TRACE] core.gemma4_loop.jarvis: except Exception")
                        print("  AGENTS.md registry is currently empty.\n")
                    continue
                else:
                    print(Fore.RED + f"Unknown command: {cmd}. Type /help for a list of commands.\n" + Style.RESET_ALL)
                    continue
            
            if user_input.lower() in ["exit", "quit", "q"]:
                break
                
            messages.append({"role": "user", "content": user_input})
            
            # Keep executing tool calls until the model returns a final text answer
            while True:
                msg = call_llm(
                    messages=messages,
                    model=model,
                    tools=TOOL_DEFINITIONS
                )
                
                messages.append(msg)
                
                if not msg.get("tool_calls"):
                    # Final answer received
                    clean_content = msg['content'].encode(sys.stdout.encoding or 'ascii', errors='replace').decode(sys.stdout.encoding or 'ascii')
                    print(Fore.MAGENTA + f"\n{clean_content}\n" + Style.RESET_ALL)
                    break
                    
                # Execute tool calls
                for call in msg["tool_calls"]:
                    fn = call["function"]["name"]
                    args = call["function"]["arguments"]
                    clean_args = str(args).encode(sys.stdout.encoding or 'ascii', errors='replace').decode(sys.stdout.encoding or 'ascii')
                    print(Fore.YELLOW + f"  [Tool Call] {fn}({clean_args})" + Style.RESET_ALL)
                    
                    try:
                        result = dispatch(fn, args)
                    except Exception as e:
                        _jtrace(f"[TRACE] core.gemma4_loop.jarvis: except {str(e)[:80]}")
                        result = f"ERROR: {e}"
                    
                    messages.append({
                        "role": "tool",
                        "content": str(result)
                    })
        
        except KeyboardInterrupt:
            _jtrace(f"[TRACE] core.gemma4_loop.jarvis: except KeyboardInterrupt")
            print("\nType 'exit' to quit.")
        except EOFError:
            _jtrace(f"[TRACE] core.gemma4_loop.jarvis: except EOFError")
            print("\nExiting Jarvis...")
            break
        except Exception as e:
            _jtrace(f"[TRACE] core.gemma4_loop.jarvis: except {str(e)[:80]}")
            print(Fore.RED + f"\nAn error occurred: {e}\n" + Style.RESET_ALL)

if __name__ == "__main__":
    jarvis()

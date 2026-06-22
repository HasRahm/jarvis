#!/usr/bin/env python3
"""
jarvis-cli.py — CLI wrapper for Jarvis agent integration with Claude Code.

Usage:
    python jarvis-cli.py --mode research --task "Find 20 AI startups hiring"
    python jarvis-cli.py --mode diagnose --task "Why won't Claude app open"
    python jarvis-cli.py --mode auto --task "Create a styled Excel tracker"
    python jarvis-cli.py --doctor   # Health check
"""

import os
import sys
import argparse
import uuid
import tempfile

# Fix Windows console encoding for emoji/unicode
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

# Ensure project root is on path
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))

# Auto-load .env so API keys are always available to Hermes subprocesses
_env_path = os.path.join(PROJECT_ROOT, ".env")
if os.path.isfile(_env_path):
    with open(_env_path, encoding="utf-8") as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _v = _line.split("=", 1)
                os.environ.setdefault(_k.strip(), _v.strip())
sys.path.insert(0, PROJECT_ROOT)


def _persist_env_var(key: str, value: str) -> None:
    """Write key=value into .env (replacing an existing line, else appending).

    Used to persist an auto-generated HERMES_SECRET so it stays stable across
    restarts and a paired phone's stored token keeps working.
    """
    print(f"[TRACE] jarvis-cli._persist_env_var: enter", file=sys.stderr, flush=True)
    lines = []
    found = False
    if os.path.isfile(_env_path):
        with open(_env_path, encoding="utf-8") as f:
            lines = f.read().splitlines()
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            if stripped.split("=", 1)[0].strip() == key:
                lines[i] = f"{key}={value}"
                found = True
                break
    if not found:
        lines.append(f"{key}={value}")
    with open(_env_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


MODES_DIR = os.path.join(PROJECT_ROOT, "modes")
SCRATCH_DIR = os.path.join(PROJECT_ROOT, "scratch")
VENV_PYTHON = os.path.join(PROJECT_ROOT, ".venv", "Scripts", "python.exe")
HERMES_RUNNER = os.path.join(PROJECT_ROOT, "core", "hermes", "hermes_cli_runner.py")

AVAILABLE_MODES = ["research", "diagnose", "browse", "desktop", "excel", "shell", "auto", "screen"]
DEFAULT_MODEL = os.environ.get("JARVIS_PRIMARY_MODEL", "gemma4:31b-cloud")


def doctor():
    """Health check — verify Ollama is running and model is available."""
    print(f"[TRACE] jarvis-cli.doctor: enter", file=sys.stderr, flush=True)
    print("🔍 Jarvis Health Check")
    print("=" * 40)

    # Check Python venv
    if os.path.exists(VENV_PYTHON):
        print(f"✅ Python venv: {VENV_PYTHON}")
    else:
        print(f"❌ Python venv not found: {VENV_PYTHON}")
        return False

    # Check Hermes runner
    if os.path.exists(HERMES_RUNNER):
        print(f"✅ Hermes runner: {HERMES_RUNNER}")
    else:
        print(f"❌ Hermes runner not found: {HERMES_RUNNER}")
        return False

    # Check modes directory
    if os.path.isdir(MODES_DIR):
        mode_files = [f for f in os.listdir(MODES_DIR) if f.endswith(".md")]
        print(f"✅ Modes directory: {len(mode_files)} modes found")
    else:
        print(f"❌ Modes directory not found: {MODES_DIR}")
        return False

    # Check Ollama
    try:
        import httpx
        resp = httpx.get("http://127.0.0.1:11434/api/tags", timeout=3)
        if resp.status_code == 200:
            models = resp.json().get("models", [])
            model_names = [m.get("name", "") for m in models]
            print(f"✅ Ollama server: running ({len(models)} models)")
            if DEFAULT_MODEL in model_names:
                print(f"✅ Model: {DEFAULT_MODEL} available")
            else:
                print(f"⚠️  Model: {DEFAULT_MODEL} not found. Available: {', '.join(model_names[:5])}")
        else:
            print(f"❌ Ollama server: HTTP {resp.status_code}")
            return False
    except Exception as e:
        print(f"[TRACE] jarvis-cli.doctor: except {str(e)[:80]}", file=sys.stderr, flush=True)
        print(f"❌ Ollama server: not reachable ({e})")
        return False

    # Check scratch directory
    os.makedirs(SCRATCH_DIR, exist_ok=True)
    print(f"✅ Scratch directory: {SCRATCH_DIR}")

    print("=" * 40)
    print("🟢 Jarvis is ready!")
    return True


def load_mode_instructions(mode: str) -> str:
    """Load behavioral instructions for a mode."""
    # Always load shared rules
    print(f"[TRACE] jarvis-cli.load_mode_instructions: enter", file=sys.stderr, flush=True)
    shared_path = os.path.join(MODES_DIR, "_shared.md")
    shared_content = ""
    if os.path.exists(shared_path):
        with open(shared_path, "r", encoding="utf-8") as f:
            shared_content = f.read().strip()

    # Load mode-specific instructions
    if mode == "auto":
        mode_content = (
            "You are Jarvis in Auto mode. Analyze the task and decide the best approach.\n"
            "You have access to: browser, shell, desktop automation, file system.\n"
            "Execute the task completely and autonomously."
        )
    else:
        mode_path = os.path.join(MODES_DIR, f"{mode}.md")
        if os.path.exists(mode_path):
            with open(mode_path, "r", encoding="utf-8") as f:
                mode_content = f.read().strip()
        else:
            print(f"⚠️  Mode file not found: {mode_path}, falling back to auto mode")
            mode_content = "Execute the task completely and autonomously using your available tools."

    composed = f"{shared_content}\n\n---\n\n{mode_content}"
    # Cluster 1: the mode files use {{OUTPUT_DIR}} where they previously hardcoded the install-dir
    # scratch path. Substitute the resolved output root so the model writes into the user's project.
    output_root = os.environ.get("JARVIS_OUTPUT_ROOT") or os.getcwd()
    return composed.replace("{{OUTPUT_DIR}}", output_root)


def build_prompt(mode: str, task: str) -> str:
    """Build the full prompt for Jarvis."""
    print(f"[TRACE] jarvis-cli.build_prompt: enter", file=sys.stderr, flush=True)
    instructions = load_mode_instructions(mode)
    output_root = os.environ.get("JARVIS_OUTPUT_ROOT") or os.getcwd()
    return f"""{instructions}

---

## YOUR TASK

{task}

## OUTPUT LOCATION
Write all generated files into the working directory: {output_root}
Use paths relative to it (e.g. `app/main.py`) or absolute paths under it. Do NOT write into the
Jarvis install directory.

IMPORTANT: Execute each step in order. Do NOT stop early. Do NOT ask for help. Complete the task fully.
"""


def run_jarvis(mode: str, task: str, model: str = DEFAULT_MODEL):
    """Launch Jarvis to execute a task."""
    # Build prompt
    print(f"[TRACE] jarvis-cli.run_jarvis: enter", file=sys.stderr, flush=True)
    prompt_content = build_prompt(mode, task)

    # Write prompt to temp file
    prompt_id = uuid.uuid4().hex[:8]
    prompt_path = os.path.join(SCRATCH_DIR, f"jarvis_prompt_{prompt_id}.txt")
    os.makedirs(SCRATCH_DIR, exist_ok=True)

    with open(prompt_path, "w", encoding="utf-8") as f:
        f.write(prompt_content)

    # Cluster 1: generated files must land in the user's working dir, not the install dir.
    # write_file resolves relative paths against the PROCESS cwd, so run the subprocess there.
    output_root = os.environ.get("JARVIS_OUTPUT_ROOT") or os.getcwd()

    print(f"🤖 Jarvis [{mode}] — Starting task...")
    print(f"   Model: {model}")
    print(f"   Output dir: {output_root}")
    print(f"   Task: {task[:100]}{'...' if len(task) > 100 else ''}")
    print("-" * 60)
    sys.stdout.flush()

    # Launch Hermes runner
    import subprocess
    result = subprocess.run(
        [VENV_PYTHON, "-u", HERMES_RUNNER, "-p", prompt_path, "-m", model],
        cwd=output_root,
        text=True,
        # Stream output directly to stdout
    )

    # Cleanup prompt file
    try:
        os.remove(prompt_path)
    except Exception:
        print(f"[TRACE] jarvis-cli.run_jarvis: except Exception", file=sys.stderr, flush=True)
        pass

    # Honest outcome (Phase 46): don't claim "completed successfully" — the runner above printed the
    # real result (incl. any model fallbacks / rate-limit retries). Just reflect the exit status.
    if result.returncode != 0:
        print(f"\n❌ Jarvis exited with code {result.returncode}")
        sys.exit(result.returncode)
    else:
        print(f"\n■ Jarvis run finished (exit 0). See the run summary above for what was done.")


def run_screen_dashboard(model: str = DEFAULT_MODEL):
    """Fetch active window structure, visual density imprint, and generate a cognitive visual summary."""
    print(f"[TRACE] jarvis-cli.run_screen_dashboard: enter", file=sys.stderr, flush=True)
    import asyncio
    from core.system.screen_reader import JarvisScreenReader
    from core.system.screen_imprint import ScreenImprintGraph
    
    print("🛸 Fetching Screen Understanding Data...")
    sys.stdout.flush()
    
    async def capture():
        print(f"[TRACE] jarvis-cli.run_screen_dashboard.capture: enter", file=sys.stderr, flush=True)
        reader = JarvisScreenReader()
        imprinter = ScreenImprintGraph()
        screen_data = await reader.read_screen()
        # ScreenImprintGraph.imprint() is synchronous — awaiting it raised
        # "object dict can't be used in 'await' expression" (smoke-test #3).
        imprint_data = imprinter.imprint()
        return screen_data, imprint_data
        
    try:
        screen, imprint = asyncio.run(capture())
    except Exception as e:
        print(f"[TRACE] jarvis-cli.run_screen_dashboard: except {str(e)[:80]}", file=sys.stderr, flush=True)
        print(f"❌ Screen capture failed: {e}")
        sys.exit(1)
        
    active = screen.get("active_app", {})
    summary = screen.get("summary", "No summary generated.")
    controls = screen.get("native_ui", [])
    ascii_map = imprint.get("imprint", {}).get("ascii_map", "")

    # Honest label (Phase 46): name the model that ACTUALLY generated the summary, not a hardcoded
    # "Gemma4" — the summary call falls back through the chain (often Kimi/etc.).
    try:
        from core.system.llm_adapter import get_last_run
        _vm = get_last_run().get("model_used") or "unknown model"
    except Exception:
        print(f"[TRACE] jarvis-cli.run_screen_dashboard: except Exception", file=sys.stderr, flush=True)
        _vm = "unknown model"

    print("┌──────────────────────────────────────────────────────────┐")
    print("│                     JARVIS VISUAL BLOCK                  │")
    print("└──────────────────────────────────────────────────────────┘")
    print(f"🖥️  ACTIVE WINDOW: {active.get('title', 'Unknown')}")
    print(f"⚙️  PROCESS:       {active.get('process_name', 'Unknown')} (PID: {active.get('pid', 'N/A')})")
    print(f"📏 COORDINATES:   {active.get('rect', {})}")
    print("-" * 60)
    print(f"📄 COGNITIVE SUMMARY (via {_vm}):")
    print(summary)
    print("-" * 60)
    print("🧩 TOP 10 VISIBLE ACTION CONTROLS:")
    valid_controls = [c for c in controls if c.get("text", "").strip()][:10]
    if valid_controls:
        for idx, ctrl in enumerate(valid_controls, 1):
            print(f"  {idx}. [{ctrl.get('class')}] '{ctrl.get('text')}' at {ctrl.get('rect')}")
    else:
        print("  No text-labeled controls detected.")
    print("-" * 60)
    print("🎨 DENSITY-BASED HALFTONE VISUAL IMPRINT:")
    print("```")
    print(ascii_map)
    print("```")
    print("🛸 End of Warp Block")
    sys.stdout.flush()


def check_tool_health():
    """Verify tool module dependencies and binaries on startup."""
    print(f"[TRACE] jarvis-cli.check_tool_health: enter", file=sys.stderr, flush=True)
    from tools.dispatcher import TOOL_DEFINITIONS
    
    defined_tools = {t["function"]["name"] for t in TOOL_DEFINITIONS if "function" in t}
    
    print("🛠️  Checking Tool Health...")
    has_errors = False
    
    browser_tools = {"browser_navigate", "browser_extract_text", "browser_click", "browser_screenshot"}
    if browser_tools.intersection(defined_tools):
        try:
            import playwright
            print("  ✓ browser_navigate (playwright chromium ready)")
        except ImportError:
            print(f"[TRACE] jarvis-cli.check_tool_health: except ImportError", file=sys.stderr, flush=True)
            print("  ✗ browser_navigate (playwright not found — run: pip install playwright && playwright install chromium)")
            has_errors = True

    if "screen_imprint" in defined_tools:
        try:
            import mss
            print("  ✓ screen_imprint (mss ready)")
        except ImportError:
            print(f"[TRACE] jarvis-cli.check_tool_health: except ImportError", file=sys.stderr, flush=True)
            print("  ✗ screen_imprint (mss not found — run: pip install mss)")
            has_errors = True

    if "screen_ocr" in defined_tools:
        try:
            import pytesseract
            import sys, os
            if sys.platform == "win32":
                tess_path = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
                if os.path.exists(tess_path):
                    if hasattr(pytesseract, 'pytesseract'):
                        pytesseract.pytesseract.tesseract_cmd = tess_path
                    else:
                        pytesseract.tesseract_cmd = tess_path
            pytesseract.get_tesseract_version()
            print("  ✓ screen_ocr (pytesseract ready)")
        except ImportError:
            print(f"[TRACE] jarvis-cli.check_tool_health: except ImportError", file=sys.stderr, flush=True)
            print("  ✗ screen_ocr (pytesseract not found — run: pip install pytesseract)")
            has_errors = True
        except Exception as e:
            print(f"[TRACE] jarvis-cli.check_tool_health: except {str(e)[:80]}", file=sys.stderr, flush=True)
            print(f"  ✗ screen_ocr (tesseract binary not found: {e} — please install tesseract)")
            has_errors = True
            
    if has_errors:
        print("\n❌ Tool health check failed. Please resolve the missing dependencies above.")
        import sys
        sys.exit(1)


def show_qr_code(hermes_secret: str = None):
    """Display the phone-pairing QR code.

    The QR encodes a phone-app URL with the WebSocket URL and auth token in the
    URL *fragment* (after #). Fragments are never transmitted to a server, so the
    token is delivered out-of-band — scanning the locally-shown QR pairs a fresh
    phone in one shot. The token is NEVER published to the public discovery gist.
    """
    print(f"[TRACE] jarvis-cli.show_qr_code: enter", file=sys.stderr, flush=True)
    from urllib.parse import quote
    from core.hermes.server import print_qr_code
    tunnel_url = os.getenv("CLOUDFLARE_TUNNEL_URL")
    if not tunnel_url:
        import httpx
        try:
            resp = httpx.get("https://gist.githubusercontent.com/HasRahm/e99532bb52fd6b67e77f759d9921d5d8/raw/jarvis-url.json", timeout=3)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("status") == "online":
                    tunnel_url = data.get("url")
        except Exception:
            print(f"[TRACE] jarvis-cli.show_qr_code: except Exception", file=sys.stderr, flush=True)
            pass
    if not tunnel_url:
        print("❌ No active tunnel URL found in .env or gist.")
        return

    secret = hermes_secret or os.getenv("HERMES_SECRET", "")
    ws_url = tunnel_url.replace("http", "ws") + "/ws"
    phone_app = os.getenv("JARVIS_PHONE_APP_URL", "https://jarvis-henna-nu.vercel.app")

    if secret:
        pair_url = f"{phone_app}/#u={quote(ws_url, safe='')}&t={quote(secret, safe='')}"
        print_qr_code(pair_url)
        # The token is a credential — don't splash it in plaintext by default (smoke-test #10).
        # The QR already carries it; scan it. Reveal the raw token only on explicit --show-token.
        if "--show-token" in sys.argv:
            print(f"\n🔑 Token (sensitive — for manual entry): {secret}")
        else:
            masked = (secret[:3] + "…" + secret[-2:]) if len(secret) > 6 else "•••"
            print(f"\n🔑 Token: {masked}  (scan the QR, or pass --show-token to reveal)")
        print(f"   WS URL: {ws_url}\n")
    else:
        # No secret available locally — fall back to URL-only QR; phone must have
        # the token already stored or entered manually.
        print_qr_code(ws_url)
        print("\n⚠️ HERMES_SECRET not set locally — phone must use a stored/manual token.\n")

def _run_json_stream():
    """Non-interactive JSON stream mode — emit each event as newline-delimited JSON.

    Usage:
        echo "what is 2+2" | python jarvis-cli.py --output json
        python jarvis-cli.py --output json --task "list files in C:/Users"

    Each stdout line is a JSON object with a 'type' field:
        {"type": "token",    "text": "..."         }  — streaming text chunk
        {"type": "tool",     "name": "...", "args": {...}  }  — tool call
        {"type": "result",   "name": "...", "output": "..." }  — tool result
        {"type": "done",     "text": "..."         }  — final full response
        {"type": "error",    "message": "..."      }  — error
    """
    print(f"[TRACE] jarvis-cli._run_json_stream: enter", file=sys.stderr, flush=True)
    import json as _json
    import io as _io
    import contextlib as _ctx
    from tools.dispatcher import dispatch, TOOL_DEFINITIONS
    from core.system import llm_adapter
    from core.system.llm_adapter import call_llm, set_stream_hook

    # NDJSON purity (smoke-test #2): stdout must contain ONLY JSON. Pin the real stdout for JSON
    # events, silence the adapter's banner, and redirect every other print to a sink.
    global _JSON_OUT
    _JSON_OUT = sys.stdout
    llm_adapter.QUIET_MODE = True
    _sink = _io.StringIO()

    model = os.environ.get("JARVIS_PRIMARY_MODEL", DEFAULT_MODEL)

    # Read task from --task flag or stdin
    task = None
    if "--task" in sys.argv:
        idx = sys.argv.index("--task")
        if idx + 1 < len(sys.argv):
            task = sys.argv[idx + 1]
    if not task:
        if not sys.stdin.isatty():
            task = sys.stdin.read().strip()
    if not task:
        _emit_json({"type": "error", "message": "--task or stdin required in --output json mode"})
        return

    instructions = load_mode_instructions("auto")
    system_msg = (
        "You are Jarvis. Complete the user task using tools as needed. "
        "Reply only with the final answer.\n\n" + instructions
    )
    messages = [
        {"role": "system", "content": system_msg},
        {"role": "user", "content": task},
    ]

    buf = {"text": ""}

    def hook(token, kind):
        if kind == "content":
            buf["text"] += token
            _emit_json({"type": "token", "text": token})

    while True:
        set_stream_hook(hook)
        try:
            # Redirect adapter stdout (routing lines, etc.) to the sink; JSON tokens still go to
            # the pinned _JSON_OUT via _emit_json, keeping stdout valid NDJSON.
            with _ctx.redirect_stdout(_sink):
                msg = call_llm(messages=messages, model=model, tools=TOOL_DEFINITIONS)
        except Exception as e:
            print(f"[TRACE] jarvis-cli._run_json_stream: except {str(e)[:80]}", file=sys.stderr, flush=True)
            _emit_json({"type": "error", "message": str(e)})
            return
        finally:
            set_stream_hook(None)

        messages.append(msg)

        if not msg.get("tool_calls"):
            _emit_json({"type": "done", "text": msg.get("content", buf["text"])})
            return

        for call in msg["tool_calls"]:
            fn = call["function"]["name"]
            args = call["function"]["arguments"]
            _emit_json({"type": "tool", "name": fn, "args": args})
            try:
                with _ctx.redirect_stdout(_sink):
                    result = dispatch(fn, args)
            except Exception as e:
                print(f"[TRACE] jarvis-cli._run_json_stream: except {str(e)[:80]}", file=sys.stderr, flush=True)
                result = f"ERROR: {e}"
            _emit_json({"type": "result", "name": fn, "output": str(result)[:2000]})
            _tcid = call.get("id")
            _tm = {"role": "tool", "content": str(result)}
            if _tcid:
                _tm["tool_call_id"] = _tcid
            messages.append(_tm)


_JSON_OUT = None   # pinned real stdout for NDJSON, so adapter chatter can be redirected away


def _emit_json(obj: dict):
    """Write a JSON event line to the pinned JSON stdout (never the redirected sink)."""
    print(f"[TRACE] jarvis-cli._emit_json: enter", file=sys.stderr, flush=True)
    import json as _json
    out = _JSON_OUT or sys.stdout
    out.write(_json.dumps(obj, ensure_ascii=False) + "\n")
    out.flush()


def main():
    # Hard offline / no-cloud switch (smoke-test #1). Set BEFORE the early --output/--tui branches
    # so every path — including JSON and --screen — refuses cloud calls and can't spend credits.
    print(f"[TRACE] jarvis-cli.main: enter", file=sys.stderr, flush=True)
    if "--offline" in sys.argv or "--no-cloud" in sys.argv:
        os.environ["JARVIS_OFFLINE"] = "1"

    # Output root (Phase 46 cluster 1): generated code lands in the USER's working dir (or
    # --output-dir), NOT the install dir. Resolve + export BEFORE the early branches so the
    # subprocess, agent workspaces, and prompt instructions all agree.
    _out_dir = None
    for _flag in ("--output-dir", "-o"):
        if _flag in sys.argv:
            _i = sys.argv.index(_flag)
            if _i + 1 < len(sys.argv):
                _out_dir = sys.argv[_i + 1]
            break
    os.environ.setdefault("JARVIS_OUTPUT_ROOT", os.path.abspath(_out_dir) if _out_dir else os.getcwd())

    # No arguments → launch the inline streaming REPL (Claude Code / Gemini CLI style).
    # --tui explicitly launches the full-screen Textual dashboard instead.
    if len(sys.argv) == 1:
        from core.cli.repl import JarvisRepl
        JarvisRepl().run()
        sys.exit(0)
    # --output json → non-interactive JSON stream mode (for piping / scripting)
    if "--output" in sys.argv:
        idx = sys.argv.index("--output")
        if idx + 1 < len(sys.argv) and sys.argv[idx + 1] == "json":
            _run_json_stream()
            sys.exit(0)
    if "--tui" in sys.argv:
        from core.cli.app import JarvisTuiApp
        app = JarvisTuiApp()
        app.run()
        sys.exit(0)

    parser = argparse.ArgumentParser(
        description="Jarvis CLI — Delegate tasks to local AI agent",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python jarvis-cli.py                  # Launches the inline streaming REPL (default)
  python jarvis-cli.py --tui            # Launches the full-screen Textual dashboard
  python jarvis-cli.py --doctor
  python jarvis-cli.py --screen
  python jarvis-cli.py --mode research --task "Find 20 AI startups hiring"
  python jarvis-cli.py --mode diagnose --task "Why won't Claude app open"
  python jarvis-cli.py --mode excel --task "Create a job tracker spreadsheet"
  python jarvis-cli.py --mode auto --task "Check disk space and clean temp files"
        """
    )
    parser.add_argument("--tui", action="store_true", help="Launch the full-screen Textual dashboard (default is the inline REPL)")
    parser.add_argument("--doctor", action="store_true", help="Run health check")
    parser.add_argument("--screen", action="store_true", help="Dump visual screen block dashboard")
    parser.add_argument("--remote", action="store_true", help="Start Hermes server and show QR code")
    parser.add_argument("--pair", action="store_true", help="Show QR code for existing Hermes session")
    parser.add_argument("--show-token", action="store_true", help="With --pair, print the raw auth token (sensitive; masked by default)")
    parser.add_argument("--mode", "-m", choices=AVAILABLE_MODES, default="auto",
                        help="Jarvis mode (default: auto)")
    parser.add_argument("--task", "-t", type=str, help="Task description")
    parser.add_argument("--model", default=DEFAULT_MODEL,
                        help=f"Chat/orchestrator primary model (default: {DEFAULT_MODEL}). "
                             "Does NOT control vision or document-generation, which route separately.")
    parser.add_argument("--output", choices=["json"], default=None,
                        help="Output format: 'json' emits newline-delimited JSON events (for scripting)")
    parser.add_argument("--offline", "--no-cloud", dest="offline", action="store_true",
                        help="Hard offline mode: only local Ollama, never call paid/cloud models")
    parser.add_argument("--output-dir", "-o", dest="output_dir", default=None,
                        help="Directory to write generated files into (default: current directory)")

    args = parser.parse_args()

    if args.offline:
        os.environ["JARVIS_OFFLINE"] = "1"
    if args.output_dir:
        os.environ["JARVIS_OUTPUT_ROOT"] = os.path.abspath(args.output_dir)

    # Validate --model loudly (Phase 46): a bogus model must error, not silently fall through the
    # fallback chain and answer as if nothing happened.
    try:
        from agents.model_router import validate_model
        _ok, _why = validate_model(args.model)
        if not _ok:
            print(f"❌ --model: {_why}")
            sys.exit(2)
    except ImportError:
        print(f"[TRACE] jarvis-cli.main: except ImportError", file=sys.stderr, flush=True)
        pass

    if args.tui:
        from core.cli.app import JarvisTuiApp
        app = JarvisTuiApp()
        app.run()
        sys.exit(0)

    if args.doctor:
        success = doctor()
        sys.exit(0 if success else 1)

    if args.screen:
        run_screen_dashboard(args.model)
        sys.exit(0)

    if args.pair:
        show_qr_code()
        sys.exit(0)

    if args.remote:
        import subprocess
        import time
        import tempfile
        import re
        import datetime
        import json
        import secrets as _secrets

        print("⚡ Starting Jarvis Hermes Bridge...")

        # 0. Ensure a strong auth secret BEFORE the server module is imported.
        #    The token is NEVER published to the public discovery gist — it is
        #    delivered out-of-band via the locally-shown QR fragment / manual entry.
        hermes_secret = os.getenv("HERMES_SECRET")
        if not hermes_secret:
            hermes_secret = _secrets.token_urlsafe(32)
            os.environ["HERMES_SECRET"] = hermes_secret
            _persist_env_var("HERMES_SECRET", hermes_secret)
            print("🔐 Generated a new HERMES_SECRET and saved it to .env")

        import uvicorn

        # 1. Boot cloudflared tunnel
        cf_log = tempfile.mktemp()
        cf_cmd = ["cloudflared", "tunnel", "--url", "http://localhost:9000"]
        if sys.platform == "win32":
            if os.path.exists(r"C:\Program Files (x86)\cloudflared\cloudflared.exe"):
                cf_cmd[0] = r"C:\Program Files (x86)\cloudflared\cloudflared.exe"
            elif os.path.exists(r"C:\Program Files\cloudflared\cloudflared.exe"):
                cf_cmd[0] = r"C:\Program Files\cloudflared\cloudflared.exe"
                
        try:
            with open(cf_log, "w") as f:
                cf_proc = subprocess.Popen(cf_cmd, stderr=f, stdout=subprocess.DEVNULL)
        except Exception as e:
            print(f"[TRACE] jarvis-cli.main: except {str(e)[:80]}", file=sys.stderr, flush=True)
            print(f"❌ Failed to start cloudflared: {e}")
            sys.exit(1)
            
        print("⏳ Waiting for Cloudflare Tunnel URL...")
        tunnel_url = None
        for _ in range(30):
            time.sleep(1)
            try:
                with open(cf_log, "r") as f:
                    content = f.read()
                    match = re.search(r"https://[a-z0-9\-]+\.trycloudflare\.com", content)
                    if match:
                        tunnel_url = match.group(0)
                        break
            except Exception:
                print(f"[TRACE] jarvis-cli.main: except Exception", file=sys.stderr, flush=True)
                pass

        gist_id = "e99532bb52fd6b67e77f759d9921d5d8"

        def _publish_gist(status: str, url: str):
            """Publish ONLY the discovery URL + status to the public gist.

            The auth token is deliberately omitted — publishing it would expose a
            full-RCE agent to anyone who can read the world-readable gist.
            """
            print(f"[TRACE] jarvis-cli.main._publish_gist: enter", file=sys.stderr, flush=True)
            payload = {
                "url": url,
                "updated": datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
                "status": status,
            }
            tmp_json = tempfile.mktemp(suffix=".json")
            try:
                with open(tmp_json, "w") as f:
                    json.dump(payload, f)
                subprocess.run(
                    ["gh", "gist", "edit", gist_id, tmp_json],
                    check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                )
                return True
            except Exception as e:
                print(f"[TRACE] jarvis-cli.main._publish_gist: except {str(e)[:80]}", file=sys.stderr, flush=True)
                print(f"⚠️ Gist update failed: {e}. Is 'gh' CLI installed and authenticated?")
                return False
            finally:
                try:
                    os.remove(tmp_json)
                except OSError:
                    print(f"[TRACE] jarvis-cli.main._publish_gist: except OSError", file=sys.stderr, flush=True)
                    pass

        if tunnel_url:
            print(f"✅ Tunnel live: {tunnel_url}")
            os.environ["CLOUDFLARE_TUNNEL_URL"] = tunnel_url
            if _publish_gist("online", tunnel_url):
                print("✅ Phone discovery Gist updated (URL only — token stays local).")
            show_qr_code(hermes_secret=hermes_secret)
        else:
            print("⚠️ Could not acquire tunnel URL.")

        try:
            uvicorn.run("core.hermes.server:app", host="0.0.0.0", port=9000, reload=False)
        finally:
            cf_proc.terminate()
            if tunnel_url:
                _publish_gist("offline", "")
        sys.exit(0)

    if not args.task:
        parser.error("--task is required (unless using --tui, --doctor, --screen, --remote, or --pair)")

    check_tool_health()
    run_jarvis(args.mode, args.task, args.model)



if __name__ == "__main__":
    main()

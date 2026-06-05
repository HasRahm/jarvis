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
sys.path.insert(0, PROJECT_ROOT)

MODES_DIR = os.path.join(PROJECT_ROOT, "modes")
SCRATCH_DIR = os.path.join(PROJECT_ROOT, "scratch")
VENV_PYTHON = os.path.join(PROJECT_ROOT, ".venv", "Scripts", "python.exe")
HERMES_RUNNER = os.path.join(PROJECT_ROOT, "core", "hermes", "hermes_cli_runner.py")

AVAILABLE_MODES = ["research", "diagnose", "browse", "desktop", "excel", "shell", "auto", "screen"]
DEFAULT_MODEL = os.environ.get("JARVIS_PRIMARY_MODEL", "gemma4:31b-cloud")


def doctor():
    """Health check — verify Ollama is running and model is available."""
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

    return f"{shared_content}\n\n---\n\n{mode_content}"


def build_prompt(mode: str, task: str) -> str:
    """Build the full prompt for Jarvis."""
    instructions = load_mode_instructions(mode)
    return f"""{instructions}

---

## YOUR TASK

{task}

IMPORTANT: Execute each step in order. Do NOT stop early. Do NOT ask for help. Complete the task fully.
"""


def run_jarvis(mode: str, task: str, model: str = DEFAULT_MODEL):
    """Launch Jarvis to execute a task."""
    # Build prompt
    prompt_content = build_prompt(mode, task)

    # Write prompt to temp file
    prompt_id = uuid.uuid4().hex[:8]
    prompt_path = os.path.join(SCRATCH_DIR, f"jarvis_prompt_{prompt_id}.txt")
    os.makedirs(SCRATCH_DIR, exist_ok=True)

    with open(prompt_path, "w", encoding="utf-8") as f:
        f.write(prompt_content)

    print(f"🤖 Jarvis [{mode}] — Starting task...")
    print(f"   Model: {model}")
    print(f"   Prompt: {prompt_path}")
    print(f"   Task: {task[:100]}{'...' if len(task) > 100 else ''}")
    print("-" * 60)
    sys.stdout.flush()

    # Launch Hermes runner
    import subprocess
    result = subprocess.run(
        [VENV_PYTHON, "-u", HERMES_RUNNER, "-p", prompt_path, "-m", model],
        cwd=PROJECT_ROOT,
        text=True,
        # Stream output directly to stdout
    )

    # Cleanup prompt file
    try:
        os.remove(prompt_path)
    except Exception:
        pass

    if result.returncode != 0:
        print(f"\n❌ Jarvis exited with code {result.returncode}")
        sys.exit(result.returncode)
    else:
        print(f"\n✅ Jarvis completed successfully")


def run_screen_dashboard(model: str = DEFAULT_MODEL):
    """Fetch active window structure, visual density imprint, and generate a cognitive visual summary."""
    import asyncio
    from core.system.screen_reader import JarvisScreenReader
    from core.system.screen_imprint import ScreenImprintGraph
    
    print("🛸 Fetching Screen Understanding Data...")
    sys.stdout.flush()
    
    async def capture():
        reader = JarvisScreenReader()
        imprinter = ScreenImprintGraph()
        screen_data = await reader.read_screen()
        imprint_data = await imprinter.imprint()
        return screen_data, imprint_data
        
    try:
        screen, imprint = asyncio.run(capture())
    except Exception as e:
        print(f"❌ Screen capture failed: {e}")
        sys.exit(1)
        
    active = screen.get("active_app", {})
    summary = screen.get("summary", "No summary generated.")
    controls = screen.get("native_ui", [])
    ascii_map = imprint.get("imprint", {}).get("ascii_map", "")
    
    print("┌──────────────────────────────────────────────────────────┐")
    print("│                     JARVIS VISUAL BLOCK                  │")
    print("└──────────────────────────────────────────────────────────┘")
    print(f"🖥️  ACTIVE WINDOW: {active.get('title', 'Unknown')}")
    print(f"⚙️  PROCESS:       {active.get('process_name', 'Unknown')} (PID: {active.get('pid', 'N/A')})")
    print(f"📏 COORDINATES:   {active.get('rect', {})}")
    print("-" * 60)
    print("📄 COGNITIVE SUMMARY (Gemma4 Visual Cortex):")
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


def main():
    # If run with no arguments, or explicitly with --tui, launch the TUI Console
    if len(sys.argv) == 1 or "--tui" in sys.argv:
        from core.cli.app import JarvisTuiApp
        app = JarvisTuiApp()
        app.run()
        sys.exit(0)

    parser = argparse.ArgumentParser(
        description="Jarvis CLI — Delegate tasks to local AI agent",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python jarvis-cli.py                  # Launches interactive TUI Console
  python jarvis-cli.py --doctor
  python jarvis-cli.py --screen
  python jarvis-cli.py --mode research --task "Find 20 AI startups hiring"
  python jarvis-cli.py --mode diagnose --task "Why won't Claude app open"
  python jarvis-cli.py --mode excel --task "Create a job tracker spreadsheet"
  python jarvis-cli.py --mode auto --task "Check disk space and clean temp files"
        """
    )
    parser.add_argument("--tui", action="store_true", help="Launch interactive TUI Console")
    parser.add_argument("--doctor", action="store_true", help="Run health check")
    parser.add_argument("--screen", action="store_true", help="Dump visual screen block dashboard")
    parser.add_argument("--mode", "-m", choices=AVAILABLE_MODES, default="auto",
                        help="Jarvis mode (default: auto)")
    parser.add_argument("--task", "-t", type=str, help="Task description")
    parser.add_argument("--model", default=DEFAULT_MODEL,
                        help=f"Ollama model to use (default: {DEFAULT_MODEL})")

    args = parser.parse_args()

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

    if not args.task:
        parser.error("--task is required (unless using --tui, --doctor, or --screen)")

    run_jarvis(args.mode, args.task, args.model)



if __name__ == "__main__":
    main()

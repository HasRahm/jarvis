import os
import sys
import importlib.util
from rich.text import Text
from rich.panel import Panel
from textual import work
from textual.app import App, ComposeResult
from textual.containers import Container, Vertical, Horizontal
from textual.widgets import Static, Input, ListView, ListItem, Label, RichLog

# Available slash commands for the command palette
SLASH_COMMANDS = [
    ("/research", "Web research & job search", "/research"),
    ("/diagnose", "System troubleshooting & debugging", "/diagnose"),
    ("/browse", "Scrape a specific URL", "/browse"),
    ("/desktop", "Desktop GUI automation", "/desktop"),
    ("/excel", "Beautiful spreadsheet generation", "/excel"),
    ("/shell", "Multi-step shell execution", "/shell"),
    ("/screen", "Audit current screen & visual layout", "/screen"),
    ("/doctor", "Verify Ollama & system health status", "/doctor"),
    ("/auto", "Let Jarvis decide the best approach", "/auto")
]

class AgentStrip(Static):
    """Horizontal status widget displaying the active agent list and their statuses from AGENTS.md."""
    def on_mount(self) -> None:
        self.update_status()
        self.set_interval(1.0, self.update_status)

    def update_status(self) -> None:
        agents = []
        try:
            agents_md_path = os.path.join(os.getcwd(), "AGENTS.md")
            if os.path.exists(agents_md_path):
                with open(agents_md_path, "r", encoding="utf-8") as f:
                    lines = f.readlines()
                for line in lines:
                    if "|" in line and "Agent" not in line and "---" not in line:
                        parts = [p.strip() for p in line.split("|")[1:-1]]
                        if len(parts) >= 3:
                            agents.append(parts)
        except Exception:
            pass

        if not agents:
            agents = [
                ["frontend", "gemini-3.1-pro-preview", "IDLE", "---"],
                ["backend", "claude-sonnet-4-6", "DONE", "Created 2 files"],
                ["qa", "gpt-5.4", "DONE", "PASSED"],
                ["iac", "claude-sonnet-4-6", "IDLE", "---"]
            ]

        status_text = Text()
        for idx, row in enumerate(agents):
            agent, model, status, step = row[0], row[1], row[2], row[3] if len(row) > 3 else "---"
            color = {
                "idle": "dim white",
                "working": "yellow",
                "done": "green",
                "passed": "bold green",
                "suspended": "red",
                "in_progress": "yellow"
            }.get(status.lower(), "white")

            status_text.append(f"{agent.upper()} ", style="bold cyan")
            status_text.append(f"({model})", style="dim")
            status_text.append(f": {status} ", style=color)
            if step and step != "---":
                status_text.append(f"· {step} ", style="italic dim")

            if idx < len(agents) - 1:
                status_text.append("   |   ", style="dim")

        self.update(status_text)


class TextualStreamRedirector:
    """Redirects file write streams (stdout/stderr) into the TUI's output stream."""
    def __init__(self, write_func):
        self.write_func = write_func

    def write(self, data: str) -> None:
        if data:
            self.write_func(data)

    def flush(self) -> None:
        pass


class JarvisTuiApp(App):
    """The central Textual TUI Application for Jarvis."""

    CSS = """
    Screen {
        background: #0a0c0f;
        color: #E6E9EF;
        font-family: monospace;
    }

    #header_title {
        background: #080a0c;
        color: #5EEAD4;
        text-align: center;
        text-style: bold;
        height: 1;
        border-bottom: solid rgba(255, 255, 255, 0.08);
    }

    AgentStrip {
        background: #080a0c;
        border-bottom: solid rgba(255, 255, 255, 0.08);
        height: 3;
        padding: 0 1;
        content-align: center middle;
    }

    RichLog {
        height: 1fr;
        border: none;
        background: transparent;
    }

    #input_container {
        height: auto;
        border-top: solid rgba(255, 255, 255, 0.08);
        background: #080a0c;
        dock: bottom;
        layout: vertical;
    }

    #dropdown_palette {
        background: #0d1117;
        border: solid #5EEAD4;
        height: 8;
        max-height: 8;
        display: none;
    }

    #dropdown_palette.visible {
        display: block;
    }

    ListItem {
        padding: 0 1;
    }

    Input {
        border: none;
        background: transparent;
        color: #E6E9EF;
    }
    """

    def compose(self) -> ComposeResult:
        yield Label("JARVIS // OPERATOR CONSOLE", id="header_title")
        yield AgentStrip()
        yield RichLog(id="output_stream", highlight=True, markup=True)
        with Vertical(id="input_container"):
            yield ListView(id="dropdown_palette")
            yield Input(placeholder="Type a task, or '/' for command palette...", id="cli_input")

    def on_mount(self) -> None:
        self.log_stream = self.query_one("#output_stream", RichLog)
        self.dropdown = self.query_one("#dropdown_palette", ListView)
        self.cli_input = self.query_one("#cli_input", Input)
        self.cli_input.focus()

        # Print banner
        self.log_stream.write(Text.from_markup(
            "[bold cyan]Welcome to Jarvis Operator Console![/]\n"
            "[dim]Type '/' to list modes or enter a task to execute autonomously.[/]\n"
        ))

    def on_input_changed(self, event: Input.Changed) -> None:
        val = event.value
        if val.startswith("/"):
            self.dropdown.add_class("visible")
            self.dropdown.clear()
            
            # Filter commands
            search = val.lower()
            matches = [c for c in SLASH_COMMANDS if c[0].startswith(search)]
            
            for cmd, desc, autocomplete in matches:
                li = ListItem(Label(f"{cmd:<12} {desc}"), id=f"item_{cmd[1:]}")
                li.cmd_text = autocomplete
                self.dropdown.append(li)
                
            if not matches:
                self.dropdown.remove_class("visible")
            else:
                self.dropdown.index = 0
        else:
            self.dropdown.remove_class("visible")

    def on_key(self, event) -> None:
        if "visible" in self.dropdown.classes:
            if event.key == "up":
                event.prevent_default()
                if self.dropdown.index is not None and len(self.dropdown) > 0:
                    self.dropdown.index = (self.dropdown.index - 1) % len(self.dropdown)
            elif event.key == "down":
                event.prevent_default()
                if self.dropdown.index is not None and len(self.dropdown) > 0:
                    self.dropdown.index = (self.dropdown.index + 1) % len(self.dropdown)
            elif event.key == "enter":
                if self.dropdown.index is not None and len(self.dropdown) > 0:
                    event.prevent_default()
                    selected_item = self.dropdown.children[self.dropdown.index]
                    cmd_text = getattr(selected_item, "cmd_text", "")
                    self.cli_input.value = cmd_text + " "
                    self.dropdown.remove_class("visible")

    def on_input_submitted(self, event: Input.Submitted) -> None:
        # If dropdown is visible, ignore direct submission (key handler handles it)
        if "visible" in self.dropdown.classes:
            return

        text = event.value.strip()
        if not text:
            return

        self.cli_input.value = ""
        self.cli_input.disabled = True

        # Parse command
        mode = "auto"
        task = text

        for cmd, _, _ in SLASH_COMMANDS:
            if text.startswith(cmd):
                mode = cmd[1:]
                task = text[len(cmd):].strip()
                break

        # Check special commands
        if mode == "doctor":
            self.run_doctor()
        elif mode == "screen":
            self.run_screen()
        else:
            # Start background worker
            self.run_task_worker(mode, task)

    def enable_input(self) -> None:
        self.cli_input.disabled = False
        self.cli_input.focus()

    @work(thread=True)
    def run_task_worker(self, mode: str, task: str) -> None:
        self.call_from_thread(self.log_stream.write, Text.from_markup(f"\n[bold cyan]🤖 Jarvis [{mode}] — Starting task...[/]"))
        self.call_from_thread(self.log_stream.write, Text.from_markup(f"[dim]Task: {task}[/]\n"))

        old_stdout = sys.stdout
        old_stderr = sys.stderr

        def write_to_tui(data: str) -> None:
            self.call_from_thread(self.log_stream.write, Text.from_ansi(data))

        sys.stdout = TextualStreamRedirector(write_to_tui)
        sys.stderr = TextualStreamRedirector(write_to_tui)

        try:
            # Dynamically import jarvis-cli helpers
            spec = importlib.util.spec_from_file_location("jarvis_cli", "jarvis-cli.py")
            jarvis_cli = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(jarvis_cli)

            from core.hermes.hermes_cli_runner import EnvironmentHandshake, SkillsEngine, call_llm
            from tools.dispatcher import TOOL_DEFINITIONS, dispatch

            prompt_content = jarvis_cli.build_prompt(mode, task)
            handshake = EnvironmentHandshake()
            
            system_instruction = (
                "You are Jarvis, a powerful AI assistant with full access to this computer via tools. Use your tools to accomplish the user's tasks. "
                "Before answering a user prompt, ALWAYS call brain_query with the user's intent to check past context or memory.\n\n"
                "For complex build tasks that involve multiple components, use the delegate_task tool.\n"
                f"{handshake.get_system_prompt_addition()}"
            )
            
            skills_engine = SkillsEngine()
            skills_addition = skills_engine.get_skills_prompt_addition(prompt_content)
            
            messages = [
                {"role": "system", "content": system_instruction + skills_addition},
                {"role": "user", "content": prompt_content}
            ]
            
            model = jarvis_cli.DEFAULT_MODEL
            
            while True:
                msg = call_llm(messages=messages, model=model, tools=TOOL_DEFINITIONS)
                messages.append(msg)
                
                if not msg.get("tool_calls"):
                    # Stream the final response
                    final_content = msg.get("content", "")
                    clean_final = final_content.encode('utf-8', errors='replace').decode('utf-8')
                    print(f"\n{clean_final}\n")
                    break
                
                # Execute tool calls
                for call in msg["tool_calls"]:
                    fn = call["function"]["name"]
                    fn_args = call["function"]["arguments"]
                    
                    print(f"  [Hermes Tool Call] {fn}({fn_args})")
                    
                    try:
                        result = dispatch(fn, fn_args)
                    except Exception as e:
                        result = f"ERROR: {e}"
                        
                    result_preview = str(result)[:300]
                    print(f"  [Hermes Tool Result] {fn} -> {result_preview}")
                    
                    messages.append({
                        "role": "tool",
                        "content": str(result)
                    })
                    
                print(f"  [Hermes] All tool calls processed. Calling LLM again...")
                
            print(f"\n✅ Jarvis completed successfully")
        except Exception as e:
            print(f"\n❌ Exception occurred during execution: {e}")
        finally:
            sys.stdout = old_stdout
            sys.stderr = old_stderr
            self.call_from_thread(self.enable_input)

    @work(thread=True)
    def run_doctor(self) -> None:
        self.call_from_thread(self.log_stream.write, Text.from_markup("\n[bold cyan]🔍 Running Jarvis Health Check...[/]"))
        
        old_stdout = sys.stdout
        old_stderr = sys.stderr

        def write_to_tui(data: str) -> None:
            self.call_from_thread(self.log_stream.write, Text.from_ansi(data))

        sys.stdout = TextualStreamRedirector(write_to_tui)
        sys.stderr = TextualStreamRedirector(write_to_tui)

        try:
            spec = importlib.util.spec_from_file_location("jarvis_cli", "jarvis-cli.py")
            jarvis_cli = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(jarvis_cli)
            jarvis_cli.doctor()
        except Exception as e:
            print(f"Error running doctor: {e}")
        finally:
            sys.stdout = old_stdout
            sys.stderr = old_stderr
            self.call_from_thread(self.enable_input)

    @work(thread=True)
    def run_screen(self) -> None:
        self.call_from_thread(self.log_stream.write, Text.from_markup("\n[bold cyan]🖥️  Fetching Screen Understanding...[/]"))
        
        old_stdout = sys.stdout
        old_stderr = sys.stderr

        def write_to_tui(data: str) -> None:
            self.call_from_thread(self.log_stream.write, Text.from_ansi(data))

        sys.stdout = TextualStreamRedirector(write_to_tui)
        sys.stderr = TextualStreamRedirector(write_to_tui)

        try:
            spec = importlib.util.spec_from_file_location("jarvis_cli", "jarvis-cli.py")
            jarvis_cli = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(jarvis_cli)
            jarvis_cli.run_screen_dashboard()
        except Exception as e:
            print(f"Error running screen: {e}")
        finally:
            sys.stdout = old_stdout
            sys.stderr = old_stderr
            self.call_from_thread(self.enable_input)

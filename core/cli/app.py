import os
import sys
from core.trace import trace as _jtrace
import importlib.util
from datetime import datetime
from rich.text import Text
from rich.table import Table
from textual import work
from textual.app import App, ComposeResult
from textual.containers import Vertical
from textual.widgets import Static, Input, ListView, ListItem, Label, RichLog

# ── Slash command registry ──────────────────────────────────────────────────
# Each entry: (command, description, autocomplete_text)
SLASH_COMMANDS = [
    # Core automation modes
    ("/research",  "Web research & job search",                        "/research"),
    ("/diagnose",  "System troubleshooting & debugging",               "/diagnose"),
    ("/browse",    "Scrape a URL or extract web content",              "/browse"),
    ("/desktop",   "Desktop GUI automation — mouse, keyboard, windows","/desktop"),
    ("/excel",     "Generate styled spreadsheets from data",           "/excel"),
    ("/shell",     "Run multi-step shell command sequences",           "/shell"),
    ("/auto",      "Let Jarvis pick the best approach",                "/auto"),
    # Awareness
    ("/screen",    "Audit current screen, controls & layout",          "/screen"),
    ("/doctor",    "Verify Ollama, tools & system health",             "/doctor"),
    # Knowledge
    ("/vocab",     "Show the visual vocabulary cheatsheet",            "/vocab"),
    # Model control
    ("/model",     "Show or switch the primary orchestration model",   "/model"),
    ("/models",    "List native models; /models <query> searches OpenRouter", "/models"),
    ("/agents",    "Show the model assigned to each agent/role",        "/agents"),
    ("/setmodel",  "Assign any (OpenRouter) model to an agent",         "/setmodel"),
    ("/resetmodel","Clear an agent's model override",                   "/resetmodel"),
    # Tools & session
    ("/tools",     "List every registered tool with its category",     "/tools"),
    ("/history",   "View recent task & automation log",                "/history"),
    ("/export",    "Export this session to a markdown file",           "/export"),
    # Agent perception & cursor (Phase 24)
    ("/agentview", "Toggle/open annotated agent-view screenshots",     "/agentview"),
    ("/cursor",    "Toggle the visible agent cursor overlay",          "/cursor"),
    # UI controls
    ("/clear",     "Clear the output stream",                          "/clear"),
    ("/theme",     "Switch theme: dark | matrix | light | ocean",      "/theme"),
    ("/help",      "Show all commands & usage guide",                  "/help"),
    # Remote
    ("/remote",    "Start Hermes remote-pairing session with phone",   "/remote"),
    # Session
    ("/save",      "Save current session to ~/.jarvis/sessions/",      "/save"),
    ("/load",      "Restore most-recent saved session",                "/load"),
    ("/forget",    "Clear this directory's memory — start fresh",      "/forget"),
    ("/context",   "Show active JARVIS.md project context file",       "/context"),
    # Coding mode
    ("/build",     "Build software with coding agents (game/app/script/tool)", "/build"),
    ("/code",      "Alias for /build — force coding agent mode",              "/code"),
]

# Commands handled inline in the TUI (no Jarvis subprocess needed)
_INLINE_COMMANDS = {"/clear", "/help", "/theme", "/model", "/models", "/tools",
                    "/history", "/export", "/vocab", "/save", "/load", "/context",
                    "/build", "/code", "/agents", "/setmodel", "/resetmodel"}

# ── Theme definitions ───────────────────────────────────────────────────────
_THEMES = {
    "dark": {
        "bg":          "#0a0c0f",
        "header_bg":   "#080a0c",
        "border":      "rgba(255,255,255,0.08)",
        "accent":      "#5EEAD4",
        "text":        "#E6E9EF",
        "dropdown_bg": "#0d1117",
    },
    "matrix": {
        "bg":          "#000900",
        "header_bg":   "#000600",
        "border":      "rgba(0,255,80,0.18)",
        "accent":      "#00FF50",
        "text":        "#A8FFB0",
        "dropdown_bg": "#001800",
    },
    "light": {
        "bg":          "#F5F7FA",
        "header_bg":   "#EAEDF0",
        "border":      "rgba(0,0,0,0.10)",
        "accent":      "#0070F3",
        "text":        "#111827",
        "dropdown_bg": "#FFFFFF",
    },
    "ocean": {
        "bg":          "#060F1F",
        "header_bg":   "#040C18",
        "border":      "rgba(56,189,248,0.15)",
        "accent":      "#38BDF8",
        "text":        "#BAE6FD",
        "dropdown_bg": "#0A1628",
    },
    "warm": {
        "bg":          "#1B1714",
        "header_bg":   "#211C18",
        "border":      "rgba(224,138,95,0.20)",
        "accent":      "#E08A5F",
        "text":        "#E9E1D4",
        "dropdown_bg": "#221F19",
        # Phase 40 — extra keys for the warm-elegant REPL (additive; app.py ignores them).
        "grad_a":      "#E08A5F",   # amber  — gradient start
        "grad_b":      "#F0C27B",   # gold   — gradient end
        "muted":       "#A89684",   # warm grey-brown for secondary text
        "rule":        "#3A322B",   # soft warm divider
        "danger":      "#E06C5F",   # warm red for denied/risky
        "success":     "#9FC089",   # muted sage for ok
    },
}


def _build_css(theme: str = "dark") -> str:
    _jtrace(f"[TRACE] core.cli.app._build_css: enter")
    t = _THEMES.get(theme, _THEMES["dark"])
    return f"""
    Screen {{
        background: {t['bg']};
        color: {t['text']};
    }}
    #header_title {{
        background: {t['header_bg']};
        color: {t['accent']};
        text-align: center;
        text-style: bold;
        height: 1;
        border-bottom: solid {t['border']};
    }}
    #status_bar {{
        background: {t['header_bg']};
        color: {t['text']};
        height: 1;
        border-top: solid {t['border']};
        padding: 0 1;
        text-align: right;
    }}
    AgentStrip {{
        background: {t['header_bg']};
        border-bottom: solid {t['border']};
        height: 3;
        padding: 0 1;
        content-align: center middle;
    }}
    RichLog {{
        height: 1fr;
        border: none;
        background: transparent;
    }}
    #input_container {{
        height: auto;
        border-top: solid {t['border']};
        background: {t['header_bg']};
        dock: bottom;
        layout: vertical;
    }}
    #dropdown_palette {{
        background: {t['dropdown_bg']};
        border: solid {t['accent']};
        height: 8;
        max-height: 8;
        display: none;
    }}
    #dropdown_palette.visible {{
        display: block;
    }}
    ListItem {{
        padding: 0 1;
    }}
    Input {{
        border: none;
        background: transparent;
        color: {t['text']};
    }}
    """


# ── Widgets ─────────────────────────────────────────────────────────────────

class AgentStrip(Static):
    """Horizontal status strip showing agents from AGENTS.md."""

    def on_mount(self) -> None:
        _jtrace(f"[TRACE] core.cli.app.AgentStrip.on_mount: enter")
        self.update_status()
        self.set_interval(2.0, self.update_status)

    def update_status(self) -> None:
        _jtrace(f"[TRACE] core.cli.app.AgentStrip.update_status: enter")
        agents = []
        try:
            path = os.path.join(os.getcwd(), "AGENTS.md")
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    for line in f:
                        if "|" in line and "Agent" not in line and "---" not in line:
                            parts = [p.strip() for p in line.split("|")[1:-1]]
                            if len(parts) >= 3:
                                agents.append(parts)
        except Exception:
            _jtrace(f"[TRACE] core.cli.app.AgentStrip.update_status: except Exception")
            pass

        if not agents:
            agents = [
                ["frontend", "gemini-3.1-pro", "IDLE", "---"],
                ["backend",  "claude-sonnet-4-6", "IDLE", "---"],
                ["qa",       "gpt-5.4", "IDLE", "---"],
            ]

        t = Text()
        _COLOR = {"idle": "dim white", "working": "yellow", "done": "green",
                  "passed": "bold green", "suspended": "red", "in_progress": "yellow"}
        for i, row in enumerate(agents):
            agent  = row[0]
            model  = row[1]
            status = row[2]
            step   = row[3] if len(row) > 3 else "---"
            color  = _COLOR.get(status.lower(), "white")
            t.append(f"{agent.upper()} ", style="bold cyan")
            t.append(f"({model})", style="dim")
            t.append(f": {status} ", style=color)
            if step and step != "---":
                t.append(f"· {step} ", style="italic dim")
            if i < len(agents) - 1:
                t.append("   |   ", style="dim")
        self.update(t)


class StatusBar(Static):
    """One-line footer: model, tool count, uptime, theme."""

    def __init__(self, app_ref, **kw):
        super().__init__(**kw)
        self._app_ref = app_ref
        self._start = datetime.now()

    def on_mount(self) -> None:
        _jtrace(f"[TRACE] core.cli.app.StatusBar.on_mount: enter")
        self.update_status()
        self.set_interval(5.0, self.update_status)

    def update_status(self) -> None:
        _jtrace(f"[TRACE] core.cli.app.StatusBar.update_status: enter")
        elapsed = int((datetime.now() - self._start).total_seconds())
        h, rem = divmod(elapsed, 3600)
        m, s   = divmod(rem, 60)
        uptime = f"{h:02d}:{m:02d}:{s:02d}"

        try:
            from tools.dispatcher import TOOL_DEFINITIONS
            tool_count = len(TOOL_DEFINITIONS)
        except Exception:
            _jtrace(f"[TRACE] core.cli.app.StatusBar.update_status: except Exception")
            tool_count = "?"

        model  = os.environ.get("JARVIS_PRIMARY_MODEL", "gemma4:31b-cloud")
        theme  = getattr(self._app_ref, "_active_theme", "dark")
        text   = Text()
        text.append(f" MODEL: ", style="dim")
        text.append(f"{model}", style="bold cyan")
        text.append(f"  TOOLS: {tool_count}", style="dim")
        text.append(f"  THEME: {theme}", style="dim")
        text.append(f"  UP: {uptime} ", style="dim")
        self.update(text)


class TextualStreamRedirector:
    """Redirects stdout/stderr into the TUI RichLog."""
    def __init__(self, write_func):
        self.write_func = write_func
    def write(self, data: str) -> None:
        if data:
            self.write_func(data)
    def flush(self) -> None:
        pass
    def reconfigure(self, **kwargs) -> None:
        pass


# ── Main application ─────────────────────────────────────────────────────────

class JarvisTuiApp(App):
    """Jarvis Operator Console — Textual TUI."""

    _active_theme: str = "warm"
    CSS = _build_css("warm")

    def compose(self) -> ComposeResult:
        _jtrace(f"[TRACE] core.cli.app.JarvisTuiApp.compose: enter")
        yield Label("JARVIS // OPERATOR CONSOLE", id="header_title")
        yield AgentStrip()
        yield RichLog(id="output_stream", highlight=True, markup=True)
        with Vertical(id="input_container"):
            yield ListView(id="dropdown_palette")
            yield Input(placeholder="Type a task or '/' for command palette…", id="cli_input")
        yield StatusBar(self, id="status_bar")

    def on_mount(self) -> None:
        _jtrace(f"[TRACE] core.cli.app.JarvisTuiApp.on_mount: enter")
        self.log_stream = self.query_one("#output_stream", RichLog)
        self.dropdown   = self.query_one("#dropdown_palette", ListView)
        self.cli_input  = self.query_one("#cli_input", Input)
        self.cli_input.focus()
        self._session_log: list[str] = []
        self._print_banner()

    # ── Banner ────────────────────────────────────────────────────────────────

    def _print_banner(self) -> None:
        self.log_stream.write(Text.from_markup(
            "[bold cyan]  JARVIS OPERATOR CONSOLE  [/]\n"
            "[dim]Type '/' to browse commands, or describe a task to run autonomously.[/]\n"
            f"[dim]Primary model: [bold]{os.environ.get('JARVIS_PRIMARY_MODEL','gemma4:31b-cloud')}[/]  "
            f"│  {len(SLASH_COMMANDS)} slash commands  │  type /help for guide[/]\n"
        ))

    # ── Command palette dropdown ──────────────────────────────────────────────

    def on_input_changed(self, event: Input.Changed) -> None:
        _jtrace(f"[TRACE] core.cli.app.JarvisTuiApp.on_input_changed: enter")
        val = event.value
        if val.startswith("/"):
            search  = val.lower()
            matches = [c for c in SLASH_COMMANDS if c[0].startswith(search)]
            if matches:
                self.dropdown.add_class("visible")
                self.dropdown.clear()
                for cmd, desc, autocomplete in matches:
                    li = ListItem(Label(f"{cmd:<14} {desc}"))
                    li.cmd_text = autocomplete
                    self.dropdown.append(li)
                self.dropdown.index = 0
            else:
                self.dropdown.remove_class("visible")
        else:
            self.dropdown.remove_class("visible")

    def on_key(self, event) -> None:
        _jtrace(f"[TRACE] core.cli.app.JarvisTuiApp.on_key: enter")
        if "visible" not in self.dropdown.classes:
            return
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
                item     = self.dropdown.children[self.dropdown.index]
                cmd_text = getattr(item, "cmd_text", "")
                self.cli_input.value = cmd_text + " "
                self.dropdown.remove_class("visible")

    # ── Input submission ──────────────────────────────────────────────────────

    def on_input_submitted(self, event: Input.Submitted) -> None:
        _jtrace(f"[TRACE] core.cli.app.JarvisTuiApp.on_input_submitted: enter")
        if "visible" in self.dropdown.classes:
            return
        text = event.value.strip()
        if not text:
            return
        self.cli_input.value = ""
        self._session_log.append(f"[{datetime.now():%H:%M:%S}] > {text}")

        # Determine mode & task
        mode = "auto"
        task = text
        for cmd, _, _ in SLASH_COMMANDS:
            if text.startswith(cmd):
                mode = cmd[1:]
                task = text[len(cmd):].strip()
                break

        # Route to inline or background handler
        if cmd_text := self._get_cmd_text(text):
            self._handle_inline(cmd_text, task)
        elif mode == "doctor":
            self.cli_input.disabled = True
            self.run_doctor()
        elif mode == "screen":
            self.cli_input.disabled = True
            self.run_screen()
        else:
            self.cli_input.disabled = True
            self.run_task_worker(mode, task)

    def _get_cmd_text(self, text: str) -> str | None:
        """Return the matched inline command or None."""
        _jtrace(f"[TRACE] core.cli.app.JarvisTuiApp._get_cmd_text: enter")
        for cmd in _INLINE_COMMANDS:
            if text.startswith(cmd):
                return cmd
        return None

    # ── Inline command handlers (synchronous, no subprocess) ─────────────────

    def _handle_inline(self, cmd: str, arg: str) -> None:
        if cmd == "/clear":
            self.log_stream.clear()
            self._session_log.clear()

        elif cmd == "/help":
            self._show_help()

        elif cmd == "/theme":
            self._switch_theme(arg.strip().lower() if arg else "")

        elif cmd == "/model":
            self._model_command(arg.strip())

        elif cmd == "/models":
            self._show_models(arg.strip())

        elif cmd == "/agents":
            self._show_agents()

        elif cmd == "/setmodel":
            self._set_agent_model_cmd(arg.strip())

        elif cmd == "/resetmodel":
            self._reset_agent_model_cmd(arg.strip())

        elif cmd == "/tools":
            self._show_tools()

        elif cmd == "/history":
            self._show_history()

        elif cmd == "/export":
            self._export_session(arg.strip())

        elif cmd == "/vocab":
            self._show_vocab()

    def _show_help(self) -> None:
        _jtrace(f"[TRACE] core.cli.app.JarvisTuiApp._show_help: enter")
        t = Table(title="Jarvis Commands", style="cyan", header_style="bold cyan",
                  show_lines=False, expand=False)
        t.add_column("Command",     style="bold", width=14)
        t.add_column("Description", style="dim",  width=52)
        for cmd, desc, _ in SLASH_COMMANDS:
            t.add_row(cmd, desc)
        self.log_stream.write(t)

    def _switch_theme(self, name: str) -> None:
        _jtrace(f"[TRACE] core.cli.app.JarvisTuiApp._switch_theme: enter")
        if name not in _THEMES:
            available = " | ".join(_THEMES.keys())
            self.log_stream.write(Text.from_markup(
                f"[yellow]Unknown theme '{name}'. Available: {available}[/]"
            ))
            return
        self._active_theme = name
        self.CSS = _build_css(name)
        self.refresh_css()
        self.log_stream.write(Text.from_markup(
            f"[bold cyan]Theme switched to '{name}'[/]"
        ))

    def _model_command(self, arg: str) -> None:
        _jtrace(f"[TRACE] core.cli.app.JarvisTuiApp._model_command: enter")
        current = os.environ.get("JARVIS_PRIMARY_MODEL", "gemma4:31b-cloud")
        if not arg:
            self.log_stream.write(Text.from_markup(
                f"[dim]Current model:[/] [bold cyan]{current}[/]\n"
                "[dim]Usage: /model <model-name>  (e.g. /model gpt-oss:120b)[/]"
            ))
            return
        os.environ["JARVIS_PRIMARY_MODEL"] = arg
        self.log_stream.write(Text.from_markup(
            f"[bold green]Model switched:[/] {current} → [bold cyan]{arg}[/]\n"
            "[dim](persists for this session; edit .env to make permanent)[/]"
        ))
        self.query_one("#status_bar", StatusBar).update_status()

    def _show_models(self, query: str = "") -> None:
        _jtrace(f"[TRACE] core.cli.app.JarvisTuiApp._show_models: enter")
        query = (query or "").strip()
        if query:
            try:
                from core.system.openrouter_catalog import list_models
                results = list_models(query, limit=40)
            except Exception as e:
                _jtrace(f"[TRACE] core.cli.app.JarvisTuiApp._show_models: except {str(e)[:80]}")
                self.log_stream.write(Text.from_markup(f"[red]catalog error: {e}[/]"))
                return
            if not results:
                self.log_stream.write(Text.from_markup(
                    f"[yellow]No OpenRouter models match '{query}'.[/] "
                    "[dim](needs OPENROUTER_API_KEY + network)[/]"))
                return
            t = Table(title=f"OpenRouter models matching '{query}'", style="cyan",
                      header_style="bold cyan", show_lines=False, expand=False)
            t.add_column("Model ID", style="bold", width=40)
            t.add_column("Ctx", style="dim", justify="right")
            t.add_column("$/Mtok in", style="dim", justify="right")
            t.add_column("$/Mtok out", style="dim", justify="right")
            for m in results:
                t.add_row(m.get("id", "?"), str(m.get("context") or "-"),
                          "-" if m.get("prompt_price") is None else str(m["prompt_price"]),
                          "-" if m.get("completion_price") is None else str(m["completion_price"]))
            self.log_stream.write(t)
            self.log_stream.write(Text.from_markup("[dim]Assign with: /setmodel <agent> <model-id>[/]"))
            return
        models = [
            ("minimaxai/minimax-m3",            "NVIDIA Build",   "minimaxai/minimax-m3"),
            ("gpt-oss:120b",                    "NVIDIA Build",   "openai/gpt-oss-120b"),
            ("moonshotai/kimi-k2.6",            "NVIDIA Build",   "moonshotai/kimi-k2.6"),
            ("nvidia/nemotron-3-nano-omni-30b",  "NVIDIA Build",   "omni — audio+image+text"),
            ("claude-sonnet-4-6",               "Anthropic API",  "claude-sonnet-4-6"),
            ("claude-opus-4-8",                 "Anthropic API",  "claude-opus-4-8"),
            ("gemini-2.5-pro",                  "Google AI",      "gemini-2.5-pro"),
            ("gemini-3.1-pro-preview",          "Google AI",      "gemini-3.1-pro-preview"),
            ("gemma4:31b-cloud",                "Ollama (cloud)", "gemma4:27b — default fallback"),
            ("gpt-5.4",                         "OpenAI API",     "gpt-5.4"),
        ]
        t = Table(title="Available Models", style="cyan", header_style="bold cyan",
                  show_lines=False, expand=False)
        t.add_column("Model ID",    style="bold",      width=36)
        t.add_column("Provider",    style="dim",       width=16)
        t.add_column("Notes",       style="italic dim",width=32)
        current = os.environ.get("JARVIS_PRIMARY_MODEL", "gemma4:31b-cloud")
        for mid, prov, note in models:
            marker = " ◀ active" if mid == current else ""
            t.add_row(mid + marker, prov, note)
        self.log_stream.write(t)
        self.log_stream.write(Text.from_markup(
            "[dim]Orchestrator: /model <id>  ·  Browse OpenRouter: /models <query>  ·  "
            "Per-agent: /agents · /setmodel <agent> <model>[/]"
        ))

    def _show_agents(self) -> None:
        _jtrace(f"[TRACE] core.cli.app.JarvisTuiApp._show_agents: enter")
        try:
            from agents.model_router import get_all_agent_models
            data = get_all_agent_models()
        except Exception as e:
            _jtrace(f"[TRACE] core.cli.app.JarvisTuiApp._show_agents: except {str(e)[:80]}")
            self.log_stream.write(Text.from_markup(f"[red]{e}[/]"))
            return
        t = Table(title="Agent Models", style="cyan", header_style="bold cyan",
                  show_lines=False, expand=False)
        t.add_column("Agent", style="bold", width=24)
        t.add_column("Model", style="cyan", width=40)
        t.add_column("Source", style="dim", width=8)
        for agent, info in data.items():
            t.add_row(agent, info.get("model", "?"), info.get("source", ""))
        self.log_stream.write(t)
        self.log_stream.write(Text.from_markup(
            "[dim]Change: /setmodel <agent> <model>  ·  Reset: /resetmodel <agent>  ·  "
            "Browse: /models <query>[/]"))

    def _set_agent_model_cmd(self, arg: str) -> None:
        _jtrace(f"[TRACE] core.cli.app.JarvisTuiApp._set_agent_model_cmd: enter")
        parts = (arg or "").split()
        if len(parts) < 2:
            self.log_stream.write(Text.from_markup(
                "[yellow]Usage:[/] /setmodel <agent> <model>  "
                "[dim](agents: frontend/backend/qa/orchestrator/verifier/iac or skill:<name>)[/]"))
            return
        target, model = parts[0], parts[1]
        try:
            from agents.model_router import set_agent_model
            stored = set_agent_model(target, model)
        except Exception as e:
            _jtrace(f"[TRACE] core.cli.app.JarvisTuiApp._set_agent_model_cmd: except {str(e)[:80]}")
            self.log_stream.write(Text.from_markup(f"[red]{e}[/]"))
            return
        self.log_stream.write(Text.from_markup(
            f"[bold green]{target}[/] → [bold cyan]{stored}[/] "
            "[dim](persisted to config/agent_models.json)[/]"))

    def _reset_agent_model_cmd(self, arg: str) -> None:
        _jtrace(f"[TRACE] core.cli.app.JarvisTuiApp._reset_agent_model_cmd: enter")
        target = (arg or "").strip()
        if not target:
            self.log_stream.write(Text.from_markup("[yellow]Usage:[/] /resetmodel <agent>"))
            return
        try:
            from agents.model_router import reset_agent_model
            removed = reset_agent_model(target)
        except Exception as e:
            _jtrace(f"[TRACE] core.cli.app.JarvisTuiApp._reset_agent_model_cmd: except {str(e)[:80]}")
            self.log_stream.write(Text.from_markup(f"[red]{e}[/]"))
            return
        self.log_stream.write(Text.from_markup(
            f"[green]reset {target}[/] [dim](back to default)[/]" if removed
            else f"[dim]no override set for {target}[/]"))

    def _show_tools(self) -> None:
        try:
            sys.path.insert(0, os.getcwd())
            from tools.dispatcher import TOOL_DEFINITIONS
            t = Table(title=f"Registered Tools ({len(TOOL_DEFINITIONS)})",
                      style="cyan", header_style="bold cyan",
                      show_lines=False, expand=False)
            t.add_column("#",    style="dim",  width=3)
            t.add_column("Tool", style="bold", width=28)
            t.add_column("Description (truncated)", style="dim", width=52)
            for i, tool in enumerate(TOOL_DEFINITIONS, 1):
                fn   = tool["function"]
                desc = fn.get("description", "")[:70]
                t.add_row(str(i), fn["name"], desc)
            self.log_stream.write(t)
        except Exception as e:
            _jtrace(f"[TRACE] core.cli.app.JarvisTuiApp._show_tools: except {str(e)[:80]}")
            self.log_stream.write(Text.from_markup(f"[red]Error loading tools: {e}[/]"))

    def _show_history(self) -> None:
        _jtrace(f"[TRACE] core.cli.app.JarvisTuiApp._show_history: enter")
        log_path = os.path.join(os.getcwd(), "@AutomationLog.txt")
        if os.path.exists(log_path):
            try:
                with open(log_path, "r", encoding="utf-8", errors="replace") as f:
                    lines = f.readlines()[-40:]
                self.log_stream.write(Text.from_markup("[bold cyan]── Recent Automation Log ──[/]"))
                for line in lines:
                    self.log_stream.write(Text.from_ansi(line.rstrip()))
                return
            except Exception as e:
                _jtrace(f"[TRACE] core.cli.app.JarvisTuiApp._show_history: except {str(e)[:80]}")
                self.log_stream.write(Text.from_markup(f"[red]Error reading log: {e}[/]"))
        # Fall back to in-session log
        if self._session_log:
            self.log_stream.write(Text.from_markup("[bold cyan]── Session History ──[/]"))
            for entry in self._session_log[-30:]:
                self.log_stream.write(Text(entry, style="dim"))
        else:
            self.log_stream.write(Text.from_markup("[dim]No history yet.[/]"))

    def _export_session(self, filename: str) -> None:
        _jtrace(f"[TRACE] core.cli.app.JarvisTuiApp._export_session: enter")
        if not filename:
            filename = f"jarvis_session_{datetime.now():%Y%m%d_%H%M%S}.md"
        if not filename.endswith(".md"):
            filename += ".md"
        out_path = os.path.join(os.getcwd(), "scratch", filename)
        try:
            os.makedirs(os.path.dirname(out_path), exist_ok=True)
            with open(out_path, "w", encoding="utf-8") as f:
                f.write(f"# Jarvis Session Export\n\n")
                f.write(f"**Date:** {datetime.now():%Y-%m-%d %H:%M:%S}\n")
                f.write(f"**Model:** {os.environ.get('JARVIS_PRIMARY_MODEL','?')}\n\n")
                f.write("## Command History\n\n")
                for entry in self._session_log:
                    f.write(f"- {entry}\n")
            self.log_stream.write(Text.from_markup(
                f"[bold green]Session exported →[/] [dim]{out_path}[/]"
            ))
        except Exception as e:
            _jtrace(f"[TRACE] core.cli.app.JarvisTuiApp._export_session: except {str(e)[:80]}")
            self.log_stream.write(Text.from_markup(f"[red]Export failed: {e}[/]"))

    def _show_vocab(self) -> None:
        try:
            sys.path.insert(0, os.getcwd())
            from core.system.visual_vocab import VisualVocabulary
            vocab    = VisualVocabulary()
            cheatsheet = vocab.get_context_addition()
            self.log_stream.write(Text.from_markup("[bold cyan]── Visual Vocabulary ──[/]"))
            # Show the cheatsheet in chunks to avoid RichLog overflow
            for chunk in cheatsheet.split("\n\n")[:20]:
                if chunk.strip():
                    self.log_stream.write(Text(chunk))
        except Exception as e:
            _jtrace(f"[TRACE] core.cli.app.JarvisTuiApp._show_vocab: except {str(e)[:80]}")
            self.log_stream.write(Text.from_markup(
                f"[yellow]Visual vocab not loaded: {e}[/]\n"
                "[dim]Run /jarvis desktop task first to initialise vocab.[/]"
            ))

    # ── Background worker: generic Jarvis task ────────────────────────────────

    def enable_input(self) -> None:
        _jtrace(f"[TRACE] core.cli.app.JarvisTuiApp.enable_input: enter")
        self.cli_input.disabled = False
        self.cli_input.focus()

    @work(thread=True)
    def run_task_worker(self, mode: str, task: str) -> None:
        _jtrace(f"[TRACE] core.cli.app.JarvisTuiApp.run_task_worker: enter")
        self.call_from_thread(self.log_stream.write, Text.from_markup(
            f"\n[bold cyan]Jarvis [{mode}][/] [dim]{task[:80]}[/]"
        ))

        old_out, old_err = sys.stdout, sys.stderr

        def _write(data: str) -> None:
            _jtrace(f"[TRACE] core.cli.app.JarvisTuiApp.run_task_worker._write: enter")
            self.call_from_thread(self.log_stream.write, Text.from_ansi(data))
            self._session_log.append(data.rstrip())

        sys.stdout = TextualStreamRedirector(_write)
        sys.stderr = TextualStreamRedirector(_write)

        try:
            spec = importlib.util.spec_from_file_location("jarvis_cli", "jarvis-cli.py")
            jarvis_cli = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(jarvis_cli)

            from core.hermes.hermes_cli_runner import EnvironmentHandshake, SkillsEngine, call_llm
            from tools.dispatcher import TOOL_DEFINITIONS, dispatch

            prompt_content  = jarvis_cli.build_prompt(mode, task)
            handshake       = EnvironmentHandshake()
            from core.jarvis_prompt import base_prompt
            from datetime import datetime as _dt
            _out_dir = os.environ.get("JARVIS_OUTPUT_ROOT") or os.getcwd()
            system_instruction = (
                base_prompt(date=_dt.now().strftime("%A, %B %d, %Y"), output_dir=_out_dir)
                + f"\n\n{handshake.get_system_prompt_addition()}"
            )
            skills_engine   = SkillsEngine()
            skills_addition = skills_engine.get_skills_prompt_addition(prompt_content)

            if not hasattr(self, "chat_history"):
                self.chat_history = []

            self.chat_history.append({"role": "user", "content": prompt_content})
            messages = [
                {"role": "system", "content": system_instruction + skills_addition}
            ] + self.chat_history

            model = os.environ.get("JARVIS_PRIMARY_MODEL", jarvis_cli.DEFAULT_MODEL)

            while True:
                msg = call_llm(messages=messages, model=model, tools=TOOL_DEFINITIONS)
                messages.append(msg)
                self.chat_history.append(msg)

                if not msg.get("tool_calls"):
                    content = msg.get("content", "")
                    clean   = content.encode("utf-8", errors="replace").decode("utf-8")
                    print(f"\n{clean}\n")
                    break

                for call in msg["tool_calls"]:
                    fn      = call["function"]["name"]
                    fn_args = call["function"]["arguments"]
                    print(f"  [Tool] {fn}({fn_args[:80]})")
                    try:
                        result = dispatch(fn, fn_args)
                    except Exception as e:
                        _jtrace(f"[TRACE] core.cli.app.JarvisTuiApp.run_task_worker: except {str(e)[:80]}")
                        result = f"ERROR: {e}"
                    print(f"  [Result] {str(result)[:200]}")
                    tool_msg = {"role": "tool", "content": str(result)}
                    messages.append(tool_msg)
                    self.chat_history.append(tool_msg)

                print("  [Hermes] Continuing…")

            print("\n✅ Done")

        except Exception as e:
            _jtrace(f"[TRACE] core.cli.app.JarvisTuiApp.run_task_worker: except {str(e)[:80]}")
            print(f"\n❌ {e}")
        finally:
            sys.stdout = old_out
            sys.stderr = old_err
            self.call_from_thread(self.enable_input)

    @work(thread=True)
    def run_doctor(self) -> None:
        _jtrace(f"[TRACE] core.cli.app.JarvisTuiApp.run_doctor: enter")
        self.call_from_thread(self.log_stream.write,
                              Text.from_markup("\n[bold cyan]Running health check…[/]"))
        old_out, old_err = sys.stdout, sys.stderr

        def _write(data: str) -> None:
            self.call_from_thread(self.log_stream.write, Text.from_ansi(data))

        sys.stdout = TextualStreamRedirector(_write)
        sys.stderr = TextualStreamRedirector(_write)
        try:
            spec = importlib.util.spec_from_file_location("jarvis_cli", "jarvis-cli.py")
            cli  = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(cli)
            cli.doctor()
        except Exception as e:
            _jtrace(f"[TRACE] core.cli.app.JarvisTuiApp.run_doctor: except {str(e)[:80]}")
            print(f"Error: {e}")
        finally:
            sys.stdout = old_out
            sys.stderr = old_err
            self.call_from_thread(self.enable_input)

    @work(thread=True)
    def run_screen(self) -> None:
        _jtrace(f"[TRACE] core.cli.app.JarvisTuiApp.run_screen: enter")
        self.call_from_thread(self.log_stream.write,
                              Text.from_markup("\n[bold cyan]Fetching screen context…[/]"))
        old_out, old_err = sys.stdout, sys.stderr

        def _write(data: str) -> None:
            self.call_from_thread(self.log_stream.write, Text.from_ansi(data))

        sys.stdout = TextualStreamRedirector(_write)
        sys.stderr = TextualStreamRedirector(_write)
        try:
            spec = importlib.util.spec_from_file_location("jarvis_cli", "jarvis-cli.py")
            cli  = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(cli)
            cli.run_screen_dashboard()
        except Exception as e:
            _jtrace(f"[TRACE] core.cli.app.JarvisTuiApp.run_screen: except {str(e)[:80]}")
            print(f"Error: {e}")
        finally:
            sys.stdout = old_out
            sys.stderr = old_err
            self.call_from_thread(self.enable_input)

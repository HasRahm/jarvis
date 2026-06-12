"""
Jarvis inline REPL — a streaming, scrollback-native console in the style of
Claude Code / Gemini CLI.

Unlike the full-screen Textual dashboard (core/cli/app.py, launched via --tui),
this prints into the normal terminal so output can be scrolled, selected and
copied. It streams the model's response token-by-token with live markdown
rendering, shows tool calls as cards, and offers inline slash autocomplete,
`@file` references, and `!shell` passthrough.
"""
import os
import sys
import importlib.util
import subprocess

from rich.console import Console, Group
from rich.markdown import Markdown
from rich.panel import Panel
from rich.text import Text
from rich.table import Table
from rich.live import Live
from rich.rule import Rule

from prompt_toolkit import PromptSession
from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.history import FileHistory
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.styles import Style as PTStyle
from prompt_toolkit.key_binding import KeyBindings

from core.cli.app import SLASH_COMMANDS, _THEMES

# Commands that run a Jarvis agent turn rather than an inline action
_AGENT_MODES = {"research", "diagnose", "browse", "desktop", "excel", "shell", "auto", "screen"}
# Commands handled locally inside the REPL (no agent loop)
_INLINE = {"help", "model", "models", "tools", "clear", "theme", "vocab",
           "history", "export", "exit", "quit", "doctor", "agentview", "cursor"}

_HISTORY_FILE = os.path.join(os.path.expanduser("~"), ".jarvis_repl_history")


# ── Autocompletion ───────────────────────────────────────────────────────────

class JarvisCompleter(Completer):
    """Inline completion for /slash commands and @file references."""

    def get_completions(self, document, complete_event):
        text = document.text_before_cursor

        # @file path completion (anywhere in the line)
        if "@" in text and not text.lstrip().startswith("/"):
            at  = text.rfind("@")
            frag = text[at + 1:]
            if " " not in frag:
                yield from self._file_completions(frag)
                return

        # /slash command completion (only at line start)
        if text.startswith("/") and " " not in text:
            for cmd, desc, _ in SLASH_COMMANDS:
                if cmd.startswith(text):
                    yield Completion(
                        cmd, start_position=-len(text),
                        display=cmd, display_meta=desc,
                    )

    def _file_completions(self, frag):
        base_dir = os.path.dirname(frag) or "."
        prefix   = os.path.basename(frag)
        try:
            for name in sorted(os.listdir(base_dir)):
                if name.startswith(prefix):
                    full = name if base_dir == "." else os.path.join(base_dir, name)
                    if os.path.isdir(full):
                        full += os.sep
                    yield Completion(full, start_position=-len(frag),
                                     display=name + ("/" if os.path.isdir(full.rstrip(os.sep)) else ""))
        except Exception:
            return


# ── The REPL ─────────────────────────────────────────────────────────────────

class JarvisRepl:
    def __init__(self):
        # Force UTF-8 on the streams FIRST. On a legacy Windows console the
        # encoding is cp1252, and rich raises UnicodeEncodeError on glyphs like
        # ❯ ✗ ◀ … — which would otherwise crash the REPL (even inside the error
        # handler). reconfigure() mutates the existing stream in place, so the
        # references we pin below stay valid and now emit UTF-8 safely.
        for stream in (sys.stdout, sys.stderr):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass

        # Pin the console to the real stdout captured now, so rendering keeps
        # working even while we temporarily redirect sys.stdout to a sink during
        # an agent turn (to swallow the adapter's raw token prints).
        self.console = Console(file=sys.stdout)
        self._real_stdout = sys.stdout
        self.chat_history: list[dict] = []
        self._jarvis_cli = None
        self._theme = "dark"
        self.session = None   # built lazily in run() — needs a real console/TTY

    def _build_session(self) -> PromptSession:
        bindings = KeyBindings()

        @bindings.add("c-l")
        def _(event):
            self.console.clear()

        return PromptSession(
            history=FileHistory(_HISTORY_FILE),
            auto_suggest=AutoSuggestFromHistory(),
            completer=JarvisCompleter(),
            complete_while_typing=True,
            key_bindings=bindings,
            bottom_toolbar=self._bottom_toolbar,
            style=PTStyle.from_dict({
                "bottom-toolbar": "#5EEAD4 bg:#0a0c0f",
                "prompt": "#5EEAD4 bold",
            }),
        )

    # ── chrome ────────────────────────────────────────────────────────────────

    def _bottom_toolbar(self):
        model = os.environ.get("JARVIS_PRIMARY_MODEL", "gemma4:31b-cloud")
        cwd   = os.path.basename(os.getcwd())
        turns = len([m for m in self.chat_history if m.get("role") == "user"])
        return HTML(f" <b>jarvis</b> · {model} · ~/{cwd} · {turns} turns · /help for commands ")

    def _banner(self):
        self.console.print()
        self.console.print(Text("  JARVIS", style="bold cyan"), Text("// inline console", style="dim"))
        model = os.environ.get("JARVIS_PRIMARY_MODEL", "gemma4:31b-cloud")
        self.console.print(
            Text(f"  {model}", style="dim cyan") +
            Text("  ·  ", style="dim") +
            Text(f"{len(SLASH_COMMANDS)} slash commands", style="dim") +
            Text("  ·  ", style="dim") +
            Text("@file  !shell  /help  /exit", style="dim"),
        )
        self.console.print(Rule(style="grey30"))

    def _lazy_jarvis_cli(self):
        if self._jarvis_cli is None:
            spec = importlib.util.spec_from_file_location("jarvis_cli", "jarvis-cli.py")
            mod  = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            self._jarvis_cli = mod
        return self._jarvis_cli

    # ── main loop ───────────────────────────────────────────────────────────────

    def run(self):
        if self.session is None:
            self.session = self._build_session()
        self._banner()
        interrupted_once = False
        while True:
            # ── read a line ──────────────────────────────────────────────────
            try:
                raw = self.session.prompt([("class:prompt", "❯ ")])
            except KeyboardInterrupt:
                # First Ctrl-C at the prompt warns; a second in a row exits.
                if interrupted_once:
                    self.console.print("[dim]bye.[/]")
                    break
                interrupted_once = True
                self.console.print("[dim](press Ctrl-C again to exit, or keep typing)[/]")
                continue
            except EOFError:
                # Ctrl-D leaves.
                self.console.print("[dim]bye.[/]")
                break

            interrupted_once = False
            text = raw.strip()
            if not text:
                continue

            # ── dispatch, fully insulated ────────────────────────────────────
            # Nothing a single line does — a tool crash, a model error, a bad
            # command — should ever drop the user out of the REPL.
            try:
                if self._dispatch_line(text) == "EXIT":
                    self.console.print("[dim]bye.[/]")
                    break
            except KeyboardInterrupt:
                # Ctrl-C during a running turn cancels it and returns to prompt.
                self.console.print("\n[yellow]⊗ cancelled — back to prompt[/]")
            except Exception as e:
                # Any other failure is shown but never fatal.
                self._print_error(e)
            finally:
                # Defensive: a turn redirects sys.stdout; make sure it's restored
                # even if something unwound abnormally.
                if sys.stdout is not self._real_stdout:
                    sys.stdout = self._real_stdout

    def _dispatch_line(self, text: str):
        """Handle one input line. Returns 'EXIT' to leave the REPL, else None."""
        # !shell passthrough
        if text.startswith("!"):
            self._run_shell(text[1:].strip())
            return None

        # /slash command
        if text.startswith("/"):
            cmd = text.split()[0][1:].lower()
            arg = text[len(cmd) + 1:].strip()
            if cmd in ("exit", "quit"):
                return "EXIT"
            if cmd in _INLINE:
                self._handle_inline(cmd, arg)
                return None
            if cmd in _AGENT_MODES:
                self._agent_turn(cmd, arg)
                return None
            self.console.print(f"[yellow]Unknown command:[/] /{cmd}  [dim](try /help)[/]")
            return None

        # Plain text → auto-mode agent turn
        self._agent_turn("auto", text)
        return None

    def _print_error(self, e: Exception):
        """Show an error without dumping a raw traceback (unless JARVIS_DEBUG=1).

        This is the REPL's safety net, so it must never raise — if rich itself
        fails (e.g. a console encoding edge case) we fall back to a plain write.
        """
        try:
            self.console.print(f"\n[red]x {type(e).__name__}:[/] {e}")
            if os.environ.get("JARVIS_DEBUG") == "1":
                import traceback
                self.console.print(Text(traceback.format_exc(), style="dim red"))
            else:
                self.console.print("[dim]  (set JARVIS_DEBUG=1 for the full traceback)[/]")
        except Exception:
            try:
                self._real_stdout.write(f"\nError: {type(e).__name__}: {e}\n")
                self._real_stdout.flush()
            except Exception:
                pass

    # ── shell passthrough ───────────────────────────────────────────────────────

    def _run_shell(self, cmd: str):
        if not cmd:
            return
        self.console.print(Panel(cmd, title="shell", title_align="left",
                                 border_style="grey50", padding=(0, 1)))
        try:
            proc = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=120)
            out = (proc.stdout or "") + (proc.stderr or "")
            self.console.print(Text(out.rstrip() or "(no output)", style="dim"))
        except Exception as e:
            self.console.print(f"[red]shell error: {e}[/]")

    # ── @file expansion ─────────────────────────────────────────────────────────

    def _expand_file_refs(self, text: str) -> str:
        """Replace @path tokens with the file's contents appended as context."""
        import re
        refs = re.findall(r"@(\S+)", text)
        if not refs:
            return text
        attached = []
        for ref in refs:
            path = ref.rstrip(".,;:")
            if os.path.isfile(path):
                try:
                    with open(path, "r", encoding="utf-8", errors="replace") as f:
                        content = f.read()[:20000]
                    attached.append(f"\n\n--- FILE: {path} ---\n{content}\n--- END {path} ---")
                    self.console.print(f"[dim]  ⛓ attached {path} ({len(content)} chars)[/]")
                except Exception as e:
                    self.console.print(f"[yellow]  could not read {path}: {e}[/]")
        return text + "".join(attached)

    # ── agent turn (streaming) ───────────────────────────────────────────────────

    def _agent_turn(self, mode: str, task: str):
        from core.system.llm_adapter import set_stream_hook
        from core.hermes.hermes_cli_runner import EnvironmentHandshake, SkillsEngine, call_llm
        from tools.dispatcher import TOOL_DEFINITIONS, dispatch

        cli  = self._lazy_jarvis_cli()
        task = self._expand_file_refs(task)

        prompt_content = cli.build_prompt(mode, task)
        handshake = EnvironmentHandshake()
        system_instruction = (
            "You are Jarvis, a powerful AI assistant with full access to this computer via tools. "
            "Use your tools to accomplish the user's tasks. "
            "Before answering, ALWAYS call brain_query with the user's intent to check past context.\n\n"
            "For complex build tasks involving multiple components, use delegate_task.\n"
            f"{handshake.get_system_prompt_addition()}"
        )
        skills = SkillsEngine().get_skills_prompt_addition(prompt_content)

        self.chat_history.append({"role": "user", "content": prompt_content})
        messages = [{"role": "system", "content": system_instruction + skills}] + self.chat_history
        model = os.environ.get("JARVIS_PRIMARY_MODEL", cli.DEFAULT_MODEL)

        real_stdout = self._real_stdout

        class _Sink:
            def write(self, *a, **k): pass
            def flush(self): pass

        while True:
            buf = {"content": "", "reasoning": ""}

            def render():
                parts = []
                if buf["reasoning"] and not buf["content"]:
                    parts.append(Text(buf["reasoning"], style="dim italic"))
                if buf["content"]:
                    parts.append(Markdown(buf["content"]))
                if not parts:
                    parts.append(Text("thinking…", style="dim"))
                return Group(*parts)

            try:
                real_stderr = sys.stderr
                with Live(render(), console=self.console, refresh_per_second=12,
                          vertical_overflow="visible") as live:
                    def hook(t, kind):
                        buf[kind] = buf.get(kind, "") + t
                        live.update(render())
                    set_stream_hook(hook)
                    # Swallow the adapter's raw prints on BOTH streams — its
                    # fallback-chain tracebacks go to stderr and would otherwise
                    # bleed through and corrupt the live render region.
                    sys.stdout = _Sink()
                    sys.stderr = _Sink()
                    try:
                        msg = call_llm(messages=messages, model=model, tools=TOOL_DEFINITIONS)
                    finally:
                        sys.stdout = real_stdout
                        sys.stderr = real_stderr
                        set_stream_hook(None)
                        if buf["content"] or buf["reasoning"]:
                            live.update(render())   # final frame = full markdown
                        else:
                            live.update(Text(""))   # tool-only turn: clear 'thinking…'
            except Exception as e:
                sys.stdout = real_stdout
                sys.stderr = real_stderr
                set_stream_hook(None)
                self._print_error(e)
                return

            messages.append(msg)
            self.chat_history.append(msg)

            if not msg.get("tool_calls"):
                self.console.print()   # spacing after the answer
                return

            # Render tool calls as cards, dispatch, feed results back
            for call in msg["tool_calls"]:
                fn   = call["function"]["name"]
                args = call["function"]["arguments"]
                args_str = args if isinstance(args, str) else _short(args)
                self.console.print(Panel(
                    Text(f"{fn}", style="bold yellow") + Text(f"  {args_str}", style="dim"),
                    title="tool", title_align="left", border_style="yellow", padding=(0, 1),
                ))
                result = self._dispatch_with_timeout(dispatch, fn, args)
                preview = str(result)[:400]
                self.console.print(Text(f"  ⮑ {preview}", style="dim"))
                self.chat_history.append({"role": "tool", "content": str(result)})
                messages.append({"role": "tool", "content": str(result)})

    def _dispatch_with_timeout(self, dispatch_fn, fn: str, args):
        """Run a tool in a worker thread with a hard timeout.

        A tool that blocks forever (window activation under Windows' foreground
        lock, an MCP connect, a stuck subprocess…) must never freeze the REPL.
        The worker is a daemon thread: on timeout we abandon it and move on.
        Ctrl-C while waiting raises KeyboardInterrupt from join(), which the
        run() loop turns into a turn-cancel.
        """
        import threading
        timeout = float(os.environ.get("JARVIS_TOOL_TIMEOUT", "120"))
        box = {}

        def target():
            try:
                box["result"] = dispatch_fn(fn, args)
            except Exception as e:
                box["error"] = e

        worker = threading.Thread(target=target, daemon=True, name=f"tool-{fn}")
        worker.start()
        # Join in small slices, not one long join: on Windows a blocking
        # lock acquire suppresses Ctrl-C delivery, so join(120) would make
        # the REPL appear dead to Ctrl-C for the full timeout. Between short
        # joins, KeyboardInterrupt is delivered and propagates to run()'s
        # cancel handler within ~200ms.
        import time as _time
        deadline = _time.monotonic() + timeout
        while worker.is_alive() and _time.monotonic() < deadline:
            worker.join(0.2)

        if worker.is_alive():
            return (f"ERROR: tool '{fn}' timed out after {timeout:.0f}s and was "
                    f"abandoned. (Tune with JARVIS_TOOL_TIMEOUT.)")
        if "error" in box:
            return f"ERROR: {box['error']}"
        return box.get("result", "")

    # ── inline command handlers ──────────────────────────────────────────────────

    def _handle_inline(self, cmd: str, arg: str):
        getattr(self, f"_cmd_{cmd}", self._cmd_unknown)(arg)

    def _cmd_unknown(self, arg):
        self.console.print("[yellow]not implemented[/]")

    def _cmd_clear(self, arg):
        self.console.clear()

    def _cmd_help(self, arg):
        t = Table(title="Jarvis Commands", header_style="bold cyan", show_lines=False)
        t.add_column("Command", style="bold cyan", width=14)
        t.add_column("Description", style="white")
        for c, d, _ in SLASH_COMMANDS:
            t.add_row(c, d)
        self.console.print(t)
        self.console.print(
            "[dim]Also: [bold]@file[/] to attach a file · [bold]!cmd[/] to run shell · "
            "[bold]Ctrl-L[/] clear · [bold]Ctrl-C[/] cancel turn (×2 to exit) · [bold]Ctrl-D[/] exit[/]")

    def _cmd_model(self, arg):
        cur = os.environ.get("JARVIS_PRIMARY_MODEL", "gemma4:31b-cloud")
        if not arg:
            self.console.print(f"current model: [bold cyan]{cur}[/]\n[dim]usage: /model <name>[/]")
            return
        os.environ["JARVIS_PRIMARY_MODEL"] = arg
        self.console.print(f"[green]model:[/] {cur} → [bold cyan]{arg}[/]  [dim](session only)[/]")

    def _cmd_models(self, arg):
        rows = [
            ("gpt-oss:120b", "NVIDIA Build"), ("moonshotai/kimi-k2.6", "NVIDIA Build"),
            ("nvidia/nemotron-3-nano-omni-30b", "NVIDIA (omni)"),
            ("claude-sonnet-4-6", "Anthropic"), ("claude-opus-4-8", "Anthropic"),
            ("gemini-2.5-pro", "Google"), ("gemini-3.1-pro-preview", "Google"),
            ("gemma4:31b-cloud", "Ollama (cloud)"), ("gpt-5.4", "OpenAI"),
        ]
        cur = os.environ.get("JARVIS_PRIMARY_MODEL", "gemma4:31b-cloud")
        t = Table(title="Models", header_style="bold cyan")
        t.add_column("Model", style="bold")
        t.add_column("Provider", style="dim")
        for mid, prov in rows:
            t.add_row(mid + ("  ◀" if mid == cur else ""), prov)
        self.console.print(t)

    def _cmd_tools(self, arg):
        try:
            from tools.dispatcher import TOOL_DEFINITIONS
            t = Table(title=f"Tools ({len(TOOL_DEFINITIONS)})", header_style="bold cyan")
            t.add_column("#", style="dim", width=3)
            t.add_column("Tool", style="bold")
            t.add_column("Description", style="dim")
            for i, tool in enumerate(TOOL_DEFINITIONS, 1):
                fn = tool["function"]
                t.add_row(str(i), fn["name"], fn.get("description", "")[:64])
            self.console.print(t)
        except Exception as e:
            self.console.print(f"[red]{e}[/]")

    def _cmd_theme(self, arg):
        name = arg.strip().lower()
        if name not in _THEMES:
            self.console.print(f"[yellow]themes:[/] {' | '.join(_THEMES)}")
            return
        self._theme = name
        self.console.print(f"[cyan]theme → {name}[/] [dim](affects --tui; REPL uses your terminal palette)[/]")

    def _cmd_vocab(self, arg):
        try:
            from core.system.visual_vocab import VisualVocabulary
            cs = VisualVocabulary().get_context_addition()
            self.console.print(Markdown(cs[:4000]))
        except Exception as e:
            self.console.print(f"[yellow]vocab unavailable: {e}[/]")

    def _cmd_history(self, arg):
        users = [m["content"] for m in self.chat_history if m.get("role") == "user"]
        if not users:
            self.console.print("[dim]no history yet[/]")
            return
        for i, u in enumerate(users[-20:], 1):
            self.console.print(f"[dim]{i:>2}[/] {u.splitlines()[0][:100]}")

    def _cmd_export(self, arg):
        from datetime import datetime
        fn = arg.strip() or f"jarvis_session_{datetime.now():%Y%m%d_%H%M%S}.md"
        if not fn.endswith(".md"):
            fn += ".md"
        out = os.path.join(os.getcwd(), "scratch", fn)
        try:
            os.makedirs(os.path.dirname(out), exist_ok=True)
            with open(out, "w", encoding="utf-8") as f:
                f.write(f"# Jarvis Session — {datetime.now():%Y-%m-%d %H:%M}\n\n")
                for m in self.chat_history:
                    role = m.get("role", "?")
                    content = m.get("content", "")
                    if content:
                        f.write(f"**{role}:** {content}\n\n")
            self.console.print(f"[green]exported →[/] [dim]{out}[/]")
        except Exception as e:
            self.console.print(f"[red]export failed: {e}[/]")

    def _cmd_doctor(self, arg):
        try:
            self._lazy_jarvis_cli().doctor()
        except Exception as e:
            self.console.print(f"[red]{e}[/]")

    def _cmd_agentview(self, arg):
        """Annotated 'what the agent sees' screenshots: on | off | open | status."""
        try:
            from tools.agent_view import agent_view_tool
            sub = (arg or "status").strip().lower()
            if sub == "open":
                self.console.print(agent_view_tool("latest", open_file=True))
            elif sub in ("on", "off", "status", "latest"):
                self.console.print(agent_view_tool(sub))
            else:
                self.console.print("[dim]usage: /agentview on | off | open | status[/]")
        except Exception as e:
            self.console.print(f"[red]{e}[/]")

    def _cmd_cursor(self, arg):
        """Visible agent-cursor overlay ring: on | off | status."""
        try:
            from tools.agent_cursor import agent_cursor_tool
            sub = (arg or "status").strip().lower()
            if sub in ("on", "off", "status"):
                self.console.print(agent_cursor_tool(sub))
            else:
                self.console.print("[dim]usage: /cursor on | off | status[/]")
        except Exception as e:
            self.console.print(f"[red]{e}[/]")


def _short(d) -> str:
    s = str(d)
    return s if len(s) <= 80 else s[:77] + "…"


def main():
    JarvisRepl().run()


if __name__ == "__main__":
    main()

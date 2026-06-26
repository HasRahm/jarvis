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
from core.trace import trace as _jtrace
import importlib.util
import subprocess

from rich.console import Console, Group
from rich.markdown import Markdown
from rich.panel import Panel
from rich.text import Text
from rich.table import Table
from rich.live import Live
from rich.rule import Rule
from rich.spinner import Spinner
from rich import box as _box

from prompt_toolkit import PromptSession
from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.history import FileHistory
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.styles import Style as PTStyle
from prompt_toolkit.key_binding import KeyBindings

from core.cli.app import SLASH_COMMANDS, _THEMES
from core import session_store
from core.orchestrator.intent_router import classify as _classify_intent

# Commands that run a Jarvis agent turn rather than an inline action
_AGENT_MODES = {"research", "diagnose", "browse", "desktop", "excel", "shell", "auto", "screen"}
# Commands handled locally inside the REPL (no agent loop)
_INLINE = {"help", "model", "models", "tools", "clear", "theme", "vocab",
           "history", "export", "exit", "quit", "doctor", "agentview", "cursor",
           "remote", "save", "load", "context", "build", "code",
           "agents", "setmodel", "resetmodel", "forget", "new"}

_HISTORY_FILE = os.path.join(os.path.expanduser("~"), ".jarvis_repl_history")

# Phase 40: subtle animation can be disabled (CI, dumb terminals, preference).
_ANIM = os.environ.get("JARVIS_NO_ANIM") != "1"


def _warm() -> dict:
    """The active warm-elegant palette (falls back to the 'warm' theme)."""
    theme = os.environ.get("JARVIS_THEME", "warm")
    return _THEMES.get(theme, _THEMES["warm"])


def _hex_to_rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _gradient_text(s: str, start_hex: str, end_hex: str, *, bold: bool = False) -> Text:
    """Build a rich Text whose characters fade from start_hex to end_hex (left→right).

    Spaces are emitted uncoloured so letter-spacing stays clean. Never raises — on any
    error it returns a plain styled Text."""
    try:
        sr, sg, sb = _hex_to_rgb(start_hex)
        er, eg, eb = _hex_to_rgb(end_hex)
        out = Text()
        glyphs = [c for c in s]
        n = max(1, len([c for c in glyphs if c != " "]) - 1)
        i = 0
        for c in glyphs:
            if c == " ":
                out.append(" ")
                continue
            t = i / n
            r = round(sr + (er - sr) * t)
            g = round(sg + (eg - sg) * t)
            b = round(sb + (eb - sb) * t)
            style = f"#{r:02x}{g:02x}{b:02x}"
            if bold:
                style = "bold " + style
            out.append(c, style=style)
            i += 1
        return out
    except Exception:
        return Text(s, style=("bold " if bold else "") + start_hex)


def _find_project_context() -> tuple[str, str] | tuple[None, None]:
    """Walk up from cwd looking for JARVIS.md (like CLAUDE.md / GEMINI.md).

    Returns (file_path, content) or (None, None) if not found.
    """
    current = os.path.abspath(os.getcwd())
    while True:
        candidate = os.path.join(current, "JARVIS.md")
        if os.path.isfile(candidate):
            try:
                with open(candidate, "r", encoding="utf-8", errors="replace") as f:
                    return candidate, f.read()
            except Exception:
                return None, None
        parent = os.path.dirname(current)
        if parent == current:
            break
        current = parent
    return None, None


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
        self._theme = os.environ.get("JARVIS_THEME", "warm")
        self.session = None   # built lazily in run() — needs a real console/TTY
        # Cluster 1: generated files (incl. /build agents) go to the REPL's launch dir, not the
        # install dir. Pin it so get_workspace_path / AGENTS.md root there for this session.
        os.environ.setdefault("JARVIS_OUTPUT_ROOT", os.getcwd())
        # Project context file (JARVIS.md, walked up from cwd like CLAUDE.md)
        self._context_path, self._context_content = _find_project_context()
        # Per-directory rolling memory: auto-resume what was discussed/built here last time,
        # unless disabled. This is why "run it" works in a fresh session and the directory remembers.
        self._resumed_turns = 0
        if os.environ.get("JARVIS_NO_RESUME") != "1":
            try:
                prior = session_store.load_cwd()
                if prior:
                    self.chat_history = prior
                    self._resumed_turns = sum(1 for m in prior if m.get("role") == "user")
            except Exception:
                pass

    def _build_session(self) -> PromptSession:
        bindings = KeyBindings()

        @bindings.add("c-l")
        def _(event):
            self.console.clear()

        theme = _THEMES.get(self._theme, _THEMES["warm"])
        return PromptSession(
            history=FileHistory(_HISTORY_FILE),
            auto_suggest=AutoSuggestFromHistory(),
            completer=JarvisCompleter(),
            complete_while_typing=True,
            key_bindings=bindings,
            bottom_toolbar=self._bottom_toolbar,
            style=PTStyle.from_dict({
                "bottom-toolbar": f"{theme.get('muted', theme['accent'])} bg:{theme['header_bg']}",
                "prompt": f"{theme.get('grad_b', theme['accent'])} bold",
                "completion-menu.completion": f"bg:{theme['dropdown_bg']} {theme['text']}",
                "completion-menu.completion.current": f"bg:{theme['accent']} {theme['bg']}",
                "completion-menu.meta.completion": f"bg:{theme['dropdown_bg']} {theme.get('muted','#888')}",
            }),
        )

    # ── chrome ────────────────────────────────────────────────────────────────

    def _bottom_toolbar(self):
        model = os.environ.get("JARVIS_PRIMARY_MODEL", "gemma4:31b-cloud")
        cwd   = os.path.basename(os.getcwd())
        turns = len([m for m in self.chat_history if m.get("role") == "user"])
        return HTML(f" <b>jarvis</b> · {model} · ~/{cwd} · {turns} turns · /help for commands ")

    def _banner(self):
        """Warm-elegant banner: a gradient JARVIS wordmark, tagline, and meta line in a
        rounded amber panel. Never raises — chrome must not crash the REPL."""
        try:
            self._render_banner()
        except Exception:
            # Minimal, guaranteed-safe fallback — chrome must never crash the REPL.
            try:
                self.console.print(Text("  JARVIS", style="bold #E08A5F"),
                                   Text("// inline console", style="dim"))
            except Exception:
                pass

    def _render_banner(self):
        w = _warm()
        accent, grad_a, grad_b = w["accent"], w.get("grad_a", w["accent"]), w.get("grad_b", w["accent"])
        muted, rule = w.get("muted", "dim"), w.get("rule", "grey30")
        model = os.environ.get("JARVIS_PRIMARY_MODEL", "gemma4:31b-cloud")

        # Letter-spaced gradient wordmark + soft sigil.
        wordmark = _gradient_text("J A R V I S", grad_a, grad_b, bold=True)
        title = Text("  ") + Text("✦ ", style=accent) + wordmark
        tagline = Text("  inline console", style=f"italic {muted}")

        meta = (
            Text(f"  {model}", style=accent)
            + Text("   ·   ", style=rule)
            + Text(f"{len(SLASH_COMMANDS)} commands", style=muted)
            + Text("   ·   ", style=rule)
            + Text("@file", style=muted) + Text("  !shell", style=muted)
            + Text("  /help", style=muted)
        )

        body = Group(title, tagline, Text(""), meta)
        panel = Panel(
            body, box=_box.ROUNDED, border_style=accent,
            padding=(1, 2), expand=False,
        )

        self.console.print()
        # Subtle one-time reveal: render the panel through a brief Live so it "settles" in.
        if _ANIM and getattr(self.console, "is_terminal", False):
            try:
                import time
                with Live(panel, console=self.console, refresh_per_second=20,
                          transient=False) as live:
                    live.update(panel)
                    time.sleep(0.18)
            except Exception:
                self.console.print(panel)
        else:
            self.console.print(panel)

        if self._context_path:
            rel = os.path.relpath(self._context_path)
            self.console.print(Text(f"  context: {rel}", style=w.get("success", "green")))
        self.console.print(Rule(style=rule))

    def _lazy_jarvis_cli(self):
        if self._jarvis_cli is None:
            spec = importlib.util.spec_from_file_location("jarvis_cli", "jarvis-cli.py")
            mod  = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            self._jarvis_cli = mod
        return self._jarvis_cli

    # ── main loop ───────────────────────────────────────────────────────────────

    def run(self):
        # Non-tty stdin (piped/redirected) can't drive prompt_toolkit — it raises
        # NoConsoleScreenBufferError. Fall back to a plain line loop so scripted commands
        # (echo "/agents" | jarvis-cli.py) work instead of crashing with a raw traceback.
        try:
            _interactive = sys.stdin.isatty()
        except Exception:
            _interactive = False
        if not _interactive:
            return self._run_noninteractive()

        if self.session is None:
            self.session = self._build_session()
        self._banner()
        if self._resumed_turns:
            w = _warm()
            self.console.print(
                Text("  ↻ resumed ", style=w.get("success", "green"))
                + Text(f"{self._resumed_turns} turns", style="bold")
                + Text(" from this directory", style=w.get("muted", "dim"))
                + Text("   ·   /forget to start fresh", style=w.get("rule", "grey30"))
            )
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
                self._autosave()
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
                    self._autosave()
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
                # Incremental per-directory save so a hard-kill (closed terminal) still
                # leaves the directory's memory up to date — not just a clean exit.
                if self.chat_history:
                    try:
                        session_store.save_cwd(self.chat_history)
                    except Exception:
                        pass

    def _run_noninteractive(self):
        """Process commands from non-tty stdin (piped/redirected) without prompt_toolkit.

        Each line is dispatched through the same handlers as the interactive REPL, so /agents,
        /save, /load, /export, etc. are reachable in scripts. No prompt UI, no crash.
        """
        self.console.print(
            "[dim]non-interactive stdin — reading commands line by line (no prompt UI). "
            "Run in a real terminal for the full REPL.[/]")
        try:
            for raw in sys.stdin:
                text = raw.strip()
                if not text:
                    continue
                try:
                    if self._dispatch_line(text) == "EXIT":
                        break
                except Exception as e:
                    self._print_error(e)
                finally:
                    if sys.stdout is not self._real_stdout:
                        sys.stdout = self._real_stdout
        except (EOFError, KeyboardInterrupt):
            pass
        self._autosave()

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
            # /build and /code → force coding agent mode
            if cmd in ("build", "code"):
                if not arg:
                    self.console.print("[yellow]Usage:[/] /build <what to build>")
                    return None
                self._agent_turn("auto", arg, force_coding=True)
                return None
            if cmd in _INLINE:
                self._handle_inline(cmd, arg)
                return None
            if cmd in _AGENT_MODES:
                self._agent_turn(cmd, arg)
                return None
            self.console.print(f"[yellow]Unknown command:[/] /{cmd}  [dim](try /help)[/]")
            return None

        # Plain text → auto-mode agent turn (with automatic coding intent detection)
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

    def _agent_turn(self, mode: str, task: str, force_coding: bool = False):
        from core.system.llm_adapter import set_stream_hook
        from core.hermes.hermes_cli_runner import EnvironmentHandshake, SkillsEngine, call_llm
        from tools.dispatcher import TOOL_DEFINITIONS, dispatch

        cli  = self._lazy_jarvis_cli()
        task = self._expand_file_refs(task)
        _jtrace(f"[TRACE] {__name__}._agent_turn: enter mode={mode} force_coding={force_coding} task={task[:60]}")

        # Coding intent detection — runs in < 1 ms, no LLM cost
        if force_coding:
            from core.orchestrator.intent_router import _build_mandate
            routing = {"mode": "coding", "mandate": _build_mandate(task, ["run_frontend_agent", "run_qa_agent"], "run_frontend_agent")}
        else:
            routing = _classify_intent(task)

        if routing["mode"] == "coding":
            self.console.print(
                f"[bold cyan]◈ coding mode[/] [dim]— activating agents[/]"
            )

        prompt_content = cli.build_prompt(mode, task)
        handshake = EnvironmentHandshake()
        context_block = ""
        if self._context_content:
            context_block = f"\n\n<project_context>\n{self._context_content}\n</project_context>"
        from core.jarvis_prompt import base_prompt
        from datetime import datetime as _dt
        _out_dir = os.environ.get("JARVIS_OUTPUT_ROOT") or os.getcwd()
        system_instruction = (
            base_prompt(date=_dt.now().strftime("%A, %B %d, %Y"), output_dir=_out_dir)
            + f"\n\n{handshake.get_system_prompt_addition()}"
            + f"{context_block}"
            + f"{routing.get('mandate', '')}"
        )
        skills = SkillsEngine().get_skills_prompt_addition(prompt_content)

        self.chat_history.append({"role": "user", "content": prompt_content})
        messages = [{"role": "system", "content": system_instruction + skills}] + self.chat_history
        model = os.environ.get("JARVIS_PRIMARY_MODEL", cli.DEFAULT_MODEL)

        real_stdout = self._real_stdout

        class _Sink:
            def write(self, *a, **k): pass
            def flush(self): pass

        # [TRACE] lines no longer touch stderr — they route through core.trace.trace() to
        # logs/jarvis_trace.log (gated by JARVIS_TRACE), so the sink can drop everything.

        # Phase 39: harness-enforced autonomy + verification state.
        from core.orchestrator import exec_guard
        continues = 0            # autonomy nudges used this turn
        pending_unverified = False  # a consequential action awaits verification

        coding = routing["mode"] == "coding"
        from contextlib import nullcontext
        from core.cli.live_graph import GraphSession
        graph_ctx = GraphSession(self.console, task, model=model) if coding else nullcontext()

        with graph_ctx as gsession:
            if coding:
                from agents.model_router import get_model as _get_orch_model
                _orch = _get_orch_model("orchestrator")
                # Show the actual orchestrator model (Kimi/architect), not the REPL loop model.
                gsession.graph.planner_running("decomposing with " + _orch)

            while True:
                buf = {"content": "", "reasoning": ""}

                def render():
                    w = _warm()
                    accent, muted = w["accent"], w.get("muted", "dim")
                    parts = []
                    if buf["reasoning"] and not buf["content"]:
                        rtext = Text(buf["reasoning"], style=f"italic {muted}")
                        if _ANIM and not buf.get("done"):
                            rtext.append(" ▌", style=f"blink {accent}")
                        parts.append(rtext)
                    if buf["content"]:
                        parts.append(Markdown(buf["content"]))
                    if not parts:
                        # The key animation: a real amber spinner while the model thinks.
                        if _ANIM and getattr(self.console, "is_terminal", False) and not buf.get("done"):
                            return Spinner("dots", text=Text("  thinking…", style=muted), style=accent)
                        parts.append(Text("  thinking…", style=muted))
                    return Group(*parts)

                try:
                    real_stderr = sys.stderr
                    if coding:
                        sys.stdout = _Sink()
                        sys.stderr = _Sink()
                        try:
                            msg = call_llm(messages=messages, model=model, tools=TOOL_DEFINITIONS)
                        finally:
                            sys.stdout = real_stdout
                            sys.stderr = real_stderr
                    else:
                        with Live(render(), console=self.console, refresh_per_second=12,
                                  vertical_overflow="visible") as live:
                            def hook(t, kind):
                                buf[kind] = buf.get(kind, "") + t
                                live.update(render())
                            set_stream_hook(hook)
                            # Swallow the adapter's raw prints on stdout; keep [TRACE] on stderr.
                            sys.stdout = _Sink()
                            sys.stderr = _Sink()
                            try:
                                msg = call_llm(messages=messages, model=model, tools=TOOL_DEFINITIONS)
                            finally:
                                sys.stdout = real_stdout
                                sys.stderr = real_stderr
                                set_stream_hook(None)
                                buf["done"] = True          # drop spinner/caret on the final frame
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
                    content = msg.get("content", "") or ""
                    # Part 1: autonomy gate — don't let it hand back a to-do list; make it execute.
                    if exec_guard.is_deferral(content) and continues < exec_guard.MAX_CONTINUES:
                        continues += 1
                        nudge = ("Do NOT hand back a to-do list or 'recommended next steps'. Execute the "
                                 "next step YOURSELF now using your tools. Before acting, confirm you are in "
                                 "the right window/app and on the right element; after acting, verify it "
                                 "worked (verify_location / verify_outcome). Continue until the goal is fully "
                                 "done and verified — only stop when truly finished or to ask permission.")
                        messages.append({"role": "user", "content": nudge})
                        self.chat_history.append({"role": "user", "content": nudge})
                        self.console.print("[dim]↻ continuing autonomously…[/]")
                        continue
                    # Part 2: block an unverified success claim once.
                    if exec_guard.should_challenge(content, pending_unverified) and continues < exec_guard.MAX_CONTINUES:
                        continues += 1
                        chal = ("You claim success but the last action is NOT verified. Call verify_location "
                                "(scroll up/down to confirm you're at the right place) or verify_outcome before "
                                "saying it's done.")
                        messages.append({"role": "user", "content": chal})
                        self.chat_history.append({"role": "user", "content": chal})
                        if not coding:
                            self.console.print("[dim]↻ verifying before finishing…[/]")
                        continue
                    # Surface a RETURNED-but-not-streamed final message (e.g. the graceful
                    # "all models unavailable" notice is returned by call_llm, never streamed —
                    # previously it vanished and the user saw nothing). Smoke-test /desktop, /code.
                    failed = content.strip().startswith("⚠")
                    if content and not buf["content"]:
                        if failed:
                            self.console.print(Text(content, style=_warm().get("danger", "red")))
                        else:
                            self.console.print(Markdown(content))

                    if not coding:
                        self.console.print()   # spacing after the answer
                    if coding:
                        n_agents = len(gsession.graph.agents)
                        if failed:
                            # Never claim success when the model failed. Show the real reason.
                            gsession.finish([content.strip().splitlines()[0] if content.strip() else
                                             "⚠ Model unavailable — nothing was generated."])
                        elif n_agents:
                            gsession.finish([
                                f"✓ Shipped — {n_agents} agents",
                                "◆ Indexed contracts → memory.gbrain",
                            ])
                        elif content.strip():
                            # The model answered directly (e.g. a trivial code snippet) — honest,
                            # no "0 agents" theater.
                            gsession.finish(["✓ Done"])
                        else:
                            gsession.finish(["⚠ No output produced — model unavailable or empty response."])
                    return

                # Render tool calls as cards, dispatch, feed results back
                for call in msg["tool_calls"]:
                    fn   = call["function"]["name"]
                    args = call["function"]["arguments"]
                    args_str = args if isinstance(args, str) else _short(args)

                    # Part 3: permission gate — ask y/N before risky/irreversible actions.
                    risky, reason = exec_guard.is_risky(fn, args)
                    _jtrace(f"[TRACE] {__name__}._agent_turn: tool_call fn={fn} risky={risky} consequential={exec_guard.is_consequential(fn)}")
                    if risky and os.environ.get("JARVIS_AUTO_APPROVE") != "1":
                        if not self._ask_yes_no(f"⚠ Jarvis wants to {reason}: {fn}({args_str}). Proceed?"):
                            denied = (f"User DENIED the action {fn}. Do NOT retry it. Find a safe alternative "
                                      "or ask the user how to proceed.")
                            self.console.print("[red]  ✗ denied by user[/]")
                            _tcid = call.get("id")
                            denied_msg = {"role": "tool", "content": denied}
                            if _tcid:
                                denied_msg["tool_call_id"] = _tcid
                            self.chat_history.append(dict(denied_msg))
                            messages.append(denied_msg)
                            continue

                    if not coding:
                        _w = _warm()
                        _acc, _mut = _w["accent"], _w.get("muted", "dim")
                        self.console.print(Panel(
                            Text(f"{fn}", style=f"bold {_acc}") + Text(f"  {args_str}", style=_mut),
                            title=Text("▸ tool", style=_acc), title_align="left",
                            box=_box.ROUNDED, border_style=_acc, padding=(0, 1), expand=False,
                        ))

                    # Part 2: pre-act grounding — capture window + screen baseline before a consequential action.
                    consequential = exec_guard.is_consequential(fn)
                    baseline = None
                    win = ""
                    if consequential:
                        win = exec_guard.active_window_title()
                        baseline = exec_guard.capture_baseline()

                    result = self._dispatch_with_timeout(dispatch, fn, args)
                    _jtrace(f"[TRACE] {__name__}._agent_turn: tool_result fn={fn} result={str(result)[:80]}")
                    if not coding:
                        preview = str(result)[:400]
                        _w = _warm()
                        self.console.print(
                            Text("  ⮑ ", style=_w["accent"]) + Text(preview, style=_w.get("muted", "dim")))
                    _tcid = call.get("id")
                    tool_msg = {"role": "tool", "content": str(result)}
                    if _tcid:
                        tool_msg["tool_call_id"] = _tcid
                    self.chat_history.append(dict(tool_msg))
                    messages.append(tool_msg)

                    # Part 2: observe-after-act + verification tracking.
                    if consequential:
                        pending_unverified = True
                        try:
                            changed, obs = exec_guard.observe_change(baseline)
                        except Exception:
                            changed, obs = False, ""
                        note = (f"[active window: {win}] " if win else "") + (obs or "")
                        if note.strip():
                            self.chat_history.append({"role": "user", "content": note})
                            messages.append({"role": "user", "content": note})
                        if changed:
                            pending_unverified = False
                    elif exec_guard.is_verify(fn):
                        pending_unverified = False

    def _ask_yes_no(self, question: str) -> bool:
        """Synchronously ask the user a yes/no question in the terminal (Phase 39).

        Returns True only on an explicit yes. Any cancel/EOF defaults to No (safe)."""
        try:
            self.console.print(f"[bold yellow]{question}[/] [dim][y/N][/]")
            ans = input("  > ").strip().lower()
            return ans in ("y", "yes")
        except (EOFError, KeyboardInterrupt):
            self.console.print("[dim](cancelled → treated as No)[/]")
            return False
        except Exception:
            return False

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
        w = _warm()
        accent, muted, rule_c = w["accent"], w.get("muted", "dim"), w.get("rule", "grey30")
        self.console.print(f"[green]model:[/] {cur} → [bold cyan]{arg}[/]  [dim](banner shows startup; live session updated)[/]")
        # Reprint the meta line in banner style so the new active model is unmistakable.
        meta = (
            Text(f"  ✦ {arg}", style=f"bold {accent}")
            + Text("   ·   ", style=rule_c)
            + Text("active now · all future turns use this model", style=muted)
        )
        self.console.print(meta)

    def _cmd_models(self, arg):
        arg = (arg or "").strip()
        w = _warm()
        accent, muted = w["accent"], w.get("muted", "dim")
        cur = os.environ.get("JARVIS_PRIMARY_MODEL", "gemma4:31b-cloud")

        # Determine scope: empty = both, "nvidia" = NVIDIA only, "openrouter"/"or" = OR only, else = query both.
        scope_nvidia = not arg or arg.lower() in ("nvidia", "nv")
        scope_openrouter = not arg or arg.lower() in ("openrouter", "or")
        query = None if (scope_nvidia or scope_openrouter) else arg

        # ── NVIDIA Build ──────────────────────────────────────────────────────
        nv_results = []
        if scope_nvidia or query:
            try:
                from core.system.nvidia_catalog import list_models as nv_list
                nv_results = nv_list(query, limit=60)
            except Exception as e:
                self.console.print(f"[yellow]NVIDIA catalog: {e}[/]")

        # ── OpenRouter ────────────────────────────────────────────────────────
        or_results = []
        if scope_openrouter or query:
            try:
                from core.system.openrouter_catalog import list_models as or_list
                or_results = or_list(query, limit=80)
                # Annotate source
                for m in or_results:
                    m.setdefault("source", "openrouter")
            except Exception as e:
                self.console.print(f"[yellow]OpenRouter catalog: {e}[/]")

        title_parts = []
        if scope_nvidia and not scope_openrouter:
            title_parts.append("NVIDIA Build")
        elif scope_openrouter and not scope_nvidia:
            title_parts.append("OpenRouter")
        elif query:
            title_parts.append(f'results for "{query}"')
        else:
            title_parts.append("All providers")

        # ── NVIDIA table ──────────────────────────────────────────────────────
        if nv_results:
            t = Table(
                title=f"NVIDIA Build — {title_parts[0] if query else 'NVIDIA Build'}  [dim](40 RPM free)[/]",
                header_style=f"bold {accent}",
            )
            t.add_column("Model ID (use as: /model <id>)", style="bold", no_wrap=True)
            t.add_column("Name", style=muted)
            t.add_column("Ctx K", justify="right", style=muted)
            t.add_column("Rate", justify="right", style="green")
            for m in nv_results:
                mid = m.get("id", "?")
                ctx = m.get("context") or 0
                ctx_str = f"{ctx // 1000}K" if ctx else "-"
                t.add_row(
                    mid + ("  ◀ active" if mid == cur else ""),
                    m.get("name", "-"),
                    ctx_str,
                    m.get("rate_limit", "40 RPM"),
                )
            self.console.print(t)

        # ── OpenRouter table ──────────────────────────────────────────────────
        if or_results:
            t = Table(
                title=f"OpenRouter — {title_parts[0] if query else 'OpenRouter'}  [dim](use openrouter/<id> form)[/]",
                header_style=f"bold {accent}",
            )
            t.add_column("Model ID", style="bold", no_wrap=True)
            t.add_column("Name", style=muted)
            t.add_column("Ctx K", justify="right", style=muted)
            t.add_column("$/Mtok in", justify="right", style=muted)
            t.add_column("$/Mtok out", justify="right", style=muted)
            for m in or_results:
                mid = m.get("id", "?")
                ctx = m.get("context") or 0
                ctx_str = f"{ctx // 1000}K" if ctx else "-"
                pin = m.get("prompt_price")
                pout = m.get("completion_price")
                free_tag = "  [green]FREE[/]" if (pin == 0 or (isinstance(pin, (int, float)) and pin == 0.0)) else ""
                t.add_row(
                    mid + ("  ◀ active" if mid == cur else "") + free_tag,
                    m.get("name", "-"),
                    ctx_str,
                    "FREE" if (pin == 0 or pin == 0.0) else ("-" if pin is None else f"${pin:.3f}"),
                    "FREE" if (pout == 0 or pout == 0.0) else ("-" if pout is None else f"${pout:.3f}"),
                )
            self.console.print(t)

        if not nv_results and not or_results:
            self.console.print(
                f"[yellow]No models found for '{arg}'.[/] "
                "[dim]OPENROUTER_API_KEY + network needed for live catalog.[/]")
            return

        self.console.print(
            f"[{muted}]"
            "/model <id>  set primary  ·  "
            "/setmodel <agent> <id>  per-agent  ·  "
            "/models nvidia  ·  /models openrouter  ·  /models <search>"
            "[/]")

    def _cmd_agents(self, arg):
        """Show the model assigned to each agent/role and its source."""
        try:
            from agents.model_router import get_all_agent_models
            data = get_all_agent_models()
        except Exception as e:
            self.console.print(f"[red]{e}[/]")
            return
        t = Table(title="Agent Models", header_style="bold cyan")
        t.add_column("Agent", style="bold")
        t.add_column("Model", style="cyan")
        t.add_column("Source", style="dim")
        for agent, info in data.items():
            t.add_row(agent, info.get("model", "?"), info.get("source", ""))
        self.console.print(t)
        self.console.print(
            "[dim]Change: [bold]/setmodel <agent> <model>[/]  ·  Reset: [bold]/resetmodel <agent>[/]  ·  "
            "Browse: [bold]/models <query>[/][/]")

    def _cmd_setmodel(self, arg):
        """Assign any model (incl. any OpenRouter model) to an agent; persists across runs."""
        parts = (arg or "").split()
        if len(parts) < 2:
            self.console.print(
                "[yellow]Usage:[/] /setmodel <agent> <model>\n"
                "[dim]agents: frontend, backend, qa, orchestrator, verifier, iac, or skill:<name>\n"
                "model: a native name (gemini-3.5-flash) or an OpenRouter slug "
                "(anthropic/claude-opus-4.8 → routed via OpenRouter)[/]")
            return
        target, model = parts[0], parts[1]
        try:
            from agents.model_router import set_agent_model
            stored = set_agent_model(target, model)
        except Exception as e:
            self.console.print(f"[red]{e}[/]")
            return
        self.console.print(
            f"[green]{target}[/] → [bold cyan]{stored}[/]  "
            "[dim](persisted to config/agent_models.json)[/]")

    def _cmd_resetmodel(self, arg):
        """Clear a per-agent model override (revert to default)."""
        target = (arg or "").strip()
        if not target:
            self.console.print("[yellow]Usage:[/] /resetmodel <agent>")
            return
        try:
            from agents.model_router import reset_agent_model
            removed = reset_agent_model(target)
        except Exception as e:
            self.console.print(f"[red]{e}[/]")
            return
        if removed:
            self.console.print(f"[green]reset[/] {target} [dim](back to default)[/]")
        else:
            self.console.print(f"[dim]no override set for {target}[/]")

    def _cmd_tools(self, arg):
        try:
            import re as _re
            from tools.dispatcher import TOOL_DEFINITIONS

            def _clean_desc(d: str) -> str:
                # Tool descriptions can embed XML-ish prompt scaffolding (e.g. <tool>open_app</tool>);
                # strip tags + collapse whitespace so the table shows clean, user-facing copy.
                d = _re.sub(r"<[^>]+>", "", d or "")
                d = _re.sub(r"\s+", " ", d).strip()
                return (d[:70] + "…") if len(d) > 71 else d

            t = Table(title=f"Tools ({len(TOOL_DEFINITIONS)})", header_style="bold cyan")
            t.add_column("#", style="dim", width=3)
            t.add_column("Tool", style="bold")
            t.add_column("Description", style="dim")
            for i, tool in enumerate(TOOL_DEFINITIONS, 1):
                fn = tool["function"]
                t.add_row(str(i), fn["name"], _clean_desc(fn.get("description", "")))
            self.console.print(t)
        except Exception as e:
            self.console.print(f"[red]{e}[/]")

    def _cmd_theme(self, arg):
        name = arg.strip().lower()
        if name not in _THEMES:
            self.console.print(f"[yellow]themes:[/] {' | '.join(_THEMES)}")
            return
        self._theme = name
        self.session = self._build_session()
        self.console.print(f"[cyan]theme → {name}[/] [dim](applied to REPL toolbar)[/]")

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

    def _cmd_remote(self, arg):
        """Hermes remote pairing: start | stop | status.

        'start' launches `jarvis-cli.py --remote` in its OWN console window —
        the flow needs a live terminal for the QR code and a blocking uvicorn
        server, so it can't run inside the REPL. The REPL tracks the child
        process for stop/status.
        """
        import subprocess
        sub = (arg or "start").strip().lower()
        proc = getattr(self, "_remote_proc", None)
        alive = proc is not None and proc.poll() is None

        if sub in ("", "start"):
            if alive:
                self.console.print(f"[yellow]Remote session already running (pid {proc.pid}). "
                                   f"Use /remote stop first.[/]")
                return
            try:
                py = sys.executable
                cli = os.path.join(os.getcwd(), "jarvis-cli.py")
                self._remote_proc = subprocess.Popen(
                    [py, cli, "--remote"],
                    cwd=os.getcwd(),
                    creationflags=subprocess.CREATE_NEW_CONSOLE,
                )
                self.console.print(
                    f"[green]Remote pairing started[/] [dim](pid {self._remote_proc.pid})[/]\n"
                    "[dim]A new console window is opening with the Cloudflare tunnel, "
                    "pairing QR code, and Hermes server logs.\n"
                    "Scan the QR with your phone to pair. "
                    "Manage with /remote status · /remote stop[/]")
            except Exception as e:
                self.console.print(f"[red]Failed to start remote session: {e}[/]")

        elif sub == "stop":
            if not alive:
                self.console.print("[dim]No remote session running.[/]")
                return
            try:
                # Kill the whole tree — the child owns a cloudflared subprocess
                # that plain terminate() would orphan (tunnel left open).
                subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                               capture_output=True)
                self._remote_proc = None
                self.console.print("[green]Remote session stopped[/] [dim](server + tunnel killed)[/]")
            except Exception as e:
                self.console.print(f"[red]Failed to stop: {e}[/]")

        elif sub == "status":
            if alive:
                self.console.print(f"[green]Remote session running[/] [dim](pid {proc.pid}) — "
                                   f"QR + logs are in its console window[/]")
            else:
                self.console.print("[dim]No remote session running. Start with /remote[/]")
        else:
            self.console.print("[dim]usage: /remote [start|stop|status][/]")

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

    def _cmd_save(self, arg):
        """Save current session to ~/.jarvis/sessions/."""
        if not self.chat_history:
            self.console.print("[dim]nothing to save yet[/]")
            return
        try:
            path = session_store.save(self.chat_history, name=arg.strip() or "")
            turns = sum(1 for m in self.chat_history if m.get("role") == "user")
            self.console.print(f"[green]saved[/] {turns} turns → [dim]{path}[/]")
        except Exception as e:
            self.console.print(f"[red]save failed: {e}[/]")

    def _cmd_load(self, arg):
        """Restore most-recent (or named) saved session."""
        try:
            if arg.strip():
                msgs = session_store.load_file(arg.strip())
            else:
                msgs = session_store.load_last()
            if not msgs:
                self.console.print("[dim]no sessions found — start chatting first[/]")
                return
            self.chat_history = msgs
            turns = sum(1 for m in msgs if m.get("role") == "user")
            self.console.print(f"[green]loaded[/] {turns} turns")
            # Print last assistant reply for context
            last = next((m for m in reversed(msgs) if m.get("role") == "assistant"), None)
            if last and last.get("content"):
                from rich.markdown import Markdown
                self.console.print(Markdown(last["content"][:800]))
        except Exception as e:
            self.console.print(f"[red]load failed: {e}[/]")

    def _cmd_forget(self, arg):
        """Clear this directory's rolling memory and start a fresh conversation."""
        self.chat_history = []
        self._resumed_turns = 0
        removed = False
        try:
            removed = session_store.clear_cwd()
        except Exception as e:
            self.console.print(f"[red]forget failed: {e}[/]")
            return
        w = _warm()
        if removed:
            self.console.print(Text("  ✦ memory cleared", style=w.get("success", "green"))
                               + Text(" — this directory starts fresh", style=w.get("muted", "dim")))
        else:
            self.console.print("[dim]nothing to forget — already a clean slate[/]")

    def _cmd_new(self, arg):
        """Alias for /forget — start a new conversation in this directory."""
        self._cmd_forget(arg)

    def _cmd_context(self, arg):
        """Show or reload the active JARVIS.md project context file."""
        if arg.strip():
            # Allow specifying a path directly
            p = arg.strip()
            if os.path.isfile(p):
                try:
                    with open(p, "r", encoding="utf-8", errors="replace") as f:
                        self._context_content = f.read()
                    self._context_path = os.path.abspath(p)
                    self.console.print(f"[green]context loaded:[/] [dim]{self._context_path}[/]")
                except Exception as e:
                    self.console.print(f"[red]could not read {p}: {e}[/]")
            else:
                self.console.print(f"[yellow]file not found: {p}[/]")
            return
        if not self._context_path:
            self.console.print("[dim]no JARVIS.md found in this directory tree[/]")
            self.console.print("[dim]create one here: JARVIS.md — Jarvis will pick it up[/]")
            return
        rel = os.path.relpath(self._context_path)
        self.console.print(f"[cyan]context file:[/] [dim]{rel}[/]")
        if self._context_content:
            from rich.markdown import Markdown
            self.console.print(Markdown(self._context_content[:2000]))


    def _cmd_build(self, arg):
        """Force coding mode and build something."""
        if not arg:
            self.console.print("[yellow]Usage:[/] /build <what to build>\n[dim]Examples: /build a snake game in pygame · /build a React todo app[/]")
            return
        self._agent_turn("auto", arg, force_coding=True)

    def _cmd_code(self, arg):
        """Alias for /build."""
        self._cmd_build(arg)

    def _autosave(self):
        """Silently persist session on exit: a timestamped archive AND the per-directory
        rolling memory (so the same directory resumes next time)."""
        if not self.chat_history:
            return
        try:
            session_store.save(self.chat_history)          # global timestamped archive
        except Exception:
            pass
        try:
            session_store.save_cwd(self.chat_history)        # per-directory rolling memory
        except Exception:
            pass


def _short(d) -> str:
    s = str(d)
    return s if len(s) <= 80 else s[:77] + "…"


def main():
    JarvisRepl().run()


if __name__ == "__main__":
    main()

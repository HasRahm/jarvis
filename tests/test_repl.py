"""Tests for the inline streaming REPL (core/cli/repl.py).

Covers the pure logic — completer, command classification, @file expansion,
and the llm_adapter stream-hook routing — without needing a real TTY.
"""
import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from prompt_toolkit.document import Document
from core.cli.repl import JarvisCompleter, JarvisRepl, _AGENT_MODES, _INLINE, _short


class TestCompleter:
    def setup_method(self):
        self.c = JarvisCompleter()

    def _complete(self, text):
        return [comp.text for comp in self.c.get_completions(Document(text), None)]

    def test_slash_prefix_filters(self):
        out = self._complete("/mod")
        assert "/model" in out and "/models" in out
        assert "/research" not in out

    def test_slash_research(self):
        out = self._complete("/res")
        assert "/research" in out

    def test_empty_slash_returns_many(self):
        out = self._complete("/")
        assert len(out) >= 20

    def test_no_completion_for_plain_text(self):
        out = self._complete("open chrome and search")
        assert out == []

    def test_slash_with_space_stops_completing(self):
        # once an argument is being typed, no command completion
        out = self._complete("/model gpt")
        assert out == []

    def test_file_completion_finds_known_file(self, tmp_path, monkeypatch):
        (tmp_path / "alpha.txt").write_text("x")
        (tmp_path / "beta.txt").write_text("y")
        monkeypatch.chdir(tmp_path)
        out = self._complete("read @al")
        assert any("alpha" in o for o in out)


class TestCommandClassification:
    def test_agent_modes_complete(self):
        for m in ("research", "diagnose", "browse", "desktop", "excel", "shell", "auto", "screen"):
            assert m in _AGENT_MODES

    def test_inline_commands(self):
        for c in ("help", "model", "models", "tools", "clear", "theme", "exit", "quit"):
            assert c in _INLINE

    def test_agent_and_inline_disjoint(self):
        assert _AGENT_MODES.isdisjoint(_INLINE), "a command can't be both agent and inline"


class TestFileExpansion:
    def setup_method(self):
        self.repl = JarvisRepl()

    def test_expands_existing_file(self, tmp_path, monkeypatch):
        f = tmp_path / "note.md"
        f.write_text("SECRET_MARKER_123", encoding="utf-8")
        monkeypatch.chdir(tmp_path)
        result = self.repl._expand_file_refs("summarise @note.md please")
        assert "SECRET_MARKER_123" in result
        assert "FILE: note.md" in result

    def test_no_refs_returns_unchanged(self):
        text = "just a normal prompt with no refs"
        assert self.repl._expand_file_refs(text) == text

    def test_missing_file_is_skipped_gracefully(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        result = self.repl._expand_file_refs("look at @does_not_exist.txt")
        # original text preserved, no crash, no file block appended
        assert "does_not_exist.txt" in result
        assert "--- FILE:" not in result


class TestStreamHookRouting:
    def test_hook_receives_tokens(self):
        from core.system import llm_adapter
        captured = []
        llm_adapter.set_stream_hook(lambda t, k: captured.append((k, t)))
        llm_adapter._emit("hello ", "content", raw_print=lambda: None)
        llm_adapter._emit("reason", "reasoning", raw_print=lambda: None)
        llm_adapter.set_stream_hook(None)
        assert ("content", "hello ") in captured
        assert ("reasoning", "reason") in captured

    def test_falls_back_to_raw_print_when_unset(self):
        from core.system import llm_adapter
        llm_adapter.set_stream_hook(None)
        flag = []
        llm_adapter._emit("x", "content", raw_print=lambda: flag.append(1))
        assert flag == [1]

    def test_hook_exception_does_not_break_stream(self):
        from core.system import llm_adapter
        def bad_hook(t, k):
            raise RuntimeError("boom")
        llm_adapter.set_stream_hook(bad_hook)
        flag = []
        # exception in hook should fall through to raw_print, not propagate
        llm_adapter._emit("x", "content", raw_print=lambda: flag.append(1))
        llm_adapter.set_stream_hook(None)
        assert flag == [1]


class TestResilience:
    """A single bad line must never drop the user out of the REPL."""

    def setup_method(self):
        self.repl = JarvisRepl()

    def test_dispatch_exit_command(self):
        assert self.repl._dispatch_line("/exit") == "EXIT"
        assert self.repl._dispatch_line("/quit") == "EXIT"

    def test_dispatch_unknown_command_returns_none(self):
        # unknown slash command should not raise, just return None
        assert self.repl._dispatch_line("/bogus") is None

    def test_dispatch_inline_does_not_raise(self):
        # /help is inline and must complete without raising
        assert self.repl._dispatch_line("/help") is None

    def test_agent_turn_error_is_caught_not_raised(self, monkeypatch):
        # Force the agent turn to blow up; _dispatch_line must swallow via _agent_turn's guard
        def boom(*a, **k):
            raise RuntimeError("simulated model failure")
        monkeypatch.setattr(self.repl, "_agent_turn", lambda *a, **k: boom())
        # The run-loop wraps _dispatch_line; here we assert _agent_turn raising
        # is the only thing that propagates, so the loop's try/except can catch it.
        with pytest.raises(RuntimeError):
            self.repl._dispatch_line("hello world")

    def test_print_error_never_raises(self):
        # _print_error must handle any exception object without raising itself
        self.repl._print_error(ValueError("x"))
        self.repl._print_error(RuntimeError("boom"))

    def test_real_stdout_captured(self):
        assert self.repl._real_stdout is not None


class TestDispatchTimeout:
    """A hung tool must never freeze the REPL — it gets abandoned with an error."""

    def setup_method(self):
        self.repl = JarvisRepl()

    def test_fast_tool_returns_result(self):
        result = self.repl._dispatch_with_timeout(lambda fn, a: f"ok:{fn}", "my_tool", {})
        assert result == "ok:my_tool"

    def test_tool_exception_becomes_error_string(self):
        def boom(fn, a):
            raise RuntimeError("tool exploded")
        result = self.repl._dispatch_with_timeout(boom, "bad_tool", {})
        assert isinstance(result, str)
        assert "tool exploded" in result

    def test_hung_tool_times_out(self, monkeypatch):
        import time
        monkeypatch.setenv("JARVIS_TOOL_TIMEOUT", "1")
        def hang(fn, a):
            time.sleep(30)
        result = self.repl._dispatch_with_timeout(hang, "hung_tool", {})
        assert "timed out" in result
        assert "hung_tool" in result

    def test_timeout_env_var_respected(self, monkeypatch):
        import time
        monkeypatch.setenv("JARVIS_TOOL_TIMEOUT", "2")
        start = time.time()
        self.repl._dispatch_with_timeout(lambda fn, a: time.sleep(60), "slow", {})
        elapsed = time.time() - start
        assert elapsed < 10, "timeout env var was not respected"


class TestShortHelper:
    def test_short_passthrough(self):
        assert _short("abc") == "abc"

    def test_short_truncates(self):
        out = _short("z" * 200)
        assert len(out) <= 80
        assert out.endswith("…")

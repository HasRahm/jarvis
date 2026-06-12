"""Phase 24 — agent cursor overlay: queue logic and no-op safety.

Never starts tkinter in CI: AgentCursor is built with start_thread=False.
"""
import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import tools.agent_cursor as ac
from tools.agent_cursor import (
    AgentCursor, cursor_enabled, cursor_hidden, move_to, pulse, hide, show,
    agent_cursor_tool,
)


@pytest.fixture(autouse=True)
def reset_singleton(monkeypatch):
    monkeypatch.setattr(ac, "_instance", None)
    yield
    ac._instance = None


class TestEnvGate:
    def test_default_off(self, monkeypatch):
        monkeypatch.delenv("JARVIS_AGENT_CURSOR", raising=False)
        assert not cursor_enabled()

    def test_on(self, monkeypatch):
        monkeypatch.setenv("JARVIS_AGENT_CURSOR", "1")
        assert cursor_enabled()


class TestNoOpSafety:
    def test_all_apis_noop_when_disabled(self, monkeypatch):
        monkeypatch.setenv("JARVIS_AGENT_CURSOR", "0")
        # none of these may raise or spawn a thread
        move_to(100, 100)
        pulse()
        hide()
        show()
        assert ac._instance is None

    def test_cursor_hidden_noop_when_disabled(self, monkeypatch):
        monkeypatch.setenv("JARVIS_AGENT_CURSOR", "0")
        with cursor_hidden():
            pass  # must not raise or sleep noticeably

    def test_broken_instance_drops_commands(self):
        inst = AgentCursor(start_thread=False)
        inst._broken = True
        inst.send("move", 1, 2, True)
        assert inst._cmds.empty()


class TestCommandQueue:
    def test_send_enqueues(self):
        inst = AgentCursor(start_thread=False)
        inst.send("move", 10, 20, True)
        inst.send("pulse")
        inst.send("hide")
        assert inst._cmds.get_nowait() == ("move", 10, 20, True)
        assert inst._cmds.get_nowait() == ("pulse",)
        assert inst._cmds.get_nowait() == ("hide",)

    def test_module_move_routes_to_instance(self, monkeypatch):
        monkeypatch.setenv("JARVIS_AGENT_CURSOR", "1")
        inst = AgentCursor(start_thread=False)
        monkeypatch.setattr(ac, "_instance", inst)
        move_to(33, 44, animate=False)
        assert inst._cmds.get_nowait() == ("move", 33, 44, False)

    def test_hide_show_route(self, monkeypatch):
        monkeypatch.setenv("JARVIS_AGENT_CURSOR", "1")
        inst = AgentCursor(start_thread=False)
        monkeypatch.setattr(ac, "_instance", inst)
        hide()
        show()
        assert inst._cmds.get_nowait() == ("hide",)
        assert inst._cmds.get_nowait() == ("show",)

    def test_cursor_hidden_hides_then_shows(self, monkeypatch):
        monkeypatch.setenv("JARVIS_AGENT_CURSOR", "1")
        inst = AgentCursor(start_thread=False)
        monkeypatch.setattr(ac, "_instance", inst)
        with cursor_hidden():
            assert inst._cmds.get_nowait() == ("hide",)
        assert inst._cmds.get_nowait() == ("show",)


class TestTool:
    def test_off_action(self, monkeypatch):
        monkeypatch.setenv("JARVIS_AGENT_CURSOR", "1")
        out = agent_cursor_tool("off")
        assert "OFF" in out
        assert os.environ["JARVIS_AGENT_CURSOR"] == "0"

    def test_status(self, monkeypatch):
        monkeypatch.setenv("JARVIS_AGENT_CURSOR", "0")
        assert "OFF" in agent_cursor_tool("status")

    def test_unknown(self):
        assert agent_cursor_tool("dance").startswith("ERROR")

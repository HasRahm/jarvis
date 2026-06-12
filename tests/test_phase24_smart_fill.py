"""Phase 24 — smart_fill routing + dispatcher registration.

All graph/vision/input dependencies are monkeypatched: no desktop needed.
"""
import os
import sys
import json
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import tools.virtual_input as vi


@pytest.fixture
def fake_cache(tmp_path, monkeypatch):
    """Point desktop_ui_tree's cache at a temp file and stub the tree walk."""
    import tools.desktop_ui_tree as dut
    cache = tmp_path / "desktop_ui_cache.json"
    monkeypatch.setattr(dut, "CACHE_FILE", str(cache))
    monkeypatch.setattr(dut, "desktop_get_ui_tree",
                        lambda max_depth=8, search_query=None: "Active Window: stub")
    def write(elements):
        cache.write_text(json.dumps(elements), encoding="utf-8")
    return write


@pytest.fixture(autouse=True)
def no_view(monkeypatch):
    monkeypatch.setenv("JARVIS_AGENT_VIEW", "0")
    monkeypatch.setenv("JARVIS_AGENT_CURSOR", "0")


EDIT_EL = {"index": 0, "name": "Search", "auto_id": "searchBox", "role": "Edit",
           "x": 100, "y": 50, "w": 200, "h": 30, "is_enabled": True}


class TestSmartFillRouting:
    def test_graph_path_with_virtual_input(self, fake_cache, monkeypatch):
        fake_cache([EDIT_EL])
        calls = {}
        monkeypatch.setattr(vi, "virtual_interact",
                            lambda el, a, t, s=None: calls.setdefault("v", (el, a, t)) or (True, "ValuePattern.SetValue", False))
        monkeypatch.setattr("tools.hybrid_cursor._check_text_on_screen",
                            lambda text, min_conf=40: (True, "found"))
        out = vi.smart_fill("search box", "hello world")
        assert "SUCCESS" in out
        assert "Graph locate" in out and "Search" in out
        assert calls["v"][0]["name"] == "Search"
        assert calls["v"][1] == "type" and calls["v"][2] == "hello world"
        assert "Vision fallback" not in out

    def test_physical_fallback_when_virtual_fails(self, fake_cache, monkeypatch):
        fake_cache([EDIT_EL])
        monkeypatch.setattr(vi, "virtual_interact",
                            lambda el, a, t, s=None: (False, "no patterns", True))
        clicked, typed = [], []
        monkeypatch.setattr("tools.desktop_automation.desktop_smooth_click",
                            lambda x, y, duration=0.4: clicked.append((x, y)) or "clicked")
        monkeypatch.setattr("tools.desktop_automation.desktop_type_text",
                            lambda t: typed.append(t) or "typed")
        monkeypatch.setattr("tools.hybrid_cursor._check_text_on_screen",
                            lambda text, min_conf=40: (False, "n/a"))
        out = vi.smart_fill("search box", "abc")
        assert "SUCCESS" in out
        assert clicked == [(200, 65)]   # element center
        assert typed == ["abc"]
        assert "Physical fallback" in out

    def test_vision_fallback_when_no_graph_match(self, fake_cache, monkeypatch):
        fake_cache([{"index": 0, "name": "Cancel", "auto_id": "", "role": "Button",
                     "x": 0, "y": 0, "w": 10, "h": 10, "is_enabled": True}])
        seen = {}
        def fake_visual_click(desc, hint=None):
            seen["desc"] = desc
            return "[VisualClick] SUCCESS\n..."
        monkeypatch.setattr("tools.visual_click.visual_click", fake_visual_click)
        monkeypatch.setattr("tools.desktop_automation.desktop_type_text",
                            lambda t: seen.setdefault("typed", t) or "typed")
        monkeypatch.setattr("tools.hybrid_cursor._check_text_on_screen",
                            lambda text, min_conf=40: (False, "n/a"))
        out = vi.smart_fill("email address field", "a@b.c")
        assert "SUCCESS" in out
        assert "Vision fallback" in out
        assert seen["desc"] == "email address field"
        assert seen["typed"] == "a@b.c"

    def test_fails_cleanly_when_everything_misses(self, fake_cache, monkeypatch):
        fake_cache([])
        monkeypatch.setattr("tools.visual_click.visual_click",
                            lambda desc, hint=None: "[VisualClick] FAILED: nope")
        out = vi.smart_fill("ghost field", "x")
        assert out.startswith("[SmartFill] FAILED")

    def test_requires_description(self):
        assert vi.smart_fill("", "x").startswith("ERROR")

    def test_requires_text(self):
        assert vi.smart_fill("field", None).startswith("ERROR")


class TestDispatcherRegistration:
    def test_new_tools_registered(self):
        from tools.dispatcher import TOOL_DEFINITIONS
        names = [t["function"]["name"] for t in TOOL_DEFINITIONS]
        for tool in ("smart_fill", "agent_view", "agent_cursor"):
            assert tool in names, f"{tool} missing from TOOL_DEFINITIONS"

    def test_smart_fill_schema(self):
        from tools.dispatcher import TOOL_DEFINITIONS
        t = next(t for t in TOOL_DEFINITIONS if t["function"]["name"] == "smart_fill")
        props = t["function"]["parameters"]["properties"]
        assert "field_description" in props and "text" in props
        assert t["function"]["parameters"]["required"] == ["field_description", "text"]

    def test_slash_commands_added(self):
        from core.cli.app import SLASH_COMMANDS
        cmds = [c[0] for c in SLASH_COMMANDS]
        assert "/agentview" in cmds and "/cursor" in cmds

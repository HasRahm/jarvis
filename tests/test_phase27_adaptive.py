"""
Phase 27 — Adaptive Reasoning, Temperature Control & Live Knowledge

CI-safe tests (no real network, no GUI launches):
- open_app + web_search registered in TOOL_DEFINITIONS and _CORTEX_EXEMPT
- _get_temperature: default, env override, reasoning-model value
- open_app decision tree with monkeypatched launcher/browser
- web_search DuckDuckGo parsing with monkeypatched httpx; graceful failure
"""

import os
import sys
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ── Tool registration ────────────────────────────────────────────────────────

def test_open_app_and_web_search_registered():
    from tools.dispatcher import TOOL_DEFINITIONS
    names = {t["function"]["name"] for t in TOOL_DEFINITIONS}
    assert "open_app" in names
    assert "web_search" in names


def test_open_app_web_search_in_cortex_exempt():
    import inspect
    import tools.dispatcher as disp
    src = inspect.getsource(disp.dispatch)
    assert '"open_app"' in src
    assert '"web_search"' in src


# ── Temperature ──────────────────────────────────────────────────────────────

def test_temperature_default(monkeypatch):
    monkeypatch.delenv("JARVIS_TEMPERATURE", raising=False)
    from core.system.llm_adapter import _get_temperature
    assert _get_temperature("gemma4:31b-cloud") == 0.6


def test_temperature_env_override(monkeypatch):
    monkeypatch.setenv("JARVIS_TEMPERATURE", "0.85")
    from core.system.llm_adapter import _get_temperature
    assert _get_temperature("gemma4:31b-cloud") == 0.85


def test_temperature_reasoning_model(monkeypatch):
    monkeypatch.delenv("JARVIS_TEMPERATURE", raising=False)
    from core.system.llm_adapter import _get_temperature
    assert _get_temperature("nvidia/nemotron-3-ultra-550b-a55b") == 1.0


def test_temperature_env_beats_reasoning_model(monkeypatch):
    monkeypatch.setenv("JARVIS_TEMPERATURE", "0.4")
    from core.system.llm_adapter import _get_temperature
    assert _get_temperature("nvidia/nemotron-3-ultra-550b-a55b") == 0.4


def test_temperature_invalid_env_falls_back(monkeypatch):
    monkeypatch.setenv("JARVIS_TEMPERATURE", "not-a-number")
    from core.system.llm_adapter import _get_temperature
    assert _get_temperature("gemma4:31b-cloud") == 0.6


# ── open_app ─────────────────────────────────────────────────────────────────

def test_open_app_empty_name():
    from tools.open_app import open_app
    assert "no app_name" in open_app("").lower()


def test_open_app_web_known_app(monkeypatch):
    import tools.open_app as oa
    opened = {}
    monkeypatch.setattr(oa.os, "startfile", lambda url: opened.setdefault("url", url), raising=False)
    monkeypatch.setattr(oa.sys, "platform", "win32")
    result = oa.open_app("notion", prefer="web")
    assert "notion.so" in opened["url"]
    assert "browser" in result.lower()


def test_open_app_web_unknown_app_uses_search(monkeypatch):
    import tools.open_app as oa
    opened = {}
    monkeypatch.setattr(oa.os, "startfile", lambda url: opened.setdefault("url", url), raising=False)
    monkeypatch.setattr(oa.sys, "platform", "win32")
    result = oa.open_app("some-obscure-app-xyz", prefer="web")
    assert "duckduckgo.com" in opened["url"]
    assert "web search" in result.lower()


def test_open_app_focuses_existing_window(monkeypatch):
    import tools.open_app as oa
    monkeypatch.setattr(oa, "_window_open", lambda name: True)
    import tools.desktop_automation as da
    monkeypatch.setattr(da, "desktop_focus_window", lambda q: f"focused {q}")
    result = oa.open_app("chrome")
    assert "already open" in result.lower()


def test_open_app_native_then_web_fallback(monkeypatch):
    """Unknown native app, not open -> falls through to web fallback in auto mode."""
    import tools.open_app as oa
    monkeypatch.setattr(oa, "_window_open", lambda name: False)
    monkeypatch.setattr(oa, "_launch_native", lambda name: (False, "no native launcher known"))
    opened = {}
    monkeypatch.setattr(oa.os, "startfile", lambda url: opened.setdefault("url", url), raising=False)
    monkeypatch.setattr(oa.sys, "platform", "win32")
    result = oa.open_app("figma", prefer="auto")
    assert "figma.com" in opened["url"]


def test_open_app_native_only_no_web(monkeypatch):
    import tools.open_app as oa
    monkeypatch.setattr(oa, "_window_open", lambda name: False)
    monkeypatch.setattr(oa, "_launch_native", lambda name: (False, "not found"))
    result = oa.open_app("figma", prefer="native")
    assert "web fallback disabled" in result.lower()


# ── web_search ───────────────────────────────────────────────────────────────

_FAKE_DDG_HTML = """
<html><body>
<div class="result">
  <a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Fclaude">Claude model news</a>
  <a class="result__snippet">The latest Claude model was announced in 2026.</a>
</div>
<div class="result">
  <a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.org%2Fai">AI updates</a>
  <a class="result__snippet">Roundup of recent AI releases.</a>
</div>
</body></html>
"""


class _FakeResp:
    def __init__(self, text):
        self.text = text
    def raise_for_status(self):
        pass


def test_web_search_empty_query():
    from tools.web_search import web_search
    assert "empty query" in web_search("").lower()


def test_web_search_duckduckgo_parsing(monkeypatch):
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    monkeypatch.delenv("BRAVE_API_KEY", raising=False)
    import tools.web_search as ws
    monkeypatch.setattr(ws.httpx, "get", lambda *a, **k: _FakeResp(_FAKE_DDG_HTML))
    result = ws.web_search("latest claude model", max_results=5)
    assert "Claude model news" in result
    assert "https://example.com/claude" in result
    assert "announced in 2026" in result


def test_web_search_graceful_failure(monkeypatch):
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    monkeypatch.delenv("BRAVE_API_KEY", raising=False)
    import tools.web_search as ws

    def boom(*a, **k):
        raise RuntimeError("network down")

    monkeypatch.setattr(ws.httpx, "get", boom)
    result = ws.web_search("anything")
    assert result.startswith("[web_search]")
    assert "unavailable" in result.lower()


def test_web_search_no_results(monkeypatch):
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    monkeypatch.delenv("BRAVE_API_KEY", raising=False)
    import tools.web_search as ws
    monkeypatch.setattr(ws.httpx, "get", lambda *a, **k: _FakeResp("<html><body></body></html>"))
    result = ws.web_search("zzz")
    assert "no results" in result.lower()

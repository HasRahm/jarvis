"""Phase 42 — model-agnostic fallback + window-scoped grounding. CI-safe."""
import os
import sys
import unittest.mock as mock

os.environ.setdefault("JARVIS_CI", "true")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

import core.system.llm_adapter as la
import tools.windows as windows
from agents.model_router import get_provider


class TestFallback:
    def test_free_openrouter_in_chain_routes(self):
        # The free safety-net model must route through OpenRouter.
        assert get_provider("openrouter/qwen/qwen3-next-80b-a3b-instruct:free") == "openrouter"

    def test_all_models_fail_returns_message_not_raise(self, monkeypatch):
        # Every provider path fails (billing/rate/offline) — call_llm must NOT raise.
        for k in ("OPENROUTER_API_KEY", "ANTHROPIC_API_KEY", "OPENAI_API_KEY",
                  "GEMINI_API_KEY", "NVIDIA_API_KEY"):
            monkeypatch.setenv(k, "x")
        with mock.patch.object(la, "is_ollama_available", return_value=False), \
             mock.patch.object(la, "_call_openai_compatible_api", side_effect=Exception("429")), \
             mock.patch.object(la, "_call_anthropic_api", side_effect=Exception("billing")):
            res = la.call_llm([{"role": "user", "content": "hi"}], model="gpt-oss:120b")
        assert isinstance(res, dict)
        assert res.get("role") == "assistant"
        assert res.get("content", "").startswith("⚠")


class TestForegroundWindow:
    def test_ci_returns_none(self):
        assert windows.get_foreground_window() is None

    def test_never_raises(self, monkeypatch):
        # Even outside CI, a ctypes failure must degrade to None, not raise.
        monkeypatch.delenv("JARVIS_CI", raising=False)
        with mock.patch.object(windows, "get_window_stack", side_effect=Exception("boom")):
            # GetForegroundWindow may or may not exist in the test env; either way no raise.
            try:
                out = windows.get_foreground_window()
            except Exception as e:
                pytest.fail(f"get_foreground_window raised: {e}")
            assert out is None or isinstance(out, dict)


class TestVisualClickNoCrash:
    def test_returns_string_without_window_hint(self):
        # In CI (no display) it returns a FAILED trace string — but never raises, and the
        # window_hint=None path (foreground auto-scope) must be reachable without NameError.
        from tools.visual_click import visual_click
        out = visual_click("the search box", window_hint=None)
        assert isinstance(out, str)

    def test_empty_description_guarded(self):
        from tools.visual_click import visual_click
        assert "ERROR" in visual_click("")

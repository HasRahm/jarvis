"""
Phase 28a — Cognitive Layer: Plan, Clarify, Verify, Recover

CI-safe tests (mock call_llm / screen primitives; no real LLM, screen, or GUI):
- planner.is_complex gating + plan_task skip/produce
- clarifier critical vs PROCEED parsing, fail-open
- recovery_navigator known routes + unknown fallback
- verification_loop dict API with mocked _verify_outcome
- verify_outcome + get_unstuck registered and cortex-exempt
"""

import os
import sys
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ── Planner ──────────────────────────────────────────────────────────────────

def test_is_complex_trivial_false():
    from core.orchestrator.planner import is_complex
    assert is_complex("run dir") is False
    assert is_complex("") is False


def test_is_complex_multistep_true():
    from core.orchestrator.planner import is_complex
    assert is_complex("open figma, search community, and download the kit") is True


def test_is_complex_keyword_true():
    from core.orchestrator.planner import is_complex
    assert is_complex("open chrome") is True


def test_plan_task_trivial_returns_empty():
    from core.orchestrator.planner import plan_task
    assert plan_task("run dir") == ""


def test_plan_task_complex_ci_returns_plan(monkeypatch):
    monkeypatch.setenv("JARVIS_CI", "true")
    from core.orchestrator.planner import plan_task
    plan = plan_task("open figma and search for a dashboard kit")
    assert plan and "GOAL" in plan


# ── Clarifier ────────────────────────────────────────────────────────────────

def test_clarifier_ci_proceeds(monkeypatch):
    monkeypatch.setenv("JARVIS_CI", "true")
    from core.orchestrator.clarifier import check_ambiguity
    assert check_ambiguity("delete everything")["proceed"] is True


def test_clarifier_proceed_response(monkeypatch):
    monkeypatch.delenv("JARVIS_CI", raising=False)
    import core.orchestrator.clarifier as clar
    monkeypatch.setattr(clar, "call_llm", lambda **k: {"content": "PROCEED"}, raising=False)
    # call_llm is imported lazily inside the function, so patch at source module too
    import core.system.llm_adapter as la
    monkeypatch.setattr(la, "call_llm", lambda **k: {"content": "PROCEED"})
    assert clar.check_ambiguity("write hello to a file")["proceed"] is True


def test_clarifier_critical_questions(monkeypatch):
    monkeypatch.delenv("JARVIS_CI", raising=False)
    import core.system.llm_adapter as la
    canned = "Q: Which account should I delete from?\n- personal\n- work"
    monkeypatch.setattr(la, "call_llm", lambda **k: {"content": canned})
    from core.orchestrator.clarifier import check_ambiguity
    result = check_ambiguity("delete my account")
    assert result["proceed"] is False
    assert len(result["questions"]) == 1
    assert "account" in result["questions"][0]["question"].lower()
    assert result["questions"][0]["options"] == ["personal", "work"]


def test_clarifier_fails_open_on_error(monkeypatch):
    monkeypatch.delenv("JARVIS_CI", raising=False)
    import core.system.llm_adapter as la

    def boom(**k):
        raise RuntimeError("model down")

    monkeypatch.setattr(la, "call_llm", boom)
    from core.orchestrator.clarifier import check_ambiguity
    assert check_ambiguity("do the thing")["proceed"] is True


# ── Recovery Navigator ───────────────────────────────────────────────────────

def test_recovery_known_dialog_route():
    from core.orchestrator.recovery_navigator import get_unstuck
    plan = get_unstuck("close the editor", "an unexpected dialog appeared")
    assert "Escape" in plan
    assert "dialog" in plan.lower()


def test_recovery_element_not_found_route():
    from core.orchestrator.recovery_navigator import get_unstuck
    plan = get_unstuck("click Save", "button not found on screen")
    assert "scroll" in plan.lower()


def test_recovery_unknown_ci_fallback(monkeypatch):
    monkeypatch.setenv("JARVIS_CI", "true")
    from core.orchestrator.recovery_navigator import get_unstuck
    plan = get_unstuck("do something", "weird unexplained state")
    assert "verify_outcome" in plan


def test_recovery_unknown_uses_llm(monkeypatch):
    monkeypatch.delenv("JARVIS_CI", raising=False)
    import core.system.llm_adapter as la
    monkeypatch.setattr(la, "call_llm", lambda **k: {"content": "1. do X\n2. do Y"})
    import core.orchestrator.recovery_navigator as rn
    monkeypatch.setattr(rn, "get_unstuck", rn.get_unstuck)  # ensure module loaded
    # Patch window stack import path used inside
    import tools.windows as win
    monkeypatch.setattr(win, "get_window_stack", lambda: [{"title": "Test"}])
    plan = rn.get_unstuck("goal", "totally novel failure mode xyz")
    assert "do X" in plan


# ── Verification Loop ────────────────────────────────────────────────────────

def test_verify_outcome_success(monkeypatch):
    import tools.hybrid_cursor as hc
    monkeypatch.setattr(hc, "_verify_outcome", lambda expected_text=None, timeout=3.0: (True, "Screen changed"))
    from core.orchestrator.verification_loop import verify_outcome
    result = verify_outcome()
    assert result["success"] is True
    assert "changed" in result["message"].lower()


def test_verify_outcome_failure(monkeypatch):
    import tools.hybrid_cursor as hc
    monkeypatch.setattr(hc, "_verify_outcome", lambda expected_text=None, timeout=3.0: (False, "Screen did not change"))
    from core.orchestrator.verification_loop import verify_outcome
    result = verify_outcome(expected_text="Saved")
    assert result["success"] is False


def test_verify_outcome_never_raises(monkeypatch):
    import tools.hybrid_cursor as hc

    def boom(**k):
        raise RuntimeError("screen grab failed")

    monkeypatch.setattr(hc, "_verify_outcome", boom)
    from core.orchestrator.verification_loop import verify_outcome
    result = verify_outcome()
    assert result["success"] is False
    assert "error" in result["message"].lower()


# ── Tool registration ────────────────────────────────────────────────────────

def test_cognition_tools_registered():
    from tools.dispatcher import TOOL_DEFINITIONS
    names = {t["function"]["name"] for t in TOOL_DEFINITIONS}
    assert "verify_outcome" in names
    assert "get_unstuck" in names


def test_cognition_tools_cortex_exempt():
    import inspect
    import tools.dispatcher as disp
    src = inspect.getsource(disp.dispatch)
    assert '"verify_outcome"' in src
    assert '"get_unstuck"' in src

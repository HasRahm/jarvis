"""Tests for the canonical Jarvis system prompt (core/jarvis_prompt.py).

CI-safe: pure string assertions, no model calls.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.jarvis_prompt import base_prompt, ORCHESTRATOR_ADDON


class TestBasePrompt:
    def test_returns_str(self):
        assert isinstance(base_prompt(), str)
        assert len(base_prompt()) > 500

    def test_is_jarvis_not_a_named_product(self):
        p = base_prompt().lower()
        assert "jarvis" in p
        # Identity must not claim to be Claude/Anthropic or any named model.
        for forbidden in ("claude", "anthropic", "gpt-", "gemini-", "i am chatgpt"):
            assert forbidden not in p, f"prompt should not assert identity '{forbidden}'"

    def test_has_orientation_sections(self):
        p = base_prompt()
        for tag in ("<identity>", "<tools>", "<worked_example>", "<what_you_receive>",
                    "<acting>", "<honesty>", "<refusal_handling>", "<instruction_boundary>"):
            assert tag in p, f"missing section {tag}"

    def test_injects_date_and_output_dir(self):
        p = base_prompt(date="Tuesday, June 09, 2026", output_dir="C:/tmp/proj")
        assert "Tuesday, June 09, 2026" in p
        assert "C:/tmp/proj" in p
        # placeholders fully substituted
        assert "{{DATE}}" not in p
        assert "{{OUTPUT_DIR}}" not in p

    def test_defaults_when_args_omitted(self):
        p = base_prompt()
        assert "{{DATE}}" not in p
        assert "{{OUTPUT_DIR}}" not in p

    def test_token_lean(self):
        # Orientation layer, not a 10k-word essay. A few thousand chars is the target.
        assert len(base_prompt()) < 9000, "base prompt drifting toward bloat"

    def test_documents_tool_groups_and_doctrine(self):
        p = base_prompt()
        # names the real tool groups it teaches the model to choose between
        for name in ("brain_query", "open_app", "element_graph", "verify_outcome",
                     "get_unstuck", "web_search", "run_backend_agent"):
            assert name in p, f"tools doctrine should reference {name}"

    def test_orchestrator_addon_has_office_meeting(self):
        # The graph renderers parse <office_meeting>; the build path must still instruct it.
        assert "<office_meeting>" in ORCHESTRATOR_ADDON
        assert "office_meeting" not in base_prompt(), "office-meeting stays orchestrator-only"

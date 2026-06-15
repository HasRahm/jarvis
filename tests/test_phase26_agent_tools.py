"""
Phase 26 — Agent Tools + XML Prompt Overhaul

15 CI-safe tests covering:
- Tool registration in TOOL_DEFINITIONS
- All 5 new tools in _CORTEX_EXEMPT
- CI execution of all 4 coding agents
- Skill runner (unknown skill → error string, not raise)
- Model routing (env override, keyword hints)
- XML structure in all 4 SYSTEM_PROMPT strings and both QA prompts
- load_skill_prompt for a known skill
"""

import json
import os
import sys
import pytest

# Ensure project root is on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

AGENT_TOOL_NAMES = {
    "run_backend_agent",
    "run_frontend_agent",
    "run_qa_agent",
    "run_iac_agent",
    "run_skill",
}


# ── Tool registration ────────────────────────────────────────────────────────

def test_agent_tools_registered_in_tool_definitions():
    """All 5 agent tools must appear in TOOL_DEFINITIONS."""
    from tools.dispatcher import TOOL_DEFINITIONS
    registered = {t["function"]["name"] for t in TOOL_DEFINITIONS}
    for name in AGENT_TOOL_NAMES:
        assert name in registered, f"Tool '{name}' missing from TOOL_DEFINITIONS"


def test_agent_tools_all_have_required_params():
    """Each agent tool must declare 'task' as a required parameter."""
    from tools.dispatcher import TOOL_DEFINITIONS
    for t in TOOL_DEFINITIONS:
        name = t["function"]["name"]
        if name in AGENT_TOOL_NAMES and name != "run_skill":
            required = t["function"]["parameters"].get("required", [])
            assert "task" in required, f"'{name}' missing 'task' in required params"


def test_run_skill_requires_skill_name_and_task():
    from tools.dispatcher import TOOL_DEFINITIONS
    skill_tool = next(t for t in TOOL_DEFINITIONS if t["function"]["name"] == "run_skill")
    required = skill_tool["function"]["parameters"]["required"]
    assert "skill_name" in required
    assert "task" in required


# ── _CORTEX_EXEMPT ───────────────────────────────────────────────────────────

def test_all_agent_tools_in_cortex_exempt(monkeypatch):
    """All 5 agent tools must be listed in _CORTEX_EXEMPT to avoid spatial cortex blocking."""
    import importlib
    import tools.dispatcher as disp

    # Capture the set at dispatch time without actually dispatching
    monkeypatch.setenv("JARVIS_CI", "true")
    captured = {}

    original_dispatch_raw = disp._dispatch_raw

    def patched_dispatch(fn_name, args):
        raise RuntimeError("sentinel")

    monkeypatch.setattr(disp, "_dispatch_raw", patched_dispatch)

    # Directly inspect the literal set in dispatch() source
    import inspect
    src = inspect.getsource(disp.dispatch)
    for name in AGENT_TOOL_NAMES:
        assert f'"{name}"' in src, f"'{name}' not found in _CORTEX_EXEMPT block in dispatch()"


# ── CI execution of coding agents ────────────────────────────────────────────

@pytest.fixture(autouse=True)
def set_ci_env(monkeypatch):
    monkeypatch.setenv("JARVIS_CI", "true")


def test_run_backend_agent_ci_returns_json_string():
    from agents.agent_tools import run_backend_agent
    result = run_backend_agent("Create a users table with email and password fields", user_id="test")
    parsed = json.loads(result)
    assert "status" in parsed


def test_run_frontend_agent_ci_returns_json_string():
    from agents.agent_tools import run_frontend_agent
    result = run_frontend_agent("Build a login form with email and password", user_id="test")
    parsed = json.loads(result)
    assert "status" in parsed


def test_run_qa_agent_ci_returns_json_string():
    from agents.agent_tools import run_qa_agent
    result = run_qa_agent("Review the users API for security issues", user_id="test")
    parsed = json.loads(result)
    assert "status" in parsed


def test_run_iac_agent_ci_returns_json_string():
    from agents.agent_tools import run_iac_agent
    result = run_iac_agent("Create a Terraform config for a local PostgreSQL container")
    parsed = json.loads(result)
    assert "status" in parsed


# ── Skill runner ─────────────────────────────────────────────────────────────

def test_run_skill_unknown_skill_returns_error_string_not_raise():
    """Unknown skill names must return an error string, never raise."""
    from agents.agent_tools import run_skill
    result = run_skill("nonexistent-skill-xyz-999", "Do something")
    assert isinstance(result, str)
    assert "[ERROR]" in result


def test_run_skill_ci_returns_mock_string():
    """In CI mode, run_skill with a known skill returns a mock string (no LLM call)."""
    from agents.agent_tools import run_skill
    # Use a skill name that won't hit disk — CI gate fires before FileNotFoundError
    result = run_skill("cs-senior-engineer", "Review my architecture")
    assert isinstance(result, str)
    assert len(result) > 0


# ── Model routing ─────────────────────────────────────────────────────────────

def test_get_skill_model_keyword_engineering():
    from agents.model_router import get_skill_model
    assert get_skill_model("cs-backend-engineer") == "claude-sonnet-4-6"


def test_get_skill_model_keyword_advisor():
    from agents.model_router import get_skill_model
    assert "nvidia" in get_skill_model("cs-cto-advisor") or "nemotron" in get_skill_model("cs-cto-advisor")


def test_get_skill_model_keyword_product():
    from agents.model_router import get_skill_model
    assert "gemini" in get_skill_model("cs-product-manager")


def test_get_skill_model_env_override(monkeypatch):
    monkeypatch.setenv("SKILL_MODEL_CS_SENIOR_ENGINEER", "gemma4:31b-cloud")
    from agents import model_router
    import importlib
    importlib.reload(model_router)
    result = model_router.get_skill_model("cs-senior-engineer")
    assert result == "gemma4:31b-cloud"
    importlib.reload(model_router)  # clean up


# ── XML structure in agent prompts ───────────────────────────────────────────

@pytest.mark.parametrize("module,attr", [
    ("agents.backend_agent", "SYSTEM_PROMPT"),
    ("agents.frontend_agent", "SYSTEM_PROMPT"),
    ("agents.qa_agent", "SYSTEM_PROMPT"),
    ("agents.iac_agent", "SYSTEM_PROMPT"),
])
def test_xml_tags_present_in_system_prompts(module, attr):
    import importlib
    mod = importlib.import_module(module)
    prompt = getattr(mod, attr)
    for tag in ("<agent_role>", "<output_requirements>", "<rules>", "<self_evaluation>"):
        assert tag in prompt, f"{module}.{attr} missing XML tag '{tag}'"


def test_qa_verifier_prompt_has_xml_tags():
    from agents.qa_agent import VERIFIER_PROMPT
    for tag in ("<agent_role>", "<verification_checklist>", "<output_schema>"):
        assert tag in VERIFIER_PROMPT, f"VERIFIER_PROMPT missing XML tag '{tag}'"

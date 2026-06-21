"""Phase 37 — Skills-as-Agents. CI-safe (no network; JARVIS_CI=true mocks model calls).

These tests use whatever skills are present locally (they do not require the external clone),
so they pass on any machine.
"""
import os
import json
import sys

os.environ.setdefault("JARVIS_CI", "true")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

from core.system.skills import SkillsEngine
from agents.skill_agent import SkillAgent
from agents.agent_tools import select_skill_for, run_skill_agent, run_engineering_agent
from tools.dispatcher import TOOL_DEFINITIONS


def _any_skill_name():
    skills = SkillsEngine().skills
    return skills[0]["name"] if skills else None


class TestSkillResolution:
    def test_skills_load(self):
        assert len(SkillsEngine().skills) > 0

    def test_no_dot_dir_skills(self):
        """Tool-converted duplicate copies under .gemini/.claude/.git must be skipped."""
        for s in SkillsEngine().skills:
            norm = s["path"].replace("\\", "/")
            assert "/.gemini/" not in norm
            assert "/.claude/" not in norm
            assert "/.git/" not in norm

    def test_get_skill_content_nonempty(self):
        name = _any_skill_name()
        if not name:
            pytest.skip("no skills available")
        assert len(SkillsEngine().get_skill_content(name)) > 0


class TestSkillAgent:
    def test_role_is_windows_safe(self):
        name = _any_skill_name()
        if not name:
            pytest.skip("no skills available")
        agent = SkillAgent(name)
        assert ":" not in agent.role
        assert agent.role.startswith("skill_")

    def test_run_returns_success_in_ci(self):
        name = _any_skill_name()
        if not name:
            pytest.skip("no skills available")
        res = SkillAgent(name).run("perform the task")
        assert res["status"] == "success"
        assert res["skill"] == name


class TestRouting:
    def test_select_skill_trivial_returns_none(self):
        # Nonsense tokens should match nothing → fall back to base agent.
        assert select_skill_for("zzqqxx wuglemorp frobnak") is None

    def test_select_skill_matches_relevant(self):
        # A clearly engineering task should match *some* skill when skills are present.
        if not SkillsEngine().skills:
            pytest.skip("no skills available")
        assert select_skill_for("design a database migration and api endpoint") is not None


class TestTools:
    def test_both_tools_registered(self):
        names = [t["function"]["name"] for t in TOOL_DEFINITIONS]
        assert "run_skill_agent" in names
        assert "run_engineering_agent" in names

    def test_run_skill_agent_ci(self):
        name = _any_skill_name()
        if not name:
            pytest.skip("no skills available")
        out = run_skill_agent(name, "do the task")
        assert json.loads(out)["status"] == "success"

    def test_run_engineering_agent_ci(self):
        out = run_engineering_agent("build a rest api with database migrations")
        assert json.loads(out)["status"] in ("success", "error")

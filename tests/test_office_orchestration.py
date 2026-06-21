"""Phase 41 — office-hierarchy orchestration. CI-safe (no network / LLM)."""
import os
import sys

os.environ.setdefault("JARVIS_CI", "true")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

from agents.model_router import get_model, get_provider, get_fallbacks, _DEFAULTS, _FALLBACKS
from core.orchestrator.task_classifier import classify, _heuristic, VALID_DOMAINS
from core.orchestrator.intent_router import route
from core.orchestrator.architect import produce_spec, _finalize_assignments
from core.orchestrator.task_parser import parse_task
from core.orchestrator.dag import _get_agent_instance


class TestRoster:
    def test_kimi_orchestrator(self):
        assert get_model("orchestrator") == "openrouter/moonshotai/kimi-k2.6"
        assert get_provider(get_model("orchestrator")) == "openrouter"

    def test_new_roles_resolve(self):
        for role in ("database", "research", "desktop_automation", "system_health"):
            assert get_model(role)

    def test_desktop_roles_are_local(self):
        assert get_model("desktop_automation") == "gemma4:31b-cloud"
        assert get_model("system_health") == "gemma4:31b-cloud"

    def test_every_chain_ends_local(self):
        for role, chain in _FALLBACKS.items():
            assert chain[-1] == "gemma4:31b-cloud", role

    def test_openrouter_models_route_to_openrouter(self):
        allm = set(_DEFAULTS.values()) | {m for ch in _FALLBACKS.values() for m in ch}
        for m in allm:
            if m.startswith("openrouter/"):
                assert get_provider(m) == "openrouter", m


class TestClassifier:
    def test_classify_returns_valid_domain(self):
        for task in ("open Spotify and play X", "build a todo app", "research laptops"):
            assert classify(task)["domain"] in VALID_DOMAINS

    def test_heuristic_no_substring_false_positive(self):
        # 'api' inside 'capital' must NOT classify as BACKEND_BUILD.
        assert _heuristic("what is the capital of France")["domain"] != "BACKEND_BUILD"


class TestRouter:
    @pytest.mark.parametrize("task,path", [
        ("open Spotify and play a song", "desktop"),
        ("clean up my disk", "desktop"),
        ("build a todo web app", "build"),
        ("design a schema migration for orders", "build"),
        ("research the best laptops 2026", "research"),
        ("what is the capital of France", "chat"),
    ])
    def test_route_paths(self, task, path):
        assert route(task)["path"] == path


class TestArchitectBrief:
    def test_assignments_carry_models(self):
        spec = produce_spec("build a todo app with user accounts")
        asn = spec["assignments"]
        assert asn and all("model" in a and "agent" in a for a in asn)
        # every assignment's model is the cost-optimized roster model for its role
        for a in asn:
            assert a["model"] == get_model(a["agent"])

    def test_finalize_synthesizes_when_missing(self):
        spec = {"data_model": [{"table": "x", "columns": ["id"]}], "api_contract": [{"method": "GET", "path": "/x"}]}
        asn = _finalize_assignments(spec)
        agents = [a["agent"] for a in asn]
        assert "database" in agents and "backend" in agents and "qa" in agents


class TestDagIntegration:
    def test_parse_task_derives_from_assignments(self):
        spec = produce_spec("build a todo app")
        subs = parse_task("build a todo app", spec=spec)
        ids = {s["id"] for s in subs}
        # qa depends on backend + frontend
        qa = next(s for s in subs if s["agent"] == "qa")
        assert all(d in ids for d in qa["depends_on"])

    def test_database_role_uses_backend_agent(self):
        a = _get_agent_instance("database")
        assert type(a).__name__ == "BackendAgent"
        assert a.role == "database"

    def test_research_role_resolves(self):
        a = _get_agent_instance("research")
        assert type(a).__name__ in ("SkillAgent", "BackendAgent")

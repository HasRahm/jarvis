"""Phase 38 — per-agent OpenRouter model selection. CI-safe (no network)."""
import os
import sys

os.environ.setdefault("JARVIS_CI", "true")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

from agents import model_router as mr


@pytest.fixture(autouse=True)
def _isolate_config(tmp_path, monkeypatch):
    """Point the override config at a temp file so tests never touch the real one."""
    cfg = tmp_path / "agent_models.json"
    monkeypatch.setattr(mr, "_AGENT_MODELS_PATH", str(cfg))
    monkeypatch.setattr(mr, "_CONFIG_DIR", str(tmp_path))
    monkeypatch.setattr(mr, "_overrides_mtime", -1.0)
    monkeypatch.setattr(mr, "_overrides_cache", {})
    yield


class TestNormalization:
    def test_vendor_slug_becomes_openrouter(self):
        assert mr.normalize_model("anthropic/claude-opus-4.8") == "openrouter/anthropic/claude-opus-4.8"

    def test_bare_native_name_unchanged(self):
        assert mr.normalize_model("gemini-3.5-flash") == "gemini-3.5-flash"

    def test_already_openrouter_unchanged(self):
        assert mr.normalize_model("openrouter/google/gemini-3.5-flash") == "openrouter/google/gemini-3.5-flash"


class TestPersistence:
    def test_set_and_get(self):
        mr.set_agent_model("qa", "anthropic/claude-opus-4.8")
        assert mr.get_model("qa") == "openrouter/anthropic/claude-opus-4.8"
        from agents.model_router import get_provider
        assert get_provider(mr.get_model("qa")) == "openrouter"

    def test_native_stays_native(self):
        mr.set_agent_model("frontend", "gemini-3.5-flash")
        assert mr.get_model("frontend") == "gemini-3.5-flash"

    def test_env_wins_over_config(self, monkeypatch):
        mr.set_agent_model("qa", "anthropic/claude-opus-4.8")
        monkeypatch.setenv("AGENT_MODEL_QA", "gpt-5.4")
        assert mr.get_model("qa") == "gpt-5.4"

    def test_reset_reverts_to_default(self):
        mr.set_agent_model("qa", "anthropic/claude-opus-4.8")
        assert mr.reset_agent_model("qa") is True
        assert mr.get_model("qa") == mr._DEFAULTS["qa"]

    def test_reset_absent_returns_false(self):
        assert mr.reset_agent_model("backend") is False

    def test_skill_override(self):
        mr.set_agent_model("skill:rag-architect", "openai/gpt-5.4")
        assert mr.get_skill_model("rag-architect") == "openrouter/openai/gpt-5.4"


class TestGetAllAgentModels:
    def test_reports_sources(self):
        mr.set_agent_model("qa", "anthropic/claude-opus-4.8")
        data = mr.get_all_agent_models()
        assert data["qa"]["source"] == "config"
        assert data["backend"]["source"] == "default"


class TestCatalogModuleImports:
    def test_catalog_importable(self):
        from core.system import openrouter_catalog
        assert hasattr(openrouter_catalog, "list_models")

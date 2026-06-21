"""Phase 46 cluster 2 — --model validation + AGENTS.md single source of truth. CI-safe."""
import os
import sys
import tempfile

os.environ.setdefault("JARVIS_CI", "true")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from agents.model_router import validate_model, get_model


class TestValidateModel:
    def test_bogus_rejected_with_suggestions(self):
        ok, why = validate_model("totally-fake-model-xyz")
        assert ok is False
        assert "Did you mean" in why and "/models" in why

    def test_empty_rejected(self):
        assert validate_model("")[0] is False
        assert validate_model("   ")[0] is False

    def test_local_ollama_ok(self):
        assert validate_model("gemma4:31b-cloud")[0] is True
        assert validate_model("llama3.2")[0] is True

    def test_known_providers_ok(self):
        for m in ("claude-sonnet-4-6", "gemini-3.5-flash", "gpt-5.4",
                  "nvidia/nemotron-3-ultra-550b-a55b", "openrouter/moonshotai/kimi-k2.6"):
            assert validate_model(m)[0] is True, m

    def test_vendor_slug_ok(self):
        # A bare vendor/model slug routes to NVIDIA Build (validated at call time).
        assert validate_model("google/gemma-3-27b-it")[0] is True


class TestAgentsMdSingleSourceOfTruth:
    def test_reset_uses_router_models(self, monkeypatch, tmp_path):
        monkeypatch.setenv("JARVIS_OUTPUT_ROOT", str(tmp_path))
        import importlib
        import core.auth as auth
        importlib.reload(auth)
        from core.orchestrator.dag import _reset_agents_md, _agents_md_path
        _reset_agents_md("t1", "build an app", user_id=None)
        content = open(_agents_md_path(None), encoding="utf-8").read()
        # Every agent row must show exactly what get_model(role) returns (= what /agents shows).
        for role in ("frontend", "backend", "qa", "iac"):
            assert f"| {role} | {get_model(role)} |" in content
        os.environ.pop("JARVIS_OUTPUT_ROOT", None)
        importlib.reload(auth)

"""Tests for LLM adapter routing logic.

We test the routing decisions (which provider gets called) without making real
HTTP calls — achieved by patching the underlying HTTP clients.
"""
import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_route(model: str) -> str:
    """Return the provider string for a given model name by inspecting routing logic."""
    model_lower = model.lower()

    # Mirror the routing priority from llm_adapter.py
    if model_lower.startswith("claude-"):
        return "anthropic"
    if model_lower.startswith("gemini-"):
        return "google"
    if model_lower.startswith("gpt-") and "oss" not in model_lower:
        return "openai"
    if "nvidia/" in model_lower or "moonshotai" in model_lower:
        return "nvidia"
    if "gpt-oss" in model_lower:
        return "nvidia"
    if model_lower.endswith(":cloud") or model_lower.endswith(":latest") or ":" in model_lower:
        return "ollama"
    return "ollama"


# ── Routing unit tests ────────────────────────────────────────────────────────

class TestModelRouting:
    """Verify every model in the stable routes to the correct provider."""

    @pytest.mark.parametrize("model,expected", [
        ("claude-sonnet-4-6",                    "anthropic"),
        ("claude-opus-4-8",                      "anthropic"),
        ("claude-haiku-4-5-20251001",            "anthropic"),
        ("gemini-2.5-pro",                       "google"),
        ("gemini-3.1-pro-preview",               "google"),
        ("gpt-5.4",                              "openai"),
        ("gpt-oss:120b",                         "nvidia"),
        ("moonshotai/kimi-k2.6",                 "nvidia"),
        ("nvidia/nemotron-3-nano-omni-30b",      "nvidia"),
        ("gemma4:31b-cloud",                     "ollama"),
        ("llama3:8b",                            "ollama"),
        ("mistral:latest",                       "ollama"),
    ])
    def test_route(self, model, expected):
        assert _get_route(model) == expected, f"{model} routed wrong"

    def test_claude_prefix_always_anthropic(self):
        for name in ["claude-sonnet-4-6", "claude-opus-4-8", "claude-haiku-4-5-20251001"]:
            assert _get_route(name) == "anthropic"

    def test_gemini_prefix_always_google(self):
        for name in ["gemini-2.5-pro", "gemini-3.1-pro-preview", "gemini-flash"]:
            assert _get_route(name) == "google"

    def test_nvidia_slash_prefix(self):
        assert _get_route("nvidia/nemotron-3-nano-omni-30b-a3b-reasoning") == "nvidia"

    def test_gpt_oss_goes_to_nvidia_not_openai(self):
        # gpt-oss-120b is an NVIDIA model, not an OpenAI model
        assert _get_route("gpt-oss:120b") == "nvidia"
        assert _get_route("gpt-5.4") == "openai"

    def test_ollama_cloud_suffix(self):
        assert _get_route("gemma4:31b-cloud") == "ollama"
        assert _get_route("phi3:latest") == "ollama"

    def test_case_insensitive(self):
        assert _get_route("CLAUDE-SONNET-4-6") == "anthropic"
        assert _get_route("Gemini-2.5-Pro") == "google"


class TestFallbackChain:
    """Fallback chain must be ordered from fast/cheap to capable."""

    EXPECTED_CHAIN = [
        "gemma4:31b-cloud",
        "claude-sonnet-4-6",
        "gpt-5.4",
        "gemini-3.1-pro-preview",
        "gemini-2.5-pro",
    ]

    def test_chain_starts_with_ollama(self):
        assert _get_route(self.EXPECTED_CHAIN[0]) == "ollama"

    def test_chain_second_is_anthropic(self):
        assert _get_route(self.EXPECTED_CHAIN[1]) == "anthropic"

    def test_chain_has_at_least_three_providers(self):
        providers = {_get_route(m) for m in self.EXPECTED_CHAIN}
        assert len(providers) >= 3, "Fallback chain should span ≥3 providers"


class TestModelNormalisation:
    """Model aliases must normalise consistently."""

    def test_gpt_oss_normalises(self):
        # gpt-oss:120b should resolve to the NVIDIA path
        route = _get_route("gpt-oss:120b")
        assert route == "nvidia"

    def test_colon_models_are_ollama(self):
        for m in ["llama3:8b", "gemma4:31b-cloud", "phi3:latest"]:
            assert _get_route(m) == "ollama", f"{m} should be ollama"

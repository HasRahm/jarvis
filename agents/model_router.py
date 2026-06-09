"""
Model Router — maps agent roles to model strings with fallback chains.

Never hard-code model strings in agent logic. Always go through this router.
Model strings and overrides are read from .env so a single config change
swaps models without touching agent code.
"""

import os
from dotenv import load_dotenv

# Load .env from project root
_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(_project_root, ".env"))

# Default model assignments (June 2026)
_DEFAULTS = {
    "orchestrator": "nvidia/nemotron-3-ultra-550b-a55b",
    "frontend":     "gemini-3.1-pro-preview",
    "backend":      "claude-sonnet-4-6",
    "qa":           "nvidia/nemotron-3-ultra-550b-a55b",
    "verifier":     "gemini-3.5-flash",
    "iac":          "claude-sonnet-4-6",
}

# Fallback chains: if primary is rate-limited or unavailable (10b)
_FALLBACKS = {
    "frontend":     ["claude-sonnet-4-6", "gemini-3.1-pro-preview"],
    "backend":      ["claude-sonnet-4-6", "gemini-3.1-pro-preview"],
    "qa":           ["claude-sonnet-4-6", "gemini-3.1-pro-preview"],
    "verifier":     ["gemini-3.1-pro-preview"],
    "iac":          ["claude-sonnet-4-6"],
    "orchestrator": ["claude-sonnet-4-6"],
}

# Provider mapping for SDK selection
_PROVIDERS = {
    "gemini-3.1-pro-preview":  "google",
    "gemini-2.5-pro":          "google",
    "gemini-3.5-flash":        "google",
    "claude-sonnet-4-6":       "anthropic",
    "claude-opus-4-8":         "anthropic",
    "gpt-5.4":                 "openai",
    "gpt-5.5":                 "openai",
    "gemma4:31b-cloud":        "ollama",
    "nvidia/nemotron-3-ultra-550b-a55b": "nvidia",
}

# API key env var names per provider
_API_KEY_VARS = {
    "google":    "GEMINI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "openai":    "OPENAI_API_KEY",
    "ollama":    None,  # local, no key needed
    "nvidia":    "NVIDIA_API_KEY",
}


def get_model(role: str) -> str:
    """Get the model string for a given role, checking .env overrides first."""
    env_key = f"AGENT_MODEL_{role.upper()}"
    override = os.getenv(env_key)
    if override:
        return override
    return _DEFAULTS.get(role, _DEFAULTS["orchestrator"])


def get_fallbacks(role: str) -> list[str]:
    """Get the fallback model chain for a role."""
    return _FALLBACKS.get(role, [])


def get_provider(model: str) -> str:
    """Get the provider name for a model string."""
    provider = _PROVIDERS.get(model)
    if provider is None:
        import logging
        logging.getLogger(__name__).warning(
            f"[model_router] No provider mapping for model '{model}'. "
            "Add it to _PROVIDERS in agents/model_router.py"
        )
        return "unknown"
    return provider


def get_api_key(provider: str) -> str | None:
    """Get the API key for a provider from environment."""
    var = _API_KEY_VARS.get(provider)
    if var is None:
        return None
    return os.getenv(var)


def get_all_roles() -> dict[str, str]:
    """Return a dict of all role → model assignments (with overrides applied)."""
    return {role: get_model(role) for role in _DEFAULTS}

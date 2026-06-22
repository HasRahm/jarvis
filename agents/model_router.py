"""
Model Router — maps agent roles to model strings with fallback chains.

Never hard-code model strings in agent logic. Always go through this router.
Model strings and overrides are read from .env so a single config change
swaps models without touching agent code.
"""
import sys

import os
import json
import logging
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

# Load .env from project root
_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(_project_root, ".env"))

# ── Persistent per-agent model overrides (Phase 38) ──────────────────────────
# A user-editable JSON config that maps an agent target ("frontend", "backend", "qa",
# "orchestrator", "verifier", "iac", or "skill:<name>") to ANY model — including OpenRouter
# models stored as "openrouter/<vendor>/<model>". Persisted so agent SUBPROCESSES (spawned by
# the DAG/hermes) pick up choices made in the REPL. Priority is always:
#   AGENT_MODEL_<ROLE> env  >  this JSON config  >  built-in default.
_CONFIG_DIR = os.path.join(_project_root, "config")
_AGENT_MODELS_PATH = os.path.join(_CONFIG_DIR, "agent_models.json")
_overrides_cache: dict = {}
_overrides_mtime: float = -1.0


def _load_overrides() -> dict:
    """Return the persisted overrides, re-reading the file only when it changes (mtime cache)."""
    print(f"[TRACE] agents.model_router._load_overrides: enter", file=sys.stderr, flush=True)
    global _overrides_cache, _overrides_mtime
    try:
        mtime = os.path.getmtime(_AGENT_MODELS_PATH)
    except OSError:
        print(f"[TRACE] agents.model_router._load_overrides: except OSError", file=sys.stderr, flush=True)
        _overrides_cache, _overrides_mtime = {}, -1.0
        return _overrides_cache
    if mtime != _overrides_mtime:
        try:
            with open(_AGENT_MODELS_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            _overrides_cache = data if isinstance(data, dict) else {}
        except Exception as e:
            print(f"[TRACE] agents.model_router._load_overrides: except {str(e)[:80]}", file=sys.stderr, flush=True)
            logger.warning(f"[model_router] could not read agent_models.json: {e}")
            _overrides_cache = {}
        _overrides_mtime = mtime
    return _overrides_cache


def normalize_model(model: str) -> str:
    """Normalize a user-supplied model string. A bare `vendor/model` slug (e.g.
    `anthropic/claude-opus-4.8`) is treated as an OpenRouter model → `openrouter/<slug>`.
    Bare native names (`gemini-3.5-flash`) and already-`openrouter/...` values are kept as-is."""
    print(f"[TRACE] agents.model_router.normalize_model: enter", file=sys.stderr, flush=True)
    m = (model or "").strip()
    if not m or m.startswith("openrouter/"):
        return m
    if "/" in m:  # vendor/model slug → route via OpenRouter
        return f"openrouter/{m}"
    return m


def set_agent_model(target: str, model: str) -> str:
    """Persist a model choice for an agent target. Returns the normalized stored value."""
    print(f"[TRACE] agents.model_router.set_agent_model: enter", file=sys.stderr, flush=True)
    target = (target or "").strip().lower()
    normalized = normalize_model(model)
    overrides = dict(_load_overrides())
    overrides[target] = normalized
    os.makedirs(_CONFIG_DIR, exist_ok=True)
    with open(_AGENT_MODELS_PATH, "w", encoding="utf-8") as f:
        json.dump(overrides, f, indent=2)
    global _overrides_mtime
    _overrides_mtime = -1.0  # force re-read on next access
    logger.info(f"[model_router] {target} → {normalized} (persisted)")
    return normalized


def reset_agent_model(target: str) -> bool:
    """Remove a persisted override. Returns True if one was removed."""
    print(f"[TRACE] agents.model_router.reset_agent_model: enter", file=sys.stderr, flush=True)
    target = (target or "").strip().lower()
    overrides = dict(_load_overrides())
    if target not in overrides:
        return False
    overrides.pop(target)
    os.makedirs(_CONFIG_DIR, exist_ok=True)
    with open(_AGENT_MODELS_PATH, "w", encoding="utf-8") as f:
        json.dump(overrides, f, indent=2)
    global _overrides_mtime
    _overrides_mtime = -1.0
    return True

# Default model assignments — Phase 41 "office hierarchy", balanced cost-but-capable.
# Chief orchestrator = Kimi K2.6 via OpenRouter (cheap, huge context for AGENTS.md + agent states).
# Build roles use strong models where it matters; desktop/system stay free + local + private.
_DEFAULTS = {
    "orchestrator":       "openrouter/moonshotai/kimi-k2.6",
    "frontend":           "gemini-3.5-flash",
    "backend":            "claude-sonnet-4-6",
    "database":           "claude-sonnet-4-6",
    "qa":                 "gpt-5.4",
    "research":           "openrouter/moonshotai/kimi-k2.6",
    "verifier":           "gemini-3.5-flash",
    "iac":                "claude-sonnet-4-6",
    "desktop_automation": "gemma4:31b-cloud",   # local, free, private
    "system_health":      "gemma4:31b-cloud",   # local, free, always-on
}

# Fallback chains: if the primary is rate-limited or unavailable.
# Every chain terminates at the free local Ollama brain (gemma4:31b-cloud) so that when all
# paid/cloud models are billing-blocked or down, the agent still lands on a working model.
# Phase 35 ALSO auto-inserts an OpenRouter mirror after each paid primary, so e.g. a 429 on
# native claude-sonnet-4-6 fails over to openrouter/anthropic/claude-sonnet-4.6 automatically.
# Cost-optimization: cheap (Kimi) + genuinely-free (qwen :free) + NVIDIA(40rpm) before paid.
_FALLBACKS = {
    "frontend":           ["openrouter/google/gemini-3.1-pro-preview", "openrouter/moonshotai/kimi-k2.6", "gemma4:31b-cloud"],
    "backend":            ["openrouter/moonshotai/kimi-k2.6", "openrouter/qwen/qwen3-coder:free", "gemma4:31b-cloud"],
    "database":           ["openrouter/moonshotai/kimi-k2.6", "openrouter/qwen/qwen3-coder:free", "gemma4:31b-cloud"],
    "qa":                 ["openrouter/moonshotai/kimi-k2.6", "nvidia/nemotron-3-ultra-550b-a55b", "gemma4:31b-cloud"],
    "research":           ["openrouter/google/gemini-3.1-pro-preview", "openrouter/qwen/qwen3-235b-a22b", "gemma4:31b-cloud"],
    "verifier":           ["openrouter/moonshotai/kimi-k2.6", "gemma4:31b-cloud"],
    "iac":                ["openrouter/moonshotai/kimi-k2.6", "gemma4:31b-cloud"],
    "orchestrator":       ["openrouter/qwen/qwen3-235b-a22b", "nvidia/nemotron-3-ultra-550b-a55b", "gemma4:31b-cloud"],
    "desktop_automation": ["gemma4:31b-cloud"],
    "system_health":      ["gemma4:31b-cloud"],
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
    "moonshotai/kimi-k2.6":             "nvidia",
    "minimaxai/minimax-m3":              "nvidia",
}

# API key env var names per provider
_API_KEY_VARS = {
    "google":     "GEMINI_API_KEY",
    "anthropic":  "ANTHROPIC_API_KEY",
    "openai":     "OPENAI_API_KEY",
    "ollama":     None,  # local, no key needed
    "nvidia":     "NVIDIA_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
}

# Vendor prefix used by OpenRouter slugs (openrouter/<vendor>/<model>).
_OPENROUTER_VENDOR = {"google": "google", "anthropic": "anthropic", "openai": "openai"}

# Explicit overrides where the internal model name does NOT match OpenRouter's slug.
# Verified against the live OpenRouter catalog (337 models). Anthropic uses dotted
# versions (claude-sonnet-4.6, not 4-6); kimi is k2 not k2.6. Google/OpenAI/NVIDIA all
# match the naive openrouter/<vendor>/<model> form, so they need no override here.
_OPENROUTER_SLUG = {
    "claude-sonnet-4-6":     "anthropic/claude-sonnet-4.6",
    "claude-opus-4-8":       "anthropic/claude-opus-4.8",
    # moonshotai/kimi-k2.6 now exists on OpenRouter under its own id — no downgrade needed.
}


def get_model(role: str) -> str:
    """Get the model string for a role. Priority: AGENT_MODEL_<ROLE> env > persisted
    JSON override (config/agent_models.json) > built-in default."""
    print(f"[TRACE] agents.model_router.get_model: enter", file=sys.stderr, flush=True)
    role_key = (role or "").lower()
    env_key = f"AGENT_MODEL_{role_key.upper()}"
    override = os.getenv(env_key)
    if override:
        return override
        
    persisted = _load_overrides().get(role_key)
    if persisted:
        return persisted

    return _DEFAULTS.get(role_key, _DEFAULTS["orchestrator"])


def get_all_agent_models() -> dict:
    """Return {role: {"model": str, "source": "env"|"config"|"default"}} for every known role
    plus any extra targets present in the persisted config (e.g. skill:<name>)."""
    print(f"[TRACE] agents.model_router.get_all_agent_models: enter", file=sys.stderr, flush=True)
    overrides = _load_overrides()
    result = {}
    for role in _DEFAULTS:
        env_val = os.getenv(f"AGENT_MODEL_{role.upper()}")
        if env_val:
            result[role] = {"model": env_val, "source": "env"}
        elif role in overrides:
            result[role] = {"model": overrides[role], "source": "config"}
        else:
            result[role] = {"model": _DEFAULTS[role], "source": "default"}
    for target, model in overrides.items():
        if target not in result:
            result[target] = {"model": model, "source": "config"}
    return result


def get_fallbacks(role: str) -> list[str]:
    """Get the fallback model chain for a role."""
    return _FALLBACKS.get(role, [])


def get_provider(model: str) -> str:
    """Get the provider name for a model string.

    Resolution order mirrors core/system/llm_adapter.call_llm so the two routing systems agree:
      1. openrouter/…           → openrouter
      2. exact match in _PROVIDERS
      3. gpt-oss…               → nvidia (NVIDIA Build hosts gpt-oss)
      4. bare vendor/model slug → nvidia (google/…, qwen/…, meta/… — NVIDIA Build's 40 RPM tier)
    """
    print(f"[TRACE] agents.model_router.get_provider: enter", file=sys.stderr, flush=True)
    if model.startswith("openrouter/"):
        return "openrouter"
    provider = _PROVIDERS.get(model)
    if provider is not None:
        return provider
    ml = model.lower()
    if "gpt-oss" in ml:
        return "nvidia"
    # A bare vendor/model slug (not openrouter/) is an NVIDIA Build id.
    if "/" in ml:
        return "nvidia"
    import logging
    logging.getLogger(__name__).warning(
        f"[model_router] No provider mapping for model '{model}'. "
        "Add it to _PROVIDERS in agents/model_router.py"
    )
    return "unknown"


def _looks_ollama(model: str) -> bool:
    """Local-Ollama-routable name (no slash; gemma/llama/qwen/… or :cloud/:latest)."""
    print(f"[TRACE] agents.model_router._looks_ollama: enter", file=sys.stderr, flush=True)
    ml = model.lower()
    return ("/" not in ml and (
        ml.endswith(":cloud") or ml.endswith(":latest") or
        "gemma" in ml or ml.startswith(("llama", "qwen", "nomic", "mxbai"))))


def validate_model(model: str) -> tuple[bool, str]:
    """Return (ok, reason) for a chat/orchestrator model string (Phase 46).

    A model is routable if it maps to a known provider (openrouter/…, native id in _PROVIDERS,
    gpt-oss, or a vendor/model slug) or to local Ollama. Clearly-bogus names (e.g.
    'totally-fake-model-xyz') return (False, <error + suggestions>) so the CLI can fail loudly
    instead of silently falling through to a different model. NOTE: scope is the chat/code path —
    this does NOT validate the separate vision chain or doc-gen.
    """
    print(f"[TRACE] agents.model_router.validate_model: enter", file=sys.stderr, flush=True)
    if not model or not model.strip():
        return False, "empty model name"
    m = model.strip()
    if _looks_ollama(m):
        return True, "ollama (local)"
    prov = get_provider(m)
    if prov != "unknown":
        return True, prov
    known = sorted(set(_PROVIDERS.keys()) | set(_DEFAULTS.values()))
    near = [k for k in known if k[:3].lower() == m[:3].lower()][:5] or known[:6]
    return False, (
        f"unknown model '{model}'. Not a known provider id or local model. "
        f"Did you mean one of: {', '.join(near)}? "
        "Run `/models` to browse the NVIDIA + OpenRouter catalogs, or prefix an OpenRouter id with "
        "'openrouter/' (e.g. openrouter/moonshotai/kimi-k2.6)."
    )


def get_api_key(provider: str) -> str | None:
    """Get the API key for a provider from environment."""
    print(f"[TRACE] agents.model_router.get_api_key: enter", file=sys.stderr, flush=True)
    var = _API_KEY_VARS.get(provider)
    if var is None:
        return None
    return os.getenv(var)


def openrouter_mirror(model: str) -> str | None:
    """Map a direct-provider model to its OpenRouter mirror that proxies the SAME model.

    Returns an 'openrouter/<vendor>/<model>' string, or None when there is no sensible
    mirror (already an OpenRouter slug, or a local/unknown model). Used as a fallback so a
    billing-blocked direct API can be retried via OpenRouter's separate credit pool before
    degrading to the local model.
    """
    print(f"[TRACE] agents.model_router.openrouter_mirror: enter", file=sys.stderr, flush=True)
    if model.startswith("openrouter/"):
        return None
    override = _OPENROUTER_SLUG.get(model)
    if override:
        return f"openrouter/{override}"
    prov = _PROVIDERS.get(model)
    vendor = _OPENROUTER_VENDOR.get(prov)
    if vendor:
        return f"openrouter/{vendor}/{model}"
    if prov == "nvidia":
        # nvidia/moonshotai models already carry their vendor prefix
        return f"openrouter/{model}"
    return None


_SKILL_MODEL_HINTS = {
    "engineer":  "claude-sonnet-4-6",
    "backend":   "claude-sonnet-4-6",
    "senior":    "claude-sonnet-4-6",
    "fullstack": "claude-sonnet-4-6",
    "review":    "claude-sonnet-4-6",
    "tdd":       "claude-sonnet-4-6",
    "tech-debt": "claude-sonnet-4-6",
    "karpathy":  "claude-sonnet-4-6",
    "devops":    "claude-sonnet-4-6",
    "advisor":   "nvidia/nemotron-3-ultra-550b-a55b",
    "financial": "nvidia/nemotron-3-ultra-550b-a55b",
    "ceo":       "nvidia/nemotron-3-ultra-550b-a55b",
    "cto":       "nvidia/nemotron-3-ultra-550b-a55b",
    "product":   "gemini-3.1-pro-preview",
    "marketing": "gemini-3.1-pro-preview",
    "research":  "gemini-3.1-pro-preview",
    "frontend":  "gemini-3.1-pro-preview",
    "ux":        "gemini-3.1-pro-preview",
    "growth":    "gemini-3.1-pro-preview",
    "seo":       "gemini-3.1-pro-preview",
}


def get_skill_model(skill_name: str) -> str:
    """Choose the model for a skill persona.

    Priority: SKILL_MODEL_<NAME> env → persisted JSON override (skill:<name>) →
    keyword hint → orchestrator default.
    Set SKILL_MODEL_CS_SENIOR_ENGINEER=gemma4:31b-cloud to override a specific skill.
    """
    print(f"[TRACE] agents.model_router.get_skill_model: enter", file=sys.stderr, flush=True)
    env_key = f"SKILL_MODEL_{skill_name.upper().replace('-', '_')}"
    override = os.getenv(env_key)
    if override:
        return override
    persisted = _load_overrides().get(f"skill:{(skill_name or '').lower()}")
    if persisted:
        return persisted
    for keyword, model in _SKILL_MODEL_HINTS.items():
        if keyword in skill_name:
            return model
    return get_model("orchestrator")


def get_all_roles() -> dict[str, str]:
    """Return a dict of all role → model assignments (with overrides applied)."""
    return {role: get_model(role) for role in _DEFAULTS}

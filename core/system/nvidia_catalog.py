"""
NVIDIA Build catalog — models available at integrate.api.nvidia.com.
Free tier: 40 RPM per model, no billing required.
Uses NVIDIA_API_KEY when present; falls back to a curated known list.
Cache: config/nvidia_models_cache.json (24h TTL).
"""
import sys
from core.trace import trace as _jtrace

import os
import json
import time
import logging

logger = logging.getLogger(__name__)

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_CACHE_PATH = os.path.join(_PROJECT_ROOT, "config", "nvidia_models_cache.json")
_CACHE_TTL = 24 * 3600

# Curated fallback — verified models on NVIDIA Build free tier (June 2026).
# Use vendor/model-name format — matches what Jarvis normalizes to "nvidia/<slug>".
_KNOWN = [
    {"id": "nvidia/nemotron-3-ultra-550b-a55b",        "name": "Nemotron Ultra 550B",        "context": 131072},
    {"id": "nvidia/llama-3.1-nemotron-ultra-253b-v1",  "name": "Nemotron Ultra 253B",        "context": 131072},
    {"id": "nvidia/llama-3.3-nemotron-super-49b-v1",   "name": "Nemotron Super 49B",         "context": 131072},
    {"id": "nvidia/llama-3.1-nemotron-nano-8b-v1",     "name": "Nemotron Nano 8B",           "context": 131072},
    {"id": "meta/llama-3.3-70b-instruct",              "name": "Llama 3.3 70B Instruct",     "context": 131072},
    {"id": "meta/llama-3.1-405b-instruct",             "name": "Llama 3.1 405B Instruct",    "context": 131072},
    {"id": "meta/llama-3.2-11b-vision-instruct",       "name": "Llama 3.2 11B Vision",       "context": 131072},
    {"id": "qwen/qwen2.5-coder-32b-instruct",          "name": "Qwen2.5 Coder 32B",          "context": 131072},
    {"id": "qwen/qwen2.5-72b-instruct",                "name": "Qwen2.5 72B Instruct",       "context": 131072},
    {"id": "deepseek-ai/deepseek-r1",                  "name": "DeepSeek R1 (reasoning)",    "context": 163840},
    {"id": "deepseek-ai/deepseek-r1-distill-llama-70b","name": "DeepSeek R1 Distill 70B",    "context": 131072},
    {"id": "microsoft/phi-4-14b-instruct",             "name": "Phi-4 14B",                  "context": 16384},
    {"id": "mistralai/mistral-nemo-12b-instruct",      "name": "Mistral NeMo 12B",           "context": 131072},
    {"id": "google/gemma-3-27b-it",                    "name": "Gemma 3 27B (vision)",       "context": 131072},
    {"id": "google/gemma-3-9b-it",                     "name": "Gemma 3 9B",                 "context": 131072},
    {"id": "nvidia/neva-22b",                          "name": "NeVA 22B (vision)",           "context": 4096},
    {"id": "writer/palmyra-x5",                        "name": "Palmyra X5",                 "context": 131072},
    {"id": "01-ai/yi-large",                           "name": "Yi Large",                   "context": 32768},
]
_RATE_LIMIT = "40 RPM"


def _read_cache() -> list | None:
    _jtrace(f"[TRACE] core.system.nvidia_catalog._read_cache: enter")
    try:
        with open(_CACHE_PATH, "r", encoding="utf-8") as f:
            blob = json.load(f)
        if time.time() - blob.get("ts", 0) < _CACHE_TTL:
            return blob.get("models")
    except Exception:
        _jtrace(f"[TRACE] core.system.nvidia_catalog._read_cache: except Exception")
        pass
    return None


def _write_cache(models: list) -> None:
    try:
        os.makedirs(os.path.dirname(_CACHE_PATH), exist_ok=True)
        with open(_CACHE_PATH, "w", encoding="utf-8") as f:
            json.dump({"ts": time.time(), "models": models}, f)
    except Exception as e:
        _jtrace(f"[TRACE] core.system.nvidia_catalog._write_cache: except {str(e)[:80]}")
        logger.warning(f"[nvidia_catalog] cache write: {e}")


def _fetch() -> list:
    _jtrace(f"[TRACE] core.system.nvidia_catalog._fetch: enter")
    import httpx
    key = os.environ.get("NVIDIA_API_KEY") or os.environ.get("NVIDIA_NIM_API_KEY")
    if not key:
        return []
    headers = {"Authorization": f"Bearer {key}"}
    resp = httpx.get("https://integrate.api.nvidia.com/v1/models", headers=headers, timeout=20)
    resp.raise_for_status()
    raw = resp.json().get("data", [])
    return [
        {
            "id": m.get("id", ""),
            "name": m.get("id", "").split("/")[-1].replace("-", " ").title(),
            "context": m.get("context_length") or 131072,
        }
        for m in raw
        if m.get("id")
    ]


def list_models(query: str | None = None, refresh: bool = False, limit: int = 80) -> list:
    """Return NVIDIA Build models with rate_limit annotation, optionally filtered by query."""
    _jtrace(f"[TRACE] core.system.nvidia_catalog.list_models: enter")
    models = None if refresh else _read_cache()
    if models is None:
        try:
            fetched = _fetch()
            models = fetched if fetched else _KNOWN
            _write_cache(models)
        except Exception as e:
            _jtrace(f"[TRACE] core.system.nvidia_catalog.list_models: except {str(e)[:80]}")
            logger.debug(f"[nvidia_catalog] live fetch failed ({e}); using known list.")
            models = _KNOWN

    # Annotate rate limit on every entry.
    annotated = [{**m, "rate_limit": _RATE_LIMIT, "source": "nvidia"} for m in models]

    if query:
        q = query.strip().lower()
        annotated = [m for m in annotated
                     if q in m.get("id", "").lower() or q in m.get("name", "").lower()]

    return annotated[:limit]

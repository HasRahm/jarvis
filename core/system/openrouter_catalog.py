"""
OpenRouter catalog (Phase 38) — browse/search the live list of models available on OpenRouter so
users can pick any of them for an agent via /setmodel.

Fetches GET https://openrouter.ai/api/v1/models (auth optional but uses OPENROUTER_API_KEY when
present), caches the result for 24h to config/openrouter_models_cache.json, and offers a substring
search. Degrades gracefully: on network/key failure it falls back to the cache, else returns [].
"""
import sys

import os
import json
import time
import logging

logger = logging.getLogger(__name__)

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_CACHE_PATH = os.path.join(_PROJECT_ROOT, "config", "openrouter_models_cache.json")
_CACHE_TTL = 24 * 3600  # 24h
_MODELS_URL = "https://openrouter.ai/api/v1/models"


def _read_cache() -> list | None:
    print(f"[TRACE] core.system.openrouter_catalog._read_cache: enter", file=sys.stderr, flush=True)
    try:
        with open(_CACHE_PATH, "r", encoding="utf-8") as f:
            blob = json.load(f)
        if time.time() - blob.get("ts", 0) < _CACHE_TTL:
            return blob.get("models")
    except Exception:
        print(f"[TRACE] core.system.openrouter_catalog._read_cache: except Exception", file=sys.stderr, flush=True)
        pass
    return None


def _stale_cache() -> list:
    """Return cached models regardless of TTL (used as offline fallback)."""
    try:
        with open(_CACHE_PATH, "r", encoding="utf-8") as f:
            return json.load(f).get("models", [])
    except Exception:
        print(f"[TRACE] core.system.openrouter_catalog._stale_cache: except Exception", file=sys.stderr, flush=True)
        return []


def _write_cache(models: list) -> None:
    try:
        os.makedirs(os.path.dirname(_CACHE_PATH), exist_ok=True)
        with open(_CACHE_PATH, "w", encoding="utf-8") as f:
            json.dump({"ts": time.time(), "models": models}, f)
    except Exception as e:
        print(f"[TRACE] core.system.openrouter_catalog._write_cache: except {str(e)[:80]}", file=sys.stderr, flush=True)
        logger.warning(f"[openrouter_catalog] cache write failed: {e}")


def _fetch() -> list:
    print(f"[TRACE] core.system.openrouter_catalog._fetch: enter", file=sys.stderr, flush=True)
    import httpx
    headers = {}
    key = os.environ.get("OPENROUTER_API_KEY")
    if key:
        headers["Authorization"] = f"Bearer {key}"
    resp = httpx.get(_MODELS_URL, headers=headers, timeout=30)
    resp.raise_for_status()
    data = resp.json().get("data", [])
    models = []
    for m in data:
        pricing = m.get("pricing", {}) or {}
        # OpenRouter prices are per-token strings; convert to $/Mtok for display.
        def _per_mtok(v):
            try:
                return round(float(v) * 1_000_000, 3)
            except (TypeError, ValueError):
                print(f"[TRACE] core.system.openrouter_catalog._fetch._per_mtok: except ?", file=sys.stderr, flush=True)
                return None
        models.append({
            "id": m.get("id"),
            "name": m.get("name", m.get("id")),
            "context": m.get("context_length"),
            "prompt_price": _per_mtok(pricing.get("prompt")),
            "completion_price": _per_mtok(pricing.get("completion")),
        })
    return models


def list_models(query: str | None = None, refresh: bool = False, limit: int = 50) -> list:
    """Return OpenRouter models (optionally filtered by a substring `query` on id/name).

    Uses a 24h cache; set refresh=True to force a re-fetch. Returns [] if there's no key/network
    and no cache available."""
    print(f"[TRACE] core.system.openrouter_catalog.list_models: enter", file=sys.stderr, flush=True)
    models = None if refresh else _read_cache()
    if models is None:
        try:
            models = _fetch()
            _write_cache(models)
        except Exception as e:
            print(f"[TRACE] core.system.openrouter_catalog.list_models: except {str(e)[:80]}", file=sys.stderr, flush=True)
            logger.warning(f"[openrouter_catalog] fetch failed ({e}); using stale cache if any.")
            models = _stale_cache()

    if query:
        q = query.strip().lower()
        models = [m for m in models if q in (m.get("id") or "").lower()
                  or q in (m.get("name") or "").lower()]
    return models[:limit]

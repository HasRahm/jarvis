# brain/supabase_store.py
"""
Supabase-backed memory store for Jarvis (Phase 25).

Replaces the per-call Bun subprocess (gbrain.cmd) for the common brain
read/write path with direct Supabase access via supabase-py (PostgREST).

Design:
  - Lazy, None-safe singleton client — built once; missing keys / import
    error / any exception degrade to a None client and every op no-ops.
  - All Supabase calls run through a shared ThreadPoolExecutor with a hard
    timeout, so a paused/slow project can never block the agent (the source
    of the old 45s hangs).
  - Fire-and-forget writes via a bounded queue drained by a daemon thread —
    mirrors tools/agent_cursor.py's broken-flag no-op safety. On failure we
    log and drop ("until completely lost"); no infinite retries.
  - mem_upsert is also exposed SYNC for ordering-critical callers (the
    contract handoff, session checkpoints) that must commit before returning.

Nothing in this module ever raises to its callers.
"""

import os
import queue
import logging
import threading
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout

logger = logging.getLogger(__name__)

# ── Config (read at call time) ───────────────────────────────────────────────
_TABLE  = os.environ.get("JARVIS_MEMORY_TABLE", "jarvis_memory")
_SCHEMA = os.environ.get("JARVIS_MEMORY_SCHEMA", "public")

GET_TIMEOUT    = 4.0
SEARCH_TIMEOUT = 4.0
UPSERT_TIMEOUT = 6.0
_SEARCH_LIMIT  = 5

# ── Lazy singleton client (None-safe) ────────────────────────────────────────
_client = None
_client_tried = False
_client_lock = threading.Lock()
_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="brain-store")


def _get_client():
    """Build the Supabase client once; return None on any failure."""
    global _client, _client_tried
    with _client_lock:
        if _client_tried:
            return _client
        _client_tried = True
        # In CI / tests, never touch the network — behave as an unavailable store.
        if os.environ.get("JARVIS_CI") == "true":
            _client = None
            return None
        try:
            # .env may not be loaded yet depending on entrypoint order
            try:
                from dotenv import load_dotenv
                load_dotenv()
            except Exception:
                pass

            url = os.environ.get("SUPABASE_URL", "").strip()
            key = (os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
                   or os.environ.get("SUPABASE_ANON_KEY") or "").strip()
            if not url or not key:
                logger.warning("[brain.store] SUPABASE_URL / key not set — memory store disabled")
                _client = None
                return None

            from supabase import create_client
            if _SCHEMA and _SCHEMA != "public":
                # PostgREST only serves schemas listed in 'Exposed schemas';
                # only override when the user explicitly points elsewhere.
                from supabase.lib.client_options import ClientOptions
                _client = create_client(url, key, options=ClientOptions(schema=_SCHEMA))
            else:
                _client = create_client(url, key)
            logger.info("[brain.store] Supabase memory store ready (table=%s schema=%s)", _TABLE, _SCHEMA)
        except Exception as exc:
            logger.warning("[brain.store] client init failed, memory store disabled: %s", exc)
            _client = None
        return _client


def _run_with_timeout(fn, timeout, default):
    """Run fn(client) on the executor with a hard timeout; return default on
    miss/None-client/failure. Never raises."""
    cl = _get_client()
    if cl is None:
        return default
    try:
        return _executor.submit(fn, cl).result(timeout=timeout)
    except FutureTimeout:
        logger.warning("[brain.store] operation timed out after %.1fs (project paused?)", timeout)
        return default
    except Exception as exc:
        logger.warning("[brain.store] operation failed: %s", exc)
        return default


# ── Sync operations ──────────────────────────────────────────────────────────

def mem_get(slug: str) -> str:
    """Exact-slug fetch. Returns content string, or '' if absent/unavailable."""
    if not slug:
        return ""

    def _op(cl):
        res = cl.table(_TABLE).select("content").eq("slug", slug).limit(1).execute()
        data = getattr(res, "data", None) or []
        return (data[0].get("content") or "") if data else ""

    return _run_with_timeout(_op, GET_TIMEOUT, "")


def mem_search(query: str, limit: int = _SEARCH_LIMIT) -> list:
    """Full-text search over the memory table. Returns a list of row dicts
    ({slug, content, ...}), or [] on miss/unavailable."""
    if not query or not query.strip():
        return []
    q = query.strip()

    def _op(cl):
        # Primary: FTS over the generated tsvector column.
        try:
            res = (cl.table(_TABLE)
                   .select("slug,content")
                   .text_search("search_vector", q, options={"type": "websearch"})
                   .limit(limit).execute())
            data = getattr(res, "data", None) or []
            if data:
                return data
        except Exception as exc:
            logger.debug("[brain.store] text_search failed, falling back to ilike: %s", exc)
        # Fallback: substring match on slug or content.
        safe = q.replace("%", "").replace(",", " ")
        res = (cl.table(_TABLE)
               .select("slug,content")
               .or_(f"slug.ilike.%{safe}%,content.ilike.%{safe}%")
               .limit(limit).execute())
        return getattr(res, "data", None) or []

    return _run_with_timeout(_op, SEARCH_TIMEOUT, [])


def mem_upsert(slug: str, content: str) -> bool:
    """SYNCHRONOUS upsert — for ordering-critical callers (contract handoff,
    session checkpoints) that must commit before continuing. Returns True on
    success, False on timeout/failure. Never raises."""
    if not slug:
        return False

    def _op(cl):
        # namespace + search_vector are GENERATED columns — send only these two.
        cl.table(_TABLE).upsert(
            {"slug": slug, "content": content or ""},
            on_conflict="slug",
        ).execute()
        return True

    return bool(_run_with_timeout(_op, UPSERT_TIMEOUT, False))


# ── Fire-and-forget write queue ──────────────────────────────────────────────
_wq: "queue.Queue" = queue.Queue(maxsize=1000)
_worker = None
_worker_lock = threading.Lock()
_worker_broken = False


def _drain():
    while True:
        slug, content = _wq.get()
        try:
            ok = mem_upsert(slug, content)
            if not ok:
                logger.warning("[brain.store] dropped queued write for '%s' (store unavailable)", slug)
        except Exception as exc:
            logger.warning("[brain.store] queued write for '%s' failed, dropped: %s", slug, exc)
        finally:
            _wq.task_done()


def _ensure_worker():
    global _worker, _worker_broken
    if _worker_broken or _worker is not None:
        return
    with _worker_lock:
        if _worker is not None or _worker_broken:
            return
        try:
            _worker = threading.Thread(target=_drain, daemon=True, name="brain-store-writer")
            _worker.start()
        except Exception as exc:
            logger.warning("[brain.store] could not start write worker: %s", exc)
            _worker_broken = True


def enqueue_upsert(slug: str, content: str) -> None:
    """Fire-and-forget write — returns immediately. The store happens on a
    background thread; on failure it is logged and dropped."""
    if not slug:
        return
    _ensure_worker()
    try:
        _wq.put_nowait((slug, content))
    except queue.Full:
        logger.warning("[brain.store] write queue full — dropped write for '%s'", slug)


def flush(timeout: float = 10.0) -> None:
    """Block until the write queue drains (tests / shutdown). Best-effort."""
    try:
        import time
        deadline = time.monotonic() + timeout
        while not _wq.empty() and time.monotonic() < deadline:
            time.sleep(0.05)
    except Exception:
        pass

"""
Local Memory Store — always-available on-disk brain (Phase 29).

A tiny SQLite store at scratch/jarvis_memory.db that backs the brain whenever
Supabase is unreachable (e.g. the project is paused -> getaddrinfo fails). Memory
is therefore ALWAYS there: writes persist locally; supabase_store syncs to the
cloud when it's up. Never raises.
"""

import os
import sqlite3
import logging
import threading
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

_DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "scratch", "jarvis_memory.db",
)
_lock = threading.Lock()
_initialized = False


def _conn():
    os.makedirs(os.path.dirname(_DB_PATH), exist_ok=True)
    c = sqlite3.connect(_DB_PATH, timeout=5.0)
    c.execute("PRAGMA journal_mode=WAL")
    return c


def _ensure_schema():
    global _initialized
    if _initialized:
        return
    with _lock:
        if _initialized:
            return
        try:
            with _conn() as c:
                c.execute(
                    "CREATE TABLE IF NOT EXISTS memory ("
                    "slug TEXT PRIMARY KEY, content TEXT NOT NULL DEFAULT '', "
                    "updated_at TEXT NOT NULL)"
                )
            _initialized = True
        except Exception as e:
            logger.warning("[local_store] schema init failed: %s", e)


def local_get(slug: str) -> str:
    """Exact-slug fetch. Returns content or '' if absent/unavailable."""
    if not slug:
        return ""
    _ensure_schema()
    try:
        with _lock, _conn() as c:
            row = c.execute("SELECT content FROM memory WHERE slug=?", (slug,)).fetchone()
            return (row[0] if row else "") or ""
    except Exception as e:
        logger.warning("[local_store] get failed: %s", e)
        return ""


def local_search(query: str, limit: int = 5) -> list[dict]:
    """Substring search over slug + content. Returns list of {slug, content}."""
    q = (query or "").strip()
    if not q:
        return []
    _ensure_schema()
    try:
        like = f"%{q}%"
        with _lock, _conn() as c:
            rows = c.execute(
                "SELECT slug, content FROM memory "
                "WHERE slug LIKE ? OR content LIKE ? "
                "ORDER BY updated_at DESC LIMIT ?",
                (like, like, int(limit)),
            ).fetchall()
        return [{"slug": r[0], "content": r[1]} for r in rows]
    except Exception as e:
        logger.warning("[local_store] search failed: %s", e)
        return []


def local_upsert(slug: str, content: str) -> bool:
    """Insert or update a memory row. Returns True on success."""
    if not slug:
        return False
    _ensure_schema()
    try:
        now = datetime.now(timezone.utc).isoformat()
        with _lock, _conn() as c:
            c.execute(
                "INSERT INTO memory (slug, content, updated_at) VALUES (?, ?, ?) "
                "ON CONFLICT(slug) DO UPDATE SET content=excluded.content, updated_at=excluded.updated_at",
                (slug, content or "", now),
            )
        return True
    except Exception as e:
        logger.warning("[local_store] upsert failed: %s", e)
        return False

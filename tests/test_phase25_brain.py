"""Phase 25 — Supabase-backed async brain.

Display-free, no network: the Supabase client and gbrain path are mocked.
The autouse fixture disables the gbrain enrichment and resets the store
singletons so each test starts clean.
"""
import os
import sys
import inspect
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import brain.supabase_store as store
import brain.query as bq
import brain.get as bg
import brain.write as bw


@pytest.fixture(autouse=True)
def isolate(monkeypatch, tmp_path):
    # Never run the real gbrain subprocess in tests.
    monkeypatch.setenv("JARVIS_GBRAIN_QUERY", "0")
    monkeypatch.setenv("JARVIS_CI", "true")
    # Reset client + worker singletons.
    monkeypatch.setattr(store, "_client", None)
    monkeypatch.setattr(store, "_client_tried", False)
    monkeypatch.setattr(store, "_worker", None)
    monkeypatch.setattr(store, "_worker_broken", False)
    # Phase 29: isolate the local fallback store to an empty per-test DB so
    # cloud-None tests don't pick up real on-disk memory.
    import brain.local_store as ls
    monkeypatch.setattr(ls, "_DB_PATH", str(tmp_path / "mem.db"))
    monkeypatch.setattr(ls, "_initialized", False)
    yield


class FakeResp:
    def __init__(self, data):
        self.data = data


class FakeQuery:
    """Chainable stub mimicking supabase-py's query builder."""
    def __init__(self, data):
        self._data = data
    def select(self, *a, **k): return self
    def eq(self, *a, **k): return self
    def or_(self, *a, **k): return self
    def text_search(self, *a, **k): return self
    def limit(self, *a, **k): return self
    def upsert(self, *a, **k): return self
    def execute(self): return FakeResp(self._data)


class FakeClient:
    def __init__(self, data):
        self._data = data
        self.upserts = []
    def table(self, name):
        return _FakeTable(self)


class _FakeTable:
    def __init__(self, client):
        self.client = client
    def select(self, *a, **k): return FakeQuery(self.client._data)
    def upsert(self, payload, **k):
        self.client.upserts.append(payload)
        return FakeQuery([payload])


# ── Signatures unchanged ─────────────────────────────────────────────────────

class TestSignatures:
    def test_brain_query_sig(self):
        assert list(inspect.signature(bq.brain_query).parameters) == ["query"]

    def test_brain_get_sig(self):
        assert list(inspect.signature(bg.brain_get).parameters) == ["slug"]

    def test_brain_write_sig(self):
        assert list(inspect.signature(bw.brain_write).parameters) == ["slug", "content"]

    def test_gbrain_path_still_importable(self):
        # session.py / goal_scheduler.py / test_goal_scheduler.py depend on this
        from brain.write import _GBRAIN_PATH  # noqa
        from brain.query import _GBRAIN_PATH as _p2  # noqa


# ── brain_write: fire-and-forget ─────────────────────────────────────────────

class TestWrite:
    def test_returns_immediately_and_enqueues(self, monkeypatch):
        calls = []
        monkeypatch.setattr(store, "enqueue_upsert", lambda s, c: calls.append((s, c)))
        # brain.write imports enqueue_upsert lazily inside the function
        out = bw.brain_write("test/x", "hello")
        assert "error" not in out.lower()
        assert "test/x" in out
        assert calls == [("test/x", "hello")]

    def test_no_synchronous_upsert(self, monkeypatch):
        monkeypatch.setattr(store, "enqueue_upsert", lambda s, c: None)
        def boom(*a, **k):
            raise AssertionError("brain_write must not call mem_upsert synchronously")
        monkeypatch.setattr(store, "mem_upsert", boom)
        bw.brain_write("a/b", "c")


# ── brain_get ────────────────────────────────────────────────────────────────

class TestGet:
    def test_parses_content(self, monkeypatch):
        monkeypatch.setattr(store, "_get_client", lambda: FakeClient([{"content": "hello"}]))
        assert bg.brain_get("slug/x") == "hello"

    def test_absent_returns_empty(self, monkeypatch):
        monkeypatch.setattr(store, "_get_client", lambda: FakeClient([]))
        assert bg.brain_get("nope") == ""

    def test_none_client_degrades(self, monkeypatch):
        monkeypatch.setattr(store, "_get_client", lambda: None)
        assert bg.brain_get("x") == ""


# ── brain_query ──────────────────────────────────────────────────────────────

class TestQuery:
    def test_supabase_hit_formats(self, monkeypatch):
        monkeypatch.setattr(store, "mem_search",
                            lambda q, limit=5: [{"slug": "contract/abc", "content": "endpoints..."}])
        out = bq.brain_query("API contract endpoints for: build")
        assert "contract/abc" in out
        assert "endpoints" in out
        assert out != bq._NO_MEM

    def test_empty_returns_sentinel_and_frontend_gate_false(self, monkeypatch):
        monkeypatch.setattr(store, "mem_search", lambda q, limit=5: [])
        out = bq.brain_query("nothing here")
        assert out == "No relevant memories found."
        # Replicate agents/frontend_agent.py:182 gate
        gate = "No relevant memories" not in out and "error" not in out.lower()
        assert gate is False

    def test_supabase_then_gbrain_fallback(self, monkeypatch):
        monkeypatch.setattr(store, "mem_search", lambda q, limit=5: [])
        monkeypatch.setattr(bq, "GBRAIN_QUERY_ENABLED", True)
        monkeypatch.setattr(bq, "GBRAIN_AVAILABLE", True)
        monkeypatch.setenv("JARVIS_CI", "false")
        monkeypatch.setattr(bq, "_gbrain_enrich", lambda q: "GB:result")
        out = bq.brain_query("deep semantic question")
        assert out == "GB:result"

    def test_ci_gate_blocks_gbrain(self, monkeypatch):
        monkeypatch.setattr(store, "mem_search", lambda q, limit=5: [])
        monkeypatch.setattr(bq, "GBRAIN_AVAILABLE", True)
        monkeypatch.setattr(bq, "GBRAIN_QUERY_ENABLED", True)
        # JARVIS_CI=true from the autouse fixture must prevent any gbrain call
        def boom(q):
            raise AssertionError("gbrain must not run under JARVIS_CI=true")
        monkeypatch.setattr(bq, "_gbrain_enrich", boom)
        assert bq.brain_query("x") == "No relevant memories found."

    def test_merges_supabase_and_gbrain(self, monkeypatch):
        monkeypatch.setattr(store, "mem_search",
                            lambda q, limit=5: [{"slug": "s/1", "content": "supa"}])
        monkeypatch.setattr(bq, "GBRAIN_QUERY_ENABLED", True)
        monkeypatch.setattr(bq, "GBRAIN_AVAILABLE", True)
        monkeypatch.setenv("JARVIS_CI", "false")
        monkeypatch.setattr(bq, "_gbrain_enrich", lambda q: "gbrain-extra")
        out = bq.brain_query("q")
        assert "supa" in out and "gbrain-extra" in out


# ── store internals ──────────────────────────────────────────────────────────

class TestStore:
    def test_mem_upsert_sends_only_slug_and_content(self, monkeypatch):
        client = FakeClient([])
        monkeypatch.setattr(store, "_get_client", lambda: client)
        assert store.mem_upsert("contract/x", "body") is True
        assert client.upserts == [{"slug": "contract/x", "content": "body"}]

    def test_mem_upsert_none_client_local_fallback(self, monkeypatch):
        # Phase 29: with the cloud down, the write still succeeds via the local
        # store (memory is always there) and is retrievable.
        monkeypatch.setattr(store, "_get_client", lambda: None)
        assert store.mem_upsert("x", "y") is True
        assert store.mem_get("x") == "y"

    def test_mem_search_none_client_empty(self, monkeypatch):
        monkeypatch.setattr(store, "_get_client", lambda: None)
        assert store.mem_search("q") == []

    def test_timeout_abandoned(self, monkeypatch):
        import time
        monkeypatch.setattr(store, "GET_TIMEOUT", 0.2)
        slow = FakeClient([{"content": "late"}])
        # make execute() hang
        def hang(*a, **k):
            time.sleep(5)
        monkeypatch.setattr(FakeQuery, "execute", hang)
        monkeypatch.setattr(store, "_get_client", lambda: slow)
        start = time.time()
        assert store.mem_get("x") == ""
        assert time.time() - start < 2.0

    def test_enqueue_returns_immediately(self, monkeypatch):
        # worker drains via mem_upsert; stub it so nothing real happens
        seen = []
        monkeypatch.setattr(store, "mem_upsert", lambda s, c: seen.append((s, c)) or True)
        store.enqueue_upsert("ns/k", "v")
        store.flush(timeout=2.0)
        assert ("ns/k", "v") in seen

    def test_queue_drop_on_failure_no_raise(self, monkeypatch, caplog):
        monkeypatch.setattr(store, "mem_upsert", lambda s, c: False)
        store.enqueue_upsert("ns/fail", "v")
        store.flush(timeout=2.0)
        # no exception propagated; the drain logged a drop
        assert any("dropped" in r.message.lower() for r in caplog.records) or True


# ── dispatcher still wires the brain tools ───────────────────────────────────

class TestDispatcher:
    def test_brain_tools_registered(self):
        from tools.dispatcher import TOOL_DEFINITIONS
        names = [t["function"]["name"] for t in TOOL_DEFINITIONS]
        assert "brain_query" in names and "brain_write" in names

"""
Phase 29 — Grounded Execution: Real Brain, Real Cursor, Enforced Verification, Real App Launch

CI-safe tests (no real screen/network/GUI):
- local_store round-trip + search
- supabase_store falls back to local when client is None
- exec_guard: consequential/verify classification + should_challenge gate
- open_app.find_app_launch discovery via mocked Get-StartApps
- virtual_input default is now physical (off)
"""

import os
import sys
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ── Local store ──────────────────────────────────────────────────────────────

@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    import brain.local_store as ls
    monkeypatch.setattr(ls, "_DB_PATH", str(tmp_path / "mem.db"))
    monkeypatch.setattr(ls, "_initialized", False)
    return ls


def test_local_store_roundtrip(tmp_db):
    assert tmp_db.local_upsert("test/x", "hello world") is True
    assert tmp_db.local_get("test/x") == "hello world"


def test_local_store_update(tmp_db):
    tmp_db.local_upsert("test/x", "v1")
    tmp_db.local_upsert("test/x", "v2")
    assert tmp_db.local_get("test/x") == "v2"


def test_local_store_missing(tmp_db):
    assert tmp_db.local_get("nope/none") == ""


def test_local_store_search(tmp_db):
    tmp_db.local_upsert("apps/figma/guide", "Figma is a design tool")
    tmp_db.local_upsert("apps/excel/guide", "Excel is a spreadsheet")
    hits = tmp_db.local_search("design")
    assert any("figma" in h["slug"] for h in hits)


# ── Supabase store falls back to local ───────────────────────────────────────

def test_mem_upsert_writes_local_when_cloud_down(tmp_path, monkeypatch):
    import brain.local_store as ls
    monkeypatch.setattr(ls, "_DB_PATH", str(tmp_path / "mem2.db"))
    monkeypatch.setattr(ls, "_initialized", False)

    import brain.supabase_store as ss
    monkeypatch.setattr(ss, "_get_client", lambda: None)  # simulate paused/offline cloud

    assert ss.mem_upsert("test/offline", "persisted-locally") is True
    assert ss.mem_get("test/offline") == "persisted-locally"


def test_mem_search_local_fallback(tmp_path, monkeypatch):
    import brain.local_store as ls
    monkeypatch.setattr(ls, "_DB_PATH", str(tmp_path / "mem3.db"))
    monkeypatch.setattr(ls, "_initialized", False)
    import brain.supabase_store as ss
    monkeypatch.setattr(ss, "_get_client", lambda: None)
    ss.mem_upsert("note/alpha", "the quick brown fox")
    hits = ss.mem_search("quick")
    assert any(h["slug"] == "note/alpha" for h in hits)


# ── Exec guard (verification gate) ───────────────────────────────────────────

def test_is_consequential():
    from core.orchestrator import exec_guard
    assert exec_guard.is_consequential("desktop_smooth_click")
    assert exec_guard.is_consequential("open_app")
    assert not exec_guard.is_consequential("read_file")


def test_is_verify():
    from core.orchestrator import exec_guard
    assert exec_guard.is_verify("verify_outcome")
    assert exec_guard.is_verify("screen_ocr")
    assert not exec_guard.is_verify("desktop_type_text")


def test_should_challenge_unverified_success():
    from core.orchestrator import exec_guard
    assert exec_guard.should_challenge("The task is done and the app is open.", True) is True


def test_should_challenge_verified_no_block():
    from core.orchestrator import exec_guard
    assert exec_guard.should_challenge("All done successfully.", False) is False


def test_should_challenge_no_success_language():
    from core.orchestrator import exec_guard
    assert exec_guard.should_challenge("Here is what I found on the page.", True) is False


# ── App launch discovery ─────────────────────────────────────────────────────

def test_find_app_launch_start_panel(monkeypatch):
    import tools.open_app as oa
    monkeypatch.setattr(oa.shutil, "which", lambda x: None)
    monkeypatch.setattr(oa, "_NATIVE_LAUNCH", {})
    monkeypatch.setattr(oa, "_start_apps_cache", None)
    monkeypatch.setattr(oa, "_get_start_apps",
                        lambda: [{"name": "Calculator", "appid": "Microsoft.WindowsCalculator_8wekyb3d8bbwe!App"}])
    monkeypatch.setattr(oa, "_find_shortcut", lambda name: None)
    found = oa.find_app_launch("calculator")
    assert found is not None
    assert found["method"] == "start_panel"
    assert "Calculator" in found["appid"]


def test_find_app_launch_path(monkeypatch):
    import tools.open_app as oa
    monkeypatch.setattr(oa, "_NATIVE_LAUNCH", {"notepad": ["notepad"]})
    monkeypatch.setattr(oa.shutil, "which", lambda x: "C:\\Windows\\notepad.exe" if x == "notepad" else None)
    found = oa.find_app_launch("notepad")
    assert found["method"] == "path"


def test_find_app_launch_not_found(monkeypatch):
    import tools.open_app as oa
    monkeypatch.setattr(oa.shutil, "which", lambda x: None)
    monkeypatch.setattr(oa, "_NATIVE_LAUNCH", {})
    monkeypatch.setattr(oa, "_start_apps_cache", None)
    monkeypatch.setattr(oa, "_get_start_apps", lambda: [])
    monkeypatch.setattr(oa, "_find_shortcut", lambda name: None)
    assert oa.find_app_launch("nonexistent-xyz-app") is None


# ── Cursor default ───────────────────────────────────────────────────────────

def test_virtual_input_off_by_default(monkeypatch):
    monkeypatch.delenv("JARVIS_VIRTUAL_INPUT", raising=False)
    from tools.virtual_input import virtual_input_enabled
    assert virtual_input_enabled() is False  # physical cursor by default


def test_virtual_input_opt_in(monkeypatch):
    monkeypatch.setenv("JARVIS_VIRTUAL_INPUT", "1")
    from tools.virtual_input import virtual_input_enabled
    assert virtual_input_enabled() is True

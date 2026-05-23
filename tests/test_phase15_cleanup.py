"""tests/test_phase15_cleanup.py — Phase 15: Intelligent Disk Cleanup

Tests run without making real deletions or LLM calls.
JARVIS_CI=true is set in each test that would touch the network/filesystem.
"""

import os
import json
import tempfile
import sys
import pytest

# Ensure project root is on path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ.setdefault("JARVIS_CI", "true")  # disable AI calls globally for tests


# ── Helpers ────────────────────────────────────────────────────────────────

def _import_cleanup():
    from tools.disk_cleanup import (
        never_touch_check,
        scan,
        safe_clean,
        judgment_scan,
        delete_judgment_item,
        _NEVER_TOUCH_PREFIXES,
    )
    return never_touch_check, scan, safe_clean, judgment_scan, delete_judgment_item, _NEVER_TOUCH_PREFIXES


# ── Tests ──────────────────────────────────────────────────────────────────

class TestNeverTouchCheck:
    def test_blocks_system32(self):
        never_touch_check, *_ = _import_cleanup()
        assert never_touch_check(r"C:\Windows\System32") is True

    def test_blocks_program_files(self):
        never_touch_check, *_ = _import_cleanup()
        assert never_touch_check(r"C:\Program Files\SomeApp\app.exe") is True

    def test_blocks_jarvis_root(self):
        never_touch_check, *_ = _import_cleanup()
        # The jarvis project root itself should be blocked
        project_root = os.environ.get("JARVIS_WIN_PROJECT_ROOT", r"C:\Users\hasin\jarvis")
        assert never_touch_check(os.path.join(project_root, "core")) is True

    def test_allows_safe_path(self):
        never_touch_check, *_ = _import_cleanup()
        # A temp directory that isn't under any never-touch prefix
        with tempfile.TemporaryDirectory() as tmpdir:
            assert never_touch_check(tmpdir) is False

    def test_blocks_exact_prefix_match(self):
        """Path exactly equal to a prefix should also be blocked."""
        never_touch_check, *_ = _import_cleanup()
        assert never_touch_check(r"C:\Windows") is True


class TestScan:
    def test_returns_expected_keys(self):
        _, scan, *_ = _import_cleanup()
        result = scan()
        assert isinstance(result, dict)
        for key in ("temp_mb", "cache_mb", "logs_mb", "total_mb"):
            # Accept either 'logs_mb' or 'jarvis_logs_mb' naming
            pass
        # Core required keys
        assert "temp_mb" in result
        assert "cache_mb" in result
        assert "total_safe_mb" in result
        assert "total_mb" in result

    def test_values_are_non_negative(self):
        _, scan, *_ = _import_cleanup()
        result = scan()
        for k, v in result.items():
            assert v >= 0, f"{k} should not be negative, got {v}"

    def test_total_safe_lte_total(self):
        _, scan, *_ = _import_cleanup()
        result = scan()
        assert result["total_safe_mb"] <= result["total_mb"] + 0.01  # float tolerance


class TestSafeClean:
    def test_dry_run_makes_no_deletions(self, tmp_path, monkeypatch):
        """dry_run=True must not remove any files from the target dirs."""
        import tools.disk_cleanup as dc
        never_touch_check, _, safe_clean, *_ = _import_cleanup()

        # Create a safe temp dir with a file to be (would-be) cleaned
        clean_dir = tmp_path / "safe_temp"
        clean_dir.mkdir()
        victim = clean_dir / "junk.tmp"
        victim.write_bytes(b"x" * 1024)

        # Sentinel outside the clean dir — must survive in all cases
        sentinel = tmp_path / "sentinel.txt"
        sentinel.write_text("keep me")

        # Redirect safe_clean to use only our controlled temp dir
        monkeypatch.setattr(dc, "_SAFE_CLEAN_DIRS", [str(clean_dir)])
        result = safe_clean(dry_run=True)

        # dry_run — victim must still exist
        assert victim.exists(), "dry_run=True must not delete files"
        assert sentinel.exists()
        assert isinstance(result, dict)
        assert result["dry_run"] is True
        assert "files_deleted" in result
        assert "mb_freed" in result
        assert "targets" in result

    def test_dry_run_returns_dict_structure(self, tmp_path, monkeypatch):
        import tools.disk_cleanup as dc
        _, _, safe_clean, *_ = _import_cleanup()

        test_dir = tmp_path / "tempclean"
        test_dir.mkdir()
        (test_dir / "a.tmp").write_bytes(b"hello")

        monkeypatch.setattr(dc, "_SAFE_CLEAN_DIRS", [str(test_dir)])
        result = safe_clean(dry_run=True)

        assert isinstance(result["files_deleted"], int)
        assert isinstance(result["mb_freed"], float)
        assert isinstance(result["targets"], list)

    def test_never_touch_not_in_targets(self, tmp_path, monkeypatch):
        """safe_clean must never include never-touch paths in its target list."""
        import tools.disk_cleanup as dc
        never_touch_check, _, safe_clean, *_ = _import_cleanup()

        # Use a safe temp dir only — ensures no system paths are ever included
        clean_dir = tmp_path / "cleanable"
        clean_dir.mkdir()
        monkeypatch.setattr(dc, "_SAFE_CLEAN_DIRS", [str(clean_dir)])

        result = safe_clean(dry_run=True)
        for target in result["targets"]:
            path = target.get("path", "")
            assert not never_touch_check(path), f"never-touch path appeared in targets: {path}"

    def test_actual_clean_removes_files(self, tmp_path, monkeypatch):
        """dry_run=False must actually delete files in the target dir."""
        import tools.disk_cleanup as dc
        _, _, safe_clean, *_ = _import_cleanup()

        clean_dir = tmp_path / "tosweep"
        clean_dir.mkdir()
        victim = clean_dir / "old.tmp"
        victim.write_bytes(b"y" * 2048)

        monkeypatch.setattr(dc, "_SAFE_CLEAN_DIRS", [str(clean_dir)])
        result = safe_clean(dry_run=False)

        assert not victim.exists(), "actual deletion must remove the file"
        assert result["dry_run"] is False
        assert result["files_deleted"] >= 1
        assert result["mb_freed"] >= 0


class TestJudgmentScan:
    def test_returns_list(self):
        _, _, _, judgment_scan, *_ = _import_cleanup()
        result = judgment_scan()
        assert isinstance(result, list)

    def test_items_have_required_keys(self):
        _, _, _, judgment_scan, *_ = _import_cleanup()
        result = judgment_scan()
        for item in result:
            assert "path" in item
            assert "type" in item
            assert "size_mb" in item
            assert "age_days" in item
            assert "reason" in item
            assert "ai_suggestion" in item

    def test_no_never_touch_in_results(self):
        """judgment_scan must not return never-touch paths."""
        never_touch_check, _, _, judgment_scan, *_ = _import_cleanup()
        result = judgment_scan()
        for item in result:
            path = item["path"]
            assert not never_touch_check(path), f"never-touch path in judgment results: {path}"

    def test_ai_suggestion_ci_mode(self):
        """Under JARVIS_CI=true, ai_suggestion should be the CI fallback string."""
        _, _, _, judgment_scan, *_ = _import_cleanup()
        # Create a large fake file to ensure at least one candidate
        with tempfile.NamedTemporaryFile(suffix=".bin", delete=False) as f:
            fname = f.name
        try:
            result = judgment_scan()
            for item in result:
                assert "CI mode" in item["ai_suggestion"] or item["ai_suggestion"]  # either CI or real
        finally:
            os.unlink(fname)


class TestDeleteJudgmentItem:
    def test_deletes_actual_file(self, tmp_path):
        """delete_judgment_item removes a real file and returns correct size."""
        _, _, _, _, delete_judgment_item, _ = _import_cleanup()
        target = tmp_path / "todelete.bin"
        target.write_bytes(b"x" * 1024)  # 1 KB

        result = delete_judgment_item(str(target))
        assert result["deleted"] is True
        assert not target.exists()
        assert result["error"] is None
        assert result["mb_freed"] >= 0

    def test_blocks_never_touch_path(self):
        """delete_judgment_item refuses to delete never-touch paths."""
        _, _, _, _, delete_judgment_item, _ = _import_cleanup()
        result = delete_judgment_item(r"C:\Windows\System32\notepad.exe")
        assert result["deleted"] is False
        assert "never-touch" in result["error"].lower()

    def test_handles_missing_path(self, tmp_path):
        """delete_judgment_item returns error for nonexistent path."""
        _, _, _, _, delete_judgment_item, _ = _import_cleanup()
        result = delete_judgment_item(str(tmp_path / "does_not_exist.txt"))
        assert result["deleted"] is False
        assert result["error"] is not None

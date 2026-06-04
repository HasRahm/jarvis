"""
tests/test_phase10_adaptive.py
Phase 10 — Adaptive Learning & Cross-Session Knowledge Persistence

All tests run under JARVIS_CI=true:
  - No real LLM calls
  - No real GBrain calls
  - File I/O uses tempfile directories for full isolation
"""

import os
import json
import tempfile
import unittest
import importlib

# Force CI mode before any module import so adaptive_router never hits real APIs
os.environ["JARVIS_CI"] = "true"


def _make_isolated_router(tmp_dir: str):
    """
    Return a fresh adaptive_router module with _PREFS_PATH pointing at tmp_dir.
    Re-imports to reset module-level state between tests.
    """
    import agents.adaptive_router as ar
    ar._PREFS_PATH = os.path.join(tmp_dir, "learned_preferences.json")
    return ar


class TestLoadPreferencesDefaults(unittest.TestCase):
    """load_preferences() returns DEFAULT_PREFS structure when file is absent."""

    def test_load_prefs_defaults_when_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            ar = _make_isolated_router(tmp)
            prefs = ar.load_preferences()
            for key in ar.DEFAULT_PREFS:
                self.assertIn(key, prefs, f"Missing key: {key}")
            self.assertEqual(prefs["model_scores"], {})
            self.assertEqual(prefs["routing_overrides"], {})


class TestRecordOutcomeBuildsScores(unittest.TestCase):
    """After recording calls, model_scores accumulates correctly."""

    def test_record_outcome_builds_scores(self):
        with tempfile.TemporaryDirectory() as tmp:
            ar = _make_isolated_router(tmp)
            # Record 2 successes and 1 failure
            ar.record_model_outcome("backend", "claude-sonnet-4-6", True)
            ar.record_model_outcome("backend", "claude-sonnet-4-6", True)
            ar.record_model_outcome("backend", "claude-sonnet-4-6", False)

            prefs = ar.load_preferences()
            entry = prefs["model_scores"]["backend"]["claude-sonnet-4-6"]
            self.assertEqual(entry["successes"], 2)
            self.assertEqual(entry["failures"], 1)
            self.assertEqual(entry["total"], 3)


class TestOverrideSetAfterMinSamples(unittest.TestCase):
    """routing_overrides is populated once min_samples (5) is reached with high success."""

    def test_override_set_after_min_samples(self):
        with tempfile.TemporaryDirectory() as tmp:
            ar = _make_isolated_router(tmp)
            for _ in range(5):
                ar.record_model_outcome("frontend", "claude-sonnet-4-6", True)

            prefs = ar.load_preferences()
            self.assertEqual(
                prefs["routing_overrides"].get("frontend"),
                "claude-sonnet-4-6",
            )


class TestNoOverrideBelowMinSamples(unittest.TestCase):
    """routing_overrides stays empty if sample count < min_samples."""

    def test_no_override_below_min_samples(self):
        with tempfile.TemporaryDirectory() as tmp:
            ar = _make_isolated_router(tmp)
            for _ in range(4):
                ar.record_model_outcome("qa", "gpt-5.4", True)

            prefs = ar.load_preferences()
            self.assertNotIn("qa", prefs["routing_overrides"])


class TestGetAdaptiveModelCiReturnsNone(unittest.TestCase):
    """get_adaptive_model() always returns None when JARVIS_CI=true."""

    def test_get_adaptive_model_ci_returns_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            ar = _make_isolated_router(tmp)
            # Populate a real override manually
            prefs = ar.load_preferences()
            prefs["routing_overrides"]["backend"] = "gpt-5.4"
            with open(ar._PREFS_PATH, "w", encoding="utf-8") as f:
                json.dump(prefs, f)

            # Under CI the override must never be surfaced
            result = ar.get_adaptive_model("backend")
            self.assertIsNone(result)


class TestDailySummaryCp1252Safe(unittest.TestCase):
    """compute_daily_summary output encodes to CP1252 without error."""

    def test_daily_summary_cp1252_safe(self):
        with tempfile.TemporaryDirectory() as tmp:
            ar = _make_isolated_router(tmp)
            # Populate some fake scores
            ar.record_model_outcome("backend", "claude-sonnet-4-6", True)
            ar.record_model_outcome("backend", "claude-sonnet-4-6", True)
            ar.record_model_outcome("backend", "gpt-5.4", False)

            prefs = ar.load_preferences()
            summary = ar.compute_daily_summary(prefs)

            # Must be a non-empty string
            self.assertIsInstance(summary, str)
            self.assertTrue(len(summary) > 0)

            # Must encode to CP1252 without raising UnicodeEncodeError
            try:
                summary.encode("cp1252")
            except UnicodeEncodeError as e:
                self.fail(f"CP1252 encoding failed: {e}")


class TestDagRunCiCompletesWithoutCrash(unittest.TestCase):
    """run_dag() under JARVIS_CI=true returns a dict with a 'status' key."""

    def test_dag_run_ci_completes_without_crash(self):
        try:
            from core.orchestrator.dag import run_dag
        except ImportError as e:
            self.skipTest(f"dag import failed (expected in minimal env): {e}")

        result = run_dag("build a simple API endpoint for user registration")
        self.assertIsInstance(result, dict, "run_dag must return a dict")
        self.assertIn("status", result, "result dict must have 'status' key")


if __name__ == "__main__":
    unittest.main()

"""Phase 39 — autonomy + risky-action classifiers. CI-safe, pure logic."""
import os
import sys

os.environ.setdefault("JARVIS_CI", "true")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.orchestrator import exec_guard as eg


class TestDeferral:
    def test_recommended_next_steps_is_deferral(self):
        assert eg.is_deferral("Recommended next steps: 1. verify the page 2. extract listings")

    def test_you_can_now_is_deferral(self):
        assert eg.is_deferral("You can now run the app to see the result.")

    def test_i_suggest_you_is_deferral(self):
        assert eg.is_deferral("I suggest you verify the page then extract the jobs.")

    def test_completion_is_not_deferral(self):
        assert not eg.is_deferral("Done. Created index.html.")

    def test_status_report_is_not_deferral(self):
        assert not eg.is_deferral("The login form is complete and all fields validate correctly.")


class TestRisky:
    def test_destructive_shell_is_risky(self):
        risky, reason = eg.is_risky("run_command", {"command": r"del C:\important"})
        assert risky and reason

    def test_force_push_is_risky(self):
        risky, _ = eg.is_risky("run_command", {"command": "git push --force origin main"})
        assert risky

    def test_send_email_is_risky(self):
        risky, _ = eg.is_risky("send_email", {"to": "a@b.com", "body": "hi"})
        assert risky

    def test_read_is_not_risky(self):
        risky, _ = eg.is_risky("read_screen_text", {})
        assert not risky

    def test_click_is_not_risky(self):
        risky, _ = eg.is_risky("desktop_smooth_click", {"x": 10, "y": 20})
        assert not risky

    def test_navigate_is_not_risky(self):
        risky, _ = eg.is_risky("browser_navigate", {"url": "https://example.com"})
        assert not risky


class TestConstants:
    def test_max_continues_positive(self):
        assert eg.MAX_CONTINUES >= 1

    def test_active_window_title_ci_safe(self):
        # In CI it must return '' without touching the display.
        assert eg.active_window_title() == ""

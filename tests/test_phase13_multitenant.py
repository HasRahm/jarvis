"""
tests/test_phase13_multitenant.py — Phase 13: Multi-Tenancy Foundation

All tests run under JARVIS_CI=true (no real LLM / GBrain / E2B calls).
Covers:
  - Dual-mode auth (core.auth)
  - Orchestrator registry isolation (concurrent run_dag calls)
  - User-scoped workspace paths
  - E2B sandbox noop under JARVIS_CI
"""

import os
import sys
import threading
import tempfile
import pytest

# Ensure project root is on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("JARVIS_CI", "true")
os.environ.setdefault("HERMES_SECRET", "test-secret-13")


# ---------------------------------------------------------------------------
# core.auth tests
# ---------------------------------------------------------------------------

class TestAuthenticate:
    def test_self_hosted_valid(self):
        """Correct HERMES_SECRET -> (True, None)."""
        os.environ["HERMES_SECRET"] = "my-self-hosted-secret"
        os.environ.pop("SUPABASE_JWT_SECRET", None)
        from core.auth import authenticate
        ok, user_id = authenticate("my-self-hosted-secret")
        assert ok is True
        assert user_id is None

    def test_self_hosted_invalid(self):
        """Wrong token -> (False, None)."""
        os.environ["HERMES_SECRET"] = "my-self-hosted-secret"
        os.environ.pop("SUPABASE_JWT_SECRET", None)
        from core.auth import authenticate
        ok, user_id = authenticate("wrong-token")
        assert ok is False
        assert user_id is None

    def test_supabase_mode_bad_token(self):
        """With SUPABASE_JWT_SECRET set, a non-JWT token fails validation."""
        os.environ["SUPABASE_JWT_SECRET"] = "super-secret-jwt-key"
        try:
            from core.auth import authenticate
            ok, user_id = authenticate("not-a-real-jwt")
            assert ok is False
            assert user_id is None
        finally:
            del os.environ["SUPABASE_JWT_SECRET"]

    def test_default_secret_fallback(self):
        """Phase 22g fail-closed: when HERMES_SECRET is unset, ALL tokens are
        rejected — the old 'default_secret' constant must NOT authenticate."""
        os.environ.pop("HERMES_SECRET", None)
        os.environ.pop("SUPABASE_JWT_SECRET", None)
        from core.auth import authenticate
        ok, user_id = authenticate("default_secret")
        assert ok is False
        assert user_id is None
        # Restore
        os.environ["HERMES_SECRET"] = "test-secret-13"


# ---------------------------------------------------------------------------
# Workspace scoping tests
# ---------------------------------------------------------------------------

class TestWorkspaceScoping:
    def test_self_hosted_path(self):
        """user_id=None -> workspaces/<role>/"""
        from core.auth import get_workspace_path
        path = get_workspace_path("frontend", None)
        assert path.endswith(os.path.join("workspaces", "frontend"))

    def test_saas_path_includes_user_id(self):
        """user_id set -> workspaces/<user_id>/<role>/"""
        from core.auth import get_workspace_path
        path = get_workspace_path("frontend", "user-abc123")
        assert os.path.join("workspaces", "user-abc123", "frontend") in path

    def test_agents_md_self_hosted(self):
        """Self-hosted AGENTS.md at <root>/AGENTS.md."""
        from core.auth import get_agents_md_path
        path = get_agents_md_path(None)
        assert path.endswith("AGENTS.md")
        assert "workspaces" not in path

    def test_agents_md_saas(self):
        """SaaS AGENTS.md scoped to <root>/workspaces/<user_id>/AGENTS.md."""
        from core.auth import get_agents_md_path
        path = get_agents_md_path("user-xyz")
        assert os.path.join("workspaces", "user-xyz", "AGENTS.md") in path


# ---------------------------------------------------------------------------
# Orchestrator registry isolation
# ---------------------------------------------------------------------------

class TestOrchestratorRegistry:
    def test_two_runs_get_distinct_instances(self, tmp_path, monkeypatch):
        """Two concurrent run_dag() calls must not share ActiveOrchestrator state."""
        from core.orchestrator import dag as dag_module

        captured = {}
        barrier = threading.Barrier(2)

        original_register = dag_module.register_orchestrator

        def patched_register(task_id, orch):
            original_register(task_id, orch)
            captured[task_id] = orch
            barrier.wait(timeout=5)

        monkeypatch.setattr(dag_module, "register_orchestrator", patched_register)

        # Patch parse_task so no real LLM call is made
        monkeypatch.setattr(
            "core.orchestrator.task_parser.parse_task",
            lambda task: [
                {"id": "st1", "agent": "backend", "task": "stub task", "depends_on": []}
            ],
        )

        results = {}

        def run(tid):
            results[tid] = dag_module.run_dag("stub task", task_id=tid)

        t1 = threading.Thread(target=run, args=("task-aaa",))
        t2 = threading.Thread(target=run, args=("task-bbb",))
        t1.start()
        t2.start()
        t1.join(timeout=30)
        t2.join(timeout=30)

        # Both ran without crashing
        assert "task-aaa" in results
        assert "task-bbb" in results
        # Each registered a distinct orchestrator
        if "task-aaa" in captured and "task-bbb" in captured:
            assert captured["task-aaa"] is not captured["task-bbb"]

    def test_registry_cleaned_up_after_run(self, monkeypatch):
        """After run_dag() returns, the orchestrator is removed from the registry."""
        from core.orchestrator import dag as dag_module

        monkeypatch.setattr(
            "core.orchestrator.task_parser.parse_task",
            lambda task: [
                {"id": "st-cleanup", "agent": "backend", "task": "cleanup test", "depends_on": []}
            ],
        )

        tid = "task-cleanup-test"
        dag_module.run_dag("cleanup test", task_id=tid)

        with dag_module._orchestrators_lock:
            assert tid not in dag_module._orchestrators


# ---------------------------------------------------------------------------
# E2B sandbox noop tests
# ---------------------------------------------------------------------------

class TestSandboxNoop:
    def test_create_returns_none_in_ci(self):
        """create_sandbox always returns None under JARVIS_CI=true."""
        from tools.sandbox import create_sandbox
        result = create_sandbox("task-noop-1")
        assert result is None

    def test_destroy_noop_with_none(self):
        """destroy_sandbox(None, ...) is a no-op — must not raise."""
        from tools.sandbox import destroy_sandbox
        destroy_sandbox(None, "task-noop-2")  # should not raise

    def test_run_in_sandbox_none_returns_empty(self):
        """run_in_sandbox(None, ...) returns '' so caller falls through to local."""
        from tools.sandbox import run_in_sandbox
        result = run_in_sandbox(None, "echo hello")
        assert result == ""

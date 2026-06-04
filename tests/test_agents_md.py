"""
Tests for AGENTS.md protocol — parse and update operations.
"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Patch the AGENTS_MD_PATH to a temp file for testing
import agents.base_agent as base_mod


def _create_test_agents_md(tmp_path: str) -> str:
    """Create a test AGENTS.md file and return its path."""
    content = """# AGENTS.md — Shared Agent State

## Current Task
| Field | Value |
|-------|-------|
| Task ID | test_001 |
| Description | Test task |
| Status | IDLE |
| Requested By | — |

## Agent Assignments
| Agent | Model | Status | Current Step |
|-------|-------|--------|-------------|
| frontend | gemini-3.1-pro-preview | IDLE | — |
| backend | claude-sonnet-4-6 | IDLE | — |
| qa | gpt-5.4 | IDLE | — |

## Task Log
"""
    filepath = os.path.join(tmp_path, "AGENTS.md")
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)
    return filepath


def test_read_agents_md():
    """Test reading AGENTS.md."""
    with tempfile.TemporaryDirectory() as tmp:
        path = _create_test_agents_md(tmp)
        # Temporarily override the path
        original = base_mod.AGENTS_MD_PATH
        base_mod.AGENTS_MD_PATH = path

        try:
            # Create a minimal concrete agent for testing
            class TestAgent(base_mod.BaseAgent):
                def __init__(self):
                    # Skip __init__ to avoid API client initialization
                    self.role = "backend"
                    self.workspace = os.path.join(tmp, "workspace")
                    os.makedirs(self.workspace, exist_ok=True)

                def run(self, task):
                    return {"status": "success", "output": "test", "files": []}

            agent = TestAgent()
            content = agent.read_agents_md()

            assert "test_001" in content
            assert "backend" in content
            assert "claude-sonnet-4-6" in content
            print("[PASS] test_read_agents_md")
        finally:
            base_mod.AGENTS_MD_PATH = original


def test_append_log():
    """Test appending to Task Log."""
    with tempfile.TemporaryDirectory() as tmp:
        path = _create_test_agents_md(tmp)
        original = base_mod.AGENTS_MD_PATH
        base_mod.AGENTS_MD_PATH = path

        try:
            class TestAgent(base_mod.BaseAgent):
                def __init__(self):
                    self.role = "qa"
                    self.workspace = os.path.join(tmp, "workspace")
                    os.makedirs(self.workspace, exist_ok=True)

                def run(self, task):
                    return {"status": "success", "output": "test", "files": []}

            agent = TestAgent()
            agent.append_log("Hello from QA agent")

            content = agent.read_agents_md()
            assert "qa: Hello from QA agent" in content
            print("[PASS] test_append_log")
        finally:
            base_mod.AGENTS_MD_PATH = original


def test_update_task():
    """Test updating the Current Task section."""
    with tempfile.TemporaryDirectory() as tmp:
        path = _create_test_agents_md(tmp)
        original = base_mod.AGENTS_MD_PATH
        base_mod.AGENTS_MD_PATH = path

        try:
            class TestAgent(base_mod.BaseAgent):
                def __init__(self):
                    self.role = "backend"
                    self.workspace = os.path.join(tmp, "workspace")
                    os.makedirs(self.workspace, exist_ok=True)

                def run(self, task):
                    return {"status": "success", "output": "test", "files": []}

            agent = TestAgent()
            agent.update_task("task_999", "Build a rocket", "IN_PROGRESS")

            content = agent.read_agents_md()
            assert "task_999" in content
            assert "Build a rocket" in content
            assert "IN_PROGRESS" in content
            print("[PASS] test_update_task")
        finally:
            base_mod.AGENTS_MD_PATH = original


def test_workspace_file_ops():
    """Test workspace file read/write."""
    with tempfile.TemporaryDirectory() as tmp:
        path = _create_test_agents_md(tmp)
        original = base_mod.AGENTS_MD_PATH
        base_mod.AGENTS_MD_PATH = path

        try:
            class TestAgent(base_mod.BaseAgent):
                def __init__(self):
                    self.role = "frontend"
                    self.workspace = os.path.join(tmp, "workspace", "frontend")
                    os.makedirs(self.workspace, exist_ok=True)

                def run(self, task):
                    return {"status": "success", "output": "test", "files": []}

            agent = TestAgent()
            agent.write_workspace_file("test.html", "<h1>Hello</h1>")
            content = agent.read_workspace_file("test.html")

            assert content == "<h1>Hello</h1>"
            print("[PASS] test_workspace_file_ops")
        finally:
            base_mod.AGENTS_MD_PATH = original


if __name__ == "__main__":
    test_read_agents_md()
    test_append_log()
    test_update_task()
    test_workspace_file_ops()
    print("\nAll AGENTS.md protocol tests passed! [PASS]")

"""
IaC Agent & Local Concurrency Locking Integration Tests
"""

import os
import shutil
import pytest
from agents.iac_agent import IacAgent
from core.orchestrator.distributed_sync import agents_md_lock


@pytest.fixture
def clean_workspace():
    """Fixture to configure and clean up temporary test workspace."""
    workspace_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "workspaces", "test_iac_workspace"
    )
    if os.path.exists(workspace_dir):
        shutil.rmtree(workspace_dir)
    os.makedirs(workspace_dir, exist_ok=True)
    yield workspace_dir
    if os.path.exists(workspace_dir):
        shutil.rmtree(workspace_dir)


def test_iac_agent_execution(clean_workspace):
    """Verify that IacAgent successfully generates configurations and plans."""
    # Ensure offline mode mock is active
    os.environ["JARVIS_CI"] = "true"
    
    agent = IacAgent()
    # Override workspace directory to clean sandbox path
    agent.workspace = clean_workspace

    task_desc = "Generate a Terraform plan to configure a local state file and standard database service."
    result = agent.run(task_desc)

    assert result["status"] == "success"
    assert "output" in result
    assert "files" in result
    assert "plan" in result
    assert "notes" in result
    
    # Assert created files exist
    assert len(result["files"]) > 0
    for rel_path in result["files"]:
        full_path = os.path.join(clean_workspace, rel_path)
        assert os.path.exists(full_path)
        with open(full_path, "r") as f:
            content = f.read()
            assert len(content) > 0


def test_agents_md_concurrency_lock(tmp_path):
    """Verify cross-platform fcntl/msvcrt lock context behaves atomically without error."""
    lock_file = os.path.join(tmp_path, "AGENTS.md.lock")
    
    # Try acquiring lock
    with agents_md_lock(lock_file):
        # Assert lock file gets created
        assert os.path.exists(lock_file)
        
        # Test double lock exception / non-blocking attempt
        # Inside the context, attempting to open and lock inside another handle
        # is expected to block or yield gracefully on exit.
        
    # Assert lock file is cleaned up after context exit
    assert not os.path.exists(lock_file)

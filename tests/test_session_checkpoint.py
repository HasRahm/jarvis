import pytest
import json
from unittest.mock import MagicMock, patch
from core.orchestrator.session import SessionManager

@patch("core.orchestrator.session.brain_write")
def test_checkpoint(mock_write):
    sm = SessionManager()
    state = {
        "current_index": 1,
        "status": "incomplete",
        "execution_list": [{"id": "sub_1", "task": "do something"}],
        "user_task": "test task",
        "results": [],
        "all_files": []
    }
    
    sm.checkpoint("test_session_1", state)
    
    mock_write.assert_called_once()
    args = mock_write.call_args[0]
    assert args[0] == "sessions/test_session_1/checkpoint"
    data = json.loads(args[1])
    assert data["session_id"] == "test_session_1"
    assert data["status"] == "incomplete"
    assert data["dag_position"] == 1

@patch("core.orchestrator.session.brain_write")
def test_mark_completed(mock_write):
    sm = SessionManager()
    state = {
        "current_index": 2,
        "status": "completed",
        "execution_list": [{"id": "sub_1", "task": "do something"}],
        "user_task": "test task",
        "results": [],
        "all_files": []
    }
    
    sm.mark_completed("test_session_1", state)
    
    mock_write.assert_called_once()
    args = mock_write.call_args[0]
    assert args[0] == "sessions/test_session_1/checkpoint"
    data = json.loads(args[1])
    assert data["status"] == "completed"

@patch("core.orchestrator.session.subprocess.run")
@patch("core.orchestrator.session.brain_get")
def test_recover_no_sessions(mock_get, mock_run):
    # Simulate empty gbrain list output
    mock_proc = MagicMock()
    mock_proc.returncode = 0
    mock_proc.stdout = ""
    mock_run.return_value = mock_proc
    
    # Force _GBRAIN_PATH mock
    with patch("brain.write._GBRAIN_PATH", "mock_gbrain"):
        sm = SessionManager()
        assert sm.recover() is None

@patch("core.orchestrator.session.subprocess.run")
@patch("core.orchestrator.session.brain_get")
def test_recover_success(mock_get, mock_run):
    # Simulate gbrain list returning one checkpoint
    mock_proc = MagicMock()
    mock_proc.returncode = 0
    mock_proc.stdout = "sessions/test_session_1/checkpoint [page] 2026-06-04 22:04:11\n"
    mock_run.return_value = mock_proc
    
    # Return incomplete checkpoint content
    mock_get.return_value = json.dumps({
        "session_id": "test_session_1",
        "status": "incomplete",
        "state": {
            "current_index": 0,
            "user_task": "resume task",
            "execution_list": [{"id": "sub_1", "task": "do something", "agent": "backend", "depends_on": []}]
        }
    })
    
    with patch("brain.write._GBRAIN_PATH", "mock_gbrain"):
        sm = SessionManager()
        recovered = sm.recover()
        assert recovered is not None
        assert recovered["session_id"] == "test_session_1"
        assert recovered["status"] == "incomplete"

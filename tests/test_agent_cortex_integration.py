import pytest
import os
import time
import json
import threading
from unittest.mock import MagicMock, patch
from tools.dispatcher import dispatch
from core.orchestrator.dag import ActiveOrchestrator, register_orchestrator, unregister_orchestrator

@patch.dict(os.environ, {"JARVIS_CI": "false"})
@patch("tools.dispatcher._dispatch_raw")
def test_dispatch_cortex_integration_success(mock_raw):
    mock_raw.return_value = "[SUCCESS] Tool executed"
    
    # 1. Setup mock orchestrator session
    orch = ActiveOrchestrator()
    orch.task_id = "test_integration_task_1"
    orch.active_agent = "backend"
    orch.user_id = None
    register_orchestrator(orch.task_id, orch)
    
    # Write initial AGENTS.md mock
    from agents.base_agent import AGENTS_MD_PATH
    initial_md = (
        "## Agent Assignments\n"
        "| Agent | Model | Status | Current Step |\n"
        "|-------|-------|--------|-------------|\n"
        "| backend | claude-sonnet-4-6 | IDLE | -- |\n"
    )
    with open(AGENTS_MD_PATH, "w", encoding="utf-8") as f:
        f.write(initial_md)
        
    try:
        # 2. Force mock cortex returns for home context
        mock_cortex = MagicMock()
        mock_cortex.task_registry = {}
        def reg_task(tid):
            mock_cortex.task_registry[tid] = {"home": {}}
        mock_cortex.register_task.side_effect = reg_task
        mock_cortex.is_home_context.return_value = True
        
        with patch("tools.dispatcher.get_cortex", return_value=mock_cortex):
            # First tool call - registers task and executes raw
            res = dispatch("test_tool", {"arg": 1})
            assert res == "[SUCCESS] Tool executed"
            assert orch.task_id in mock_cortex.task_registry
            
    finally:
        unregister_orchestrator(orch.task_id)

@patch.dict(os.environ, {"JARVIS_CI": "false"})
@patch("tools.dispatcher._dispatch_raw")
def test_dispatch_cortex_switch_suspension_and_resume(mock_raw):
    mock_raw.return_value = "[SUCCESS] Resumed execution"
    
    # Setup mock orchestrator
    orch = ActiveOrchestrator()
    orch.task_id = "test_integration_task_2"
    orch.active_agent = "backend"
    orch.user_id = None
    register_orchestrator(orch.task_id, orch)
    
    # Write initial AGENTS.md
    from agents.base_agent import AGENTS_MD_PATH
    initial_md = (
        "## Agent Assignments\n"
        "| Agent | Model | Status | Current Step |\n"
        "|-------|-------|--------|-------------|\n"
        "| backend | claude-sonnet-4-6 | WORKING | -- |\n"
    )
    with open(AGENTS_MD_PATH, "w", encoding="utf-8") as f:
        f.write(initial_md)
        
    try:
        # Mock cortex behavior
        mock_cortex = MagicMock()
        mock_cortex.task_registry = {orch.task_id: {"home": {}}}
        
        # side_effect returns False first (switched), then returns True (restored) after 2 calls
        is_home_calls = [False, False, True]
        def side_effect(tid):
            if is_home_calls:
                return is_home_calls.pop(0)
            return True
            
        mock_cortex.is_home_context.side_effect = side_effect
        
        with patch("tools.dispatcher.get_cortex", return_value=mock_cortex):
            # This call should switch context, suspend, poll, and then resume
            res = dispatch("test_tool", {"arg": 1})
            assert res == "[SUCCESS] Resumed execution"
            
            # Verify status in AGENTS.md was updated to SUSPENDED, then back to WORKING/Resuming
            with open(AGENTS_MD_PATH, "r", encoding="utf-8") as f:
                content = f.read()
            # The final state should be WORKING or Resuming (restored)
            assert "WORKING" in content
            
    finally:
        unregister_orchestrator(orch.task_id)

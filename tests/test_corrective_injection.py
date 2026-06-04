import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import core.orchestrator.dag as dag_mod

# Ensure we have an active orchestrator instance for testing
if dag_mod.active_orchestrator is None:
    dag_mod.active_orchestrator = dag_mod.ActiveOrchestrator()

def test_corrective_subtask_injection_case_a():
    # Setup standard orchestrator state
    orch = dag_mod.active_orchestrator
    orch.reset()
    
    orch.is_running = True
    orch.active_agent = "frontend"
    orch.current_index = 0
    orch.execution_list = [
        {
            "id": "node_1",
            "agent": "frontend",
            "task": "Create a frontend view",
            "depends_on": []
        }
    ]
    
    selector = "#submit-btn"
    instruction = "make background red"
    
    # Inject subtask (Case a: active target agent frontend running)
    orch.inject_corrective_subtask(selector, instruction)
    
    # Check that corrective node was injected before current_index
    assert len(orch.execution_list) == 2
    assert orch.execution_list[0]["agent"] == "frontend"
    assert "Self-Correction" in orch.execution_list[0]["task"]
    assert orch.is_interrupted is True

def test_corrective_subtask_injection_case_b():
    # Setup standard orchestrator state
    orch = dag_mod.active_orchestrator
    orch.reset()
    
    orch.is_running = True
    orch.active_agent = "backend"
    orch.current_index = 1
    orch.execution_list = [
        {
            "id": "frontend",
            "agent": "frontend",
            "task": "Create frontend",
            "depends_on": []
        },
        {
            "id": "backend",
            "agent": "backend",
            "task": "Create backend",
            "depends_on": ["frontend"]
        }
    ]
    
    selector = "#submit-btn"
    instruction = "make background red"
    
    # Inject subtask (Case b: target frontend completed, downstream backend running)
    orch.inject_corrective_subtask(selector, instruction)
    
    # Check that corrective node and frontend retry were injected at current_index
    assert len(orch.execution_list) == 4
    assert orch.execution_list[1]["agent"] == "frontend"
    assert "Self-Correction" in orch.execution_list[1]["task"]
    assert orch.execution_list[2]["agent"] == "frontend"
    assert "Re-execute" in orch.execution_list[2]["task"]
    assert orch.is_interrupted is True

def test_corrective_subtask_injection_case_c():
    # Setup standard orchestrator state
    orch = dag_mod.active_orchestrator
    orch.reset()
    
    orch.is_running = False
    orch.active_agent = None
    orch.current_index = -1
    orch.execution_list = []
    
    selector = "#submit-btn"
    instruction = "make background red"
    
    # Inject subtask (Case c: idle)
    orch.inject_corrective_subtask(selector, instruction)
    
    # Check that corrective node was appended
    assert len(orch.execution_list) == 1
    assert orch.execution_list[0]["agent"] == "frontend"
    assert "Self-Correction" in orch.execution_list[0]["task"]

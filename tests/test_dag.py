"""
Tests for the DAG Orchestrator — dependency resolution and topological sort.
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.orchestrator.dag import _topological_sort


def test_topological_sort_simple():
    """Test a simple linear dependency chain."""
    subtasks = [
        {"id": "sub_3", "agent": "qa", "task": "Review", "depends_on": ["sub_2"]},
        {"id": "sub_1", "agent": "backend", "task": "DB schema", "depends_on": []},
        {"id": "sub_2", "agent": "backend", "task": "API route", "depends_on": ["sub_1"]},
    ]

    ordered = _topological_sort(subtasks)
    
    assert len(ordered) == 3
    assert ordered[0]["id"] == "sub_1"
    assert ordered[1]["id"] == "sub_2"
    assert ordered[2]["id"] == "sub_3"
    print("[PASS] test_topological_sort_simple")


def test_topological_sort_complex():
    """Test a complex graph with multiple independent starting nodes."""
    subtasks = [
        {"id": "qa", "agent": "qa", "task": "Test both", "depends_on": ["frontend", "backend"]},
        {"id": "backend", "agent": "backend", "task": "Build API", "depends_on": ["db"]},
        {"id": "db", "agent": "backend", "task": "Schema", "depends_on": []},
        {"id": "frontend", "agent": "frontend", "task": "Build UI", "depends_on": ["backend"]},
    ]

    ordered = _topological_sort(subtasks)
    
    assert len(ordered) == 4
    # db must be first
    assert ordered[0]["id"] == "db"
    # qa must be last
    assert ordered[-1]["id"] == "qa"
    # frontend must come after backend
    backend_idx = next(i for i, st in enumerate(ordered) if st["id"] == "backend")
    frontend_idx = next(i for i, st in enumerate(ordered) if st["id"] == "frontend")
    assert frontend_idx > backend_idx
    
    print("[PASS] test_topological_sort_complex")


def test_topological_sort_circular():
    """Test that circular dependencies are caught."""
    subtasks = [
        {"id": "sub_1", "agent": "backend", "task": "A", "depends_on": ["sub_2"]},
        {"id": "sub_2", "agent": "frontend", "task": "B", "depends_on": ["sub_1"]},
    ]

    try:
        _topological_sort(subtasks)
        assert False, "Should have raised ValueError for circular dependency"
    except ValueError as e:
        assert "Circular dependency detected" in str(e)
        print("[PASS] test_topological_sort_circular")


if __name__ == "__main__":
    test_topological_sort_simple()
    test_topological_sort_complex()
    test_topological_sort_circular()
    print("\nAll DAG tests passed! [PASS]")

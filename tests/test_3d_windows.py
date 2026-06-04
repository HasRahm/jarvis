import pytest
from unittest.mock import MagicMock, patch
from tools.windows import get_window_stack, find_occlusions, get_3d_window_graph

def test_find_occlusions():
    # Define a custom stack with overlapping windows
    stack = [
        {"title": "Dialog", "x": 100, "y": 100, "w": 200, "h": 200, "depth": 0},
        {"title": "Browser", "x": 150, "y": 150, "w": 400, "h": 400, "depth": 1},
        {"title": "VS Code", "x": 500, "y": 500, "w": 400, "h": 400, "depth": 2}
    ]
    
    occlusions = find_occlusions(stack)
    
    # Dialog (depth 0) overlaps Browser (depth 1) in the rect [150, 150, 300, 300]
    # Intersection is x:150, y:150, w:150, h:150
    assert len(occlusions) > 0
    
    browser_blocked = [o for o in occlusions if o["blocked_window"] == "Browser"]
    assert len(browser_blocked) == 1
    assert browser_blocked[0]["blocking_window"] == "Dialog"
    assert browser_blocked[0]["intersection"] == {"x": 150, "y": 150, "w": 150, "h": 150}
    
    # VS Code and Dialog do not overlap (VS Code is at [500, 500], Dialog is at [100, 100])
    vs_code_blocked_by_dialog = [o for o in occlusions if o["blocked_window"] == "VS Code" and o["blocking_window"] == "Dialog"]
    assert len(vs_code_blocked_by_dialog) == 0

@patch("tools.windows.ctypes")
@patch("tools.windows.pyautogui.position")
def test_get_3d_window_graph(mock_position, mock_ctypes):
    mock_position.return_value = (100, 200)
    
    # Mock ctypes.windll.user32.GetTopWindow to return None (no windows)
    mock_user32 = mock_ctypes.windll.user32
    mock_user32.GetTopWindow.return_value = None
    
    graph = get_3d_window_graph()
    
    assert graph["agent_position"] == {"x": 100, "y": 200, "z": 0}
    assert isinstance(graph["nodes"], list)
    assert isinstance(graph["blocked_paths"], list)
    assert graph["navigation_plan"] == []

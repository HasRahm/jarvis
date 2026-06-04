import pytest
from unittest.mock import MagicMock, patch
from tools.desktop_automation import desktop_get_active_window, desktop_focus_window

@patch("tools.desktop_automation.gw")
def test_desktop_get_active_window_success(mock_gw):
    # Mock active window returning a valid window title
    mock_win = MagicMock()
    mock_win.title = "silabser.inf - Notepad"
    mock_gw.getActiveWindow.return_value = mock_win
    
    result = desktop_get_active_window()
    assert "silabser.inf - Notepad" in result
    assert "Active Window:" in result

@patch("tools.desktop_automation.gw")
def test_desktop_get_active_window_none(mock_gw):
    # Mock active window returning None
    mock_gw.getActiveWindow.return_value = None
    
    result = desktop_get_active_window()
    assert "No active window detected" in result

@patch("tools.desktop_automation.gw")
def test_desktop_focus_window_success_minimized(mock_gw):
    # Setup mock windows
    mock_win = MagicMock()
    mock_win.title = "Microsoft PowerPoint - Butterflies"
    mock_win.isMinimized = True
    
    mock_gw.getAllWindows.return_value = [mock_win]
    mock_gw.getActiveWindow.return_value = mock_win
    
    result = desktop_focus_window("PowerPoint")
    
    # Assert window restore and activation were triggered
    mock_win.restore.assert_called_once()
    mock_win.activate.assert_called_once()
    assert "Successfully focused window" in result
    assert "Microsoft PowerPoint - Butterflies" in result

@patch("tools.desktop_automation.gw")
def test_desktop_focus_window_success_not_minimized(mock_gw):
    # Setup mock windows
    mock_win = MagicMock()
    mock_win.title = "Google Chrome"
    mock_win.isMinimized = False
    
    mock_gw.getAllWindows.return_value = [mock_win]
    mock_gw.getActiveWindow.return_value = mock_win
    
    result = desktop_focus_window("chrome")
    
    # Assert activate was called, but restore was NOT called
    mock_win.restore.assert_not_called()
    mock_win.activate.assert_called_once()
    assert "Successfully focused window" in result
    assert "Google Chrome" in result

@patch("tools.desktop_automation.gw")
def test_desktop_focus_window_not_found(mock_gw):
    # Mock empty window list
    mock_gw.getAllWindows.return_value = []
    
    result = desktop_focus_window("Excel")
    assert "ERROR: No open window found matching" in result

import pytest
from unittest.mock import MagicMock, patch
from tools.desktop_automation import desktop_smooth_click

@patch("tools.desktop_automation._get_pyautogui")
def test_desktop_smooth_click_clamps_when_window_bounds_provided(mock_get_pyautogui):
    # Mock pyautogui
    mock_pyautogui = MagicMock()
    mock_pyautogui.position.return_value = (150, 150)
    mock_get_pyautogui.return_value = mock_pyautogui

    bounds = {"x": 100, "y": 100, "w": 500, "h": 500}

    # Call with coordinates completely outside the window bounds
    # Left border: wx + margin = 100 + 8 = 108
    # Top border: wy + margin = 100 + 8 = 108
    desktop_smooth_click(50, 50, duration=0.1, window_bounds=bounds)

    # Verify pyautogui click was called with clamped values
    mock_pyautogui.moveTo.assert_called_once_with(108, 108, duration=0.1, tween=mock_pyautogui.easeInOutQuad)
    mock_pyautogui.click.assert_called_once()


@patch("tools.desktop_automation._get_pyautogui")
def test_desktop_smooth_click_does_not_clamp_when_no_bounds_provided(mock_get_pyautogui):
    # Mock pyautogui
    mock_pyautogui = MagicMock()
    mock_pyautogui.position.return_value = (150, 150)
    mock_get_pyautogui.return_value = mock_pyautogui

    # Call without window bounds
    desktop_smooth_click(50, 50, duration=0.1)

    # Verify click was at the original coordinates
    mock_pyautogui.moveTo.assert_called_once_with(50, 50, duration=0.1, tween=mock_pyautogui.easeInOutQuad)


@patch("tools.desktop_automation._get_pyautogui")
def test_desktop_smooth_click_does_not_clamp_in_bounds(mock_get_pyautogui):
    # Mock pyautogui
    mock_pyautogui = MagicMock()
    mock_pyautogui.position.return_value = (150, 150)
    mock_get_pyautogui.return_value = mock_pyautogui

    bounds = {"x": 100, "y": 100, "w": 500, "h": 500}

    # Call with coordinates inside window bounds
    desktop_smooth_click(300, 300, duration=0.1, window_bounds=bounds)

    # Verify click was at the original coordinates
    mock_pyautogui.moveTo.assert_called_once_with(300, 300, duration=0.1, tween=mock_pyautogui.easeInOutQuad)


@patch("tools.desktop_automation._get_pyautogui")
@patch("tools.desktop_automation._get_gw")
@patch("tools.windows.get_window_stack")
@patch("tools.windows.find_occlusions")
@patch("tools.desktop_automation.desktop_focus_window")
def test_desktop_smooth_click_window_tracker_translates_and_refocuses(
    mock_focus_window, mock_find_occlusions, mock_get_window_stack, mock_get_gw, mock_get_pyautogui
):
    # Mock pyautogui
    mock_pyautogui = MagicMock()
    mock_pyautogui.position.return_value = (150, 150)
    mock_get_pyautogui.return_value = mock_pyautogui

    # Mock pygetwindow active window
    mock_gw = MagicMock()
    mock_win = MagicMock()
    mock_win.title = "Notepad"
    mock_gw.getActiveWindow.return_value = mock_win
    mock_get_gw.return_value = mock_gw

    # Target window initially declared at (100, 100)
    bounds = {"title": "Notepad", "x": 100, "y": 100, "w": 500, "h": 500}

    # Stack reports the window moved to (200, 250)
    mock_get_window_stack.return_value = [
        {"title": "Notepad", "x": 200, "y": 250, "w": 500, "h": 500}
    ]
    # Mock occlusion detection (Notepad is occluded by Chrome)
    mock_find_occlusions.return_value = [
        {"blocked_window": "Notepad", "blocking_window": "Chrome"}
    ]

    # Target coordinate: (150, 150) — inside old bounds.
    # Shift vector is (+100, +150) -> Translated coordinate should be (250, 300).
    desktop_smooth_click(150, 150, duration=0.1, window_bounds=bounds)

    # Verify coordinate translation
    mock_pyautogui.moveTo.assert_called_once_with(250, 300, duration=0.1, tween=mock_pyautogui.easeInOutQuad)
    
    # Verify bounds updated in-place
    assert bounds["x"] == 200
    assert bounds["y"] == 250

    # Verify refocuser triggered due to occlusion
    mock_focus_window.assert_called_once_with("Notepad")

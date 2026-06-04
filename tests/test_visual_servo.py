import pytest
import os
from unittest.mock import MagicMock, patch
import numpy as np

# Set environment variable to force headless mock/fallback mode for tests
os.environ["JARVIS_CI"] = "true"

from tools.visual_servo import is_graphical_env_available, visual_servo_click

def test_visual_servo_fallback_in_headless_env():
    # In headless/CI mode, is_graphical_env_available should return False
    assert is_graphical_env_available() is False
    
    # In headless/CI mode, visual_servo_click should automatically return True fallback
    success = visual_servo_click("non_existent_template.png")
    assert success is True

@patch("tools.visual_servo.os.environ")
@patch("tools.visual_servo._lazy_load")
@patch("tools.visual_servo.ImageGrab")
def test_visual_servo_graphical_detection(mock_image_grab, mock_lazy_load, mock_environ):
    # Mock environment to simulate active GUI display available
    mock_environ.get.return_value = "false"
    mock_image_grab.grab.return_value = MagicMock()
    
    assert is_graphical_env_available() is True
    mock_lazy_load.assert_called_once()
    mock_image_grab.grab.assert_called_once()

@patch("tools.visual_servo.os.environ")
@patch("tools.visual_servo._lazy_load")
@patch("tools.visual_servo.ImageGrab")
@patch("tools.visual_servo.cv2")
@patch("tools.visual_servo.pyautogui")
@patch("tools.visual_servo.os.path.exists")
def test_visual_servo_click_loop_convergence(
    mock_exists, mock_pyautogui, mock_cv2, mock_image_grab, mock_lazy_load, mock_environ
):
    # Setup mocks for active GUI mode
    mock_environ.get.return_value = "false"
    mock_exists.return_value = True
    
    # Mock loaded template size (40x40)
    mock_template = MagicMock()
    mock_template.shape = (40, 40, 3)
    mock_cv2.imread.return_value = mock_template
    
    # Mock visual screen captures
    mock_screen = MagicMock()
    mock_image_grab.grab.return_value = mock_screen
    
    # Mock template matching results
    # First loop: target is at (100, 100). Cursor is at (200, 200). Offset = 100px.
    # Second loop: target stays at (100, 100). Cursor moves to (101, 101). Offset = 1.4px (< 1.5px).
    # Since stabilization_steps is incremented on offset < 1.5, loop will lock on 3rd match.
    mock_cv2.minMaxLoc.side_effect = [
        (0.0, 0.95, (0, 0), (80, 80)), # Target center = 80 + 20 = 100
        (0.0, 0.95, (0, 0), (80, 80)),
        (0.0, 0.95, (0, 0), (80, 80)),
        (0.0, 0.95, (0, 0), (80, 80))
    ]
    
    # Mock cursor tracking position coordinates
    mock_pyautogui.position.side_effect = [
        (200, 200),
        (101, 101),
        (100, 100),
        (100, 100)
    ]
    
    success = visual_servo_click("valid_template.png", timeout_sec=2.0, Kp=0.5)
    
    assert success is True
    # Verify physical cursor click was triggered at final target coordinate
    mock_pyautogui.click.assert_called_once_with(100, 100)

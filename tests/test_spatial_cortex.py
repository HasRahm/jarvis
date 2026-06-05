import pytest
import time
import asyncio
from unittest.mock import MagicMock, patch
from core.system.spatial_cortex import SpatialContextCortex

@patch("core.system.spatial_cortex.BrailleLayer")
@patch("core.system.spatial_cortex.SoundLayer")
@patch("core.system.spatial_cortex.VibrationLayer")
@patch("core.system.spatial_cortex.AirMovementLayer")
def test_fingerprint_generation_and_delta(mock_air, mock_vib, mock_sound, mock_braille):
    # Setup sensory layers mocks
    mock_braille.return_value.read.return_value = {
        "hwnd": 111,
        "title": "Home - Chrome",
        "process": "chrome.exe",
        "tree_hash": "tree1",
        "page_url": "https://example.com",
        "dom_hash": "dom1"
    }
    mock_sound.return_value.read.return_value = {
        "active_audio": [], "keyboard_target": "chrome.exe", "sound_profile": "browser"
    }
    mock_vib.return_value.read.return_value = {
        "cpu": 10.0, "memory": 50.0, "deltas": {}
    }
    mock_air.return_value.read.return_value = {
        "mouse_pos": {"x": 100, "y": 100},
        "focus_process": "chrome.exe",
        "focus_hwnd": 111,
        "in_task_zone": True,
        "drift_vector": 10.0,
        "drift_warning": False
    }
    
    cortex = SpatialContextCortex()
    
    fp1 = cortex._fuse_streams()
    assert fp1["identity"] != ""
    
    # 1. Identical context returns 0.0 delta
    assert cortex._fingerprint_delta(fp1, fp1) == 0.0
    
    # 2. Slight shift (URL change)
    fp2 = fp1.copy()
    fp2["braille"] = fp1["braille"].copy()
    fp2["braille"]["page_url"] = "https://example.com/other"
    # Weight of page_url is 0.2 / total weight (0.5+0.2+0.2+0.1 = 1.0) -> 0.2
    assert cortex._fingerprint_delta(fp1, fp2) == pytest.approx(0.2)
    
    # 3. Complete context change (hwnd, title, tree, process)
    fp3 = fp1.copy()
    fp3["braille"] = {
        "hwnd": 222,
        "title": "Slack",
        "process": "slack.exe",
        "tree_hash": "tree2",
        "page_url": "",
        "dom_hash": ""
    }
    fp3["air"] = fp1["air"].copy()
    fp3["air"]["focus_process"] = "slack.exe"
    # hwnd change (0.5) + tree change (0.2) + page_url change (0.2) + focus_proc change (0.1) -> 1.0 delta
    assert cortex._fingerprint_delta(fp1, fp3) == 1.0

def test_cortex_lifecycle_and_callback():
    cortex = SpatialContextCortex(check_interval_sec=0.01)
    
    # Mock sensory layers to simulate a context switch
    cortex.braille = MagicMock()
    cortex.sound = MagicMock()
    cortex.vibration = MagicMock()
    cortex.air = MagicMock()
    
    # Initial state (Chrome)
    cortex.braille.read.return_value = {
        "hwnd": 111, "title": "Chrome", "process": "chrome.exe", "tree_hash": "tree1", "page_url": "", "dom_hash": ""
    }
    cortex.air.read.return_value = {
        "mouse_pos": {"x": 10}, "focus_process": "chrome.exe", "focus_hwnd": 111, "in_task_zone": True, "drift_vector": 0, "drift_warning": False
    }
    
    event_fired = []
    def on_event(event_type, fp):
        event_fired.append(event_type)
        
    cortex.register_callback(on_event)
    
    cortex.start()
    time.sleep(0.05) # Allow background loop to establish current_fingerprint
    
    # Trigger context switch (hwnd change to Slack)
    cortex.braille.read.return_value = {
        "hwnd": 222, "title": "Slack", "process": "slack.exe", "tree_hash": "tree2", "page_url": "", "dom_hash": ""
    }
    cortex.air.read.return_value = {
        "mouse_pos": {"x": 10}, "focus_process": "slack.exe", "focus_hwnd": 222, "in_task_zone": True, "drift_vector": 0, "drift_warning": False
    }
    
    time.sleep(0.05) # Allow background loop to detect change and fire
    
    cortex.stop()
    
    assert "CONTEXT_SWITCH" in event_fired

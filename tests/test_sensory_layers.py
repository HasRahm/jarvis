import sys
from unittest.mock import MagicMock
mock_pycaw = MagicMock()
sys.modules["pycaw"] = mock_pycaw
sys.modules["pycaw.pycaw"] = mock_pycaw

import pytest
from unittest.mock import patch
from core.system.sensory.braille import BrailleLayer
from core.system.sensory.sound import SoundLayer
from core.system.sensory.vibration import VibrationLayer
from core.system.sensory.air import AirMovementLayer

@patch("core.system.sensory.braille.HAS_WIN32", True)
@patch("core.system.sensory.braille.win32gui")
@patch("core.system.sensory.braille.win32process")
@patch("core.system.sensory.braille.psutil")
@patch("tools.browser.browser_get_url")
def test_braille_layer_read(mock_get_url, mock_psutil, mock_win32process, mock_win32gui):
    # Mock foreground window title and details
    mock_win32gui.GetForegroundWindow.return_value = 999
    mock_win32gui.GetWindowText.return_value = "Inbox - Slack"
    
    mock_win32process.GetWindowThreadProcessId.return_value = (0, 1234)
    mock_proc = MagicMock()
    mock_proc.name.return_value = "slack.exe"
    mock_psutil.Process.return_value = mock_proc
    
    # Mock child windows collection for tree hash
    def side_effect(hwnd, callback, extra):
        callback(101, None)
        callback(102, None)
    mock_win32gui.EnumChildWindows.side_effect = side_effect
    mock_win32gui.GetClassName.side_effect = lambda h: f"Class{h}"
    
    layer = BrailleLayer()
    res = layer.read()
    
    assert res["hwnd"] == 999
    assert res["title"] == "Inbox - Slack"
    assert res["process"] == "slack.exe"
    # Classes are sorted: Class101|Class102 -> MD5 hash
    assert res["tree_hash"] != ""

@patch("core.system.sensory.sound.HAS_PYCAW", True)
@patch("core.system.sensory.sound.AudioUtilities")
@patch("core.system.sensory.sound.HAS_WIN32", True)
@patch("core.system.sensory.sound.win32gui")
@patch("core.system.sensory.sound.win32process")
@patch("core.system.sensory.sound.psutil")
def test_sound_layer(mock_psutil, mock_win32process, mock_win32gui, mock_audio):
    # Mock audio session
    mock_session = MagicMock()
    mock_session.Process.name.return_value = "chrome.exe"
    mock_session.SimpleAudioVolume.GetMute.return_value = 0
    mock_session.SimpleAudioVolume.GetMasterVolume.return_value = 0.8
    mock_audio.GetAllSessions.return_value = [mock_session]
    
    # Mock active keyboard target
    mock_win32gui.GetForegroundWindow.return_value = 888
    mock_win32process.GetWindowThreadProcessId.return_value = (0, 5678)
    mock_proc = MagicMock()
    mock_proc.name.return_value = "code.exe"
    mock_psutil.Process.return_value = mock_proc
    
    layer = SoundLayer()
    res = layer.read()
    
    assert len(res["active_audio"]) == 1
    assert res["active_audio"][0]["process"] == "chrome.exe"
    assert res["keyboard_target"] == "code.exe"
    assert res["sound_profile"] == "browser"

@patch("core.system.sensory.vibration.HAS_PSUTIL", True)
@patch("core.system.sensory.vibration.psutil")
def test_vibration_layer(mock_psutil):
    mock_psutil.cpu_percent.return_value = 10.0
    mock_psutil.virtual_memory.return_value.percent = 50.0
    
    mock_disk = MagicMock()
    mock_disk.read_bytes = 1000
    mock_disk.write_bytes = 2000
    mock_psutil.disk_io_counters.return_value = mock_disk
    
    mock_net = MagicMock()
    mock_net.bytes_sent = 500
    mock_net.bytes_recv = 1500
    mock_psutil.net_io_counters.return_value = mock_net
    
    layer = VibrationLayer()
    # 1st read establishes baseline
    res1 = layer.read()
    assert res1["cpu"] == 10.0
    assert res1["memory"] == 50.0
    
    # 2nd read calculates deltas
    mock_psutil.cpu_percent.return_value = 60.0
    mock_psutil.virtual_memory.return_value.percent = 56.0
    mock_disk.read_bytes = 20000000
    
    res2 = layer.read()
    assert res2["deltas"]["cpu_spike"] is True
    assert res2["deltas"]["memory_jump"] is True
    assert res2["deltas"]["disk_burst"] is True

@patch("core.system.sensory.air.HAS_WIN32API", True)
@patch("core.system.sensory.air.HAS_WIN32GUI", True)
@patch("core.system.sensory.air.win32api")
@patch("core.system.sensory.air.win32gui")
@patch("core.system.sensory.air.win32process")
@patch("core.system.sensory.air.psutil")
def test_air_layer(mock_psutil, mock_win32process, mock_win32gui, mock_win32api):
    mock_win32api.GetCursorPos.return_value = (500, 500)
    mock_win32gui.GetForegroundWindow.return_value = 777
    mock_win32process.GetWindowThreadProcessId.return_value = (0, 9999)
    
    mock_proc = MagicMock()
    mock_proc.name.return_value = "code.exe"
    mock_psutil.Process.return_value = mock_proc
    
    # Region center is at (100, 100)
    layer = AirMovementLayer(task_region={"x": 0, "y": 0, "w": 200, "h": 200})
    
    # 1st read
    res1 = layer.read()
    assert res1["mouse_pos"] == {"x": 500, "y": 500}
    assert res1["focus_process"] == "code.exe"
    assert res1["in_task_zone"] is False
    assert res1["drift_vector"] == 0.0 # Not enough history
    
    # Move cursor and read again
    mock_win32api.GetCursorPos.return_value = (550, 550)
    res2 = layer.read()
    assert res2["in_task_zone"] is False
    # Center is at (100, 100), cursor at (550, 550) -> diff: 450, 450 -> hypot: 636.39
    assert res2["drift_vector"] > 600
    assert res2["drift_warning"] is True

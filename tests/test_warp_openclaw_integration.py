import pytest
import os
import json
from unittest.mock import MagicMock, patch
from tools.desktop_automation import desktop_batch_actions
from core.hermes.bridge import TelegramBridge

# Force headless mock/fallback mode for tests
os.environ["JARVIS_CI"] = "true"

# ==========================================
# 1. Test Batched GUI Action Primitives
# ==========================================

@patch("tools.desktop_automation.desktop_focus_window")
@patch("tools.desktop_automation.desktop_smooth_click")
@patch("tools.desktop_automation.desktop_type_text")
@patch("tools.desktop_automation.desktop_press_keys")
@patch("tools.desktop_automation.desktop_scroll")
@patch("tools.desktop_automation.time.sleep")
def test_desktop_batch_actions_success(
    mock_sleep, mock_scroll, mock_press, mock_type, mock_click, mock_focus
):
    # Setup mock return values to simulate success
    mock_focus.return_value = "Successfully focused window"
    mock_click.return_value = "Successfully glided and clicked"
    mock_type.return_value = "Successfully typed"
    mock_press.return_value = "Successfully pressed keys"
    mock_scroll.return_value = "Successfully scrolled"
    
    actions = [
        {"type": "focus", "title_query": "chrome"},
        {"type": "click", "x": 100, "y": 200},
        {"type": "type_text", "text": "https://www.linkedin.com"},
        {"type": "press_keys", "keys": ["ctrl", "t"]},
        {"type": "scroll", "amount": -100},
        {"type": "wait", "seconds": 2.5}
    ]
    
    res = desktop_batch_actions(actions)
    
    # Assert each native tool was invoked with correct parameters
    mock_focus.assert_called_once_with("chrome")
    mock_click.assert_called_once_with(100, 200, duration=1.5)
    mock_type.assert_called_once_with("https://www.linkedin.com")
    mock_press.assert_called_once_with(["ctrl", "t"])
    mock_scroll.assert_called_once_with(-100, steps=5)
    mock_sleep.assert_called_once_with(2.5)
    
    assert "Successfully executed all 6 batched actions" in res
    assert "focus:" in res
    assert "click:" in res
    assert "type_text:" in res

def test_desktop_batch_actions_unknown_type():
    actions = [
        {"type": "invalid_action_type"}
    ]
    res = desktop_batch_actions(actions)
    assert "ERROR" in res
    assert "Unknown action type" in res

# ==========================================
# 2. Test OpenClaw Telegram Bot Bridge
# ==========================================

@patch.dict(os.environ, {
    "JARVIS_TELEGRAM_TOKEN": "mock_token",
    "JARVIS_ALLOWED_CHAT_IDS": "12345,67890"
})
def test_telegram_bridge_init_and_auth():
    bridge = TelegramBridge()
    assert bridge.token == "mock_token"
    assert 12345 in bridge.allowed_chats
    assert 67890 in bridge.allowed_chats
    assert 99999 not in bridge.allowed_chats

@patch("core.hermes.bridge.urllib.request.urlopen")
@patch.dict(os.environ, {
    "JARVIS_TELEGRAM_TOKEN": "mock_token",
    "JARVIS_ALLOWED_CHAT_IDS": "12345"
})
def test_telegram_bridge_send_message(mock_urlopen):
    # Mock HTTP response
    mock_resp = MagicMock()
    mock_resp.read.return_value = b'{"ok": true}'
    mock_urlopen.return_value.__enter__.return_value = mock_resp
    
    bridge = TelegramBridge()
    bridge.send_telegram_message(12345, "Hello from Jarvis test!")
    
    # Verify urllib request was prepared and opened
    mock_urlopen.assert_called_once()
    req = mock_urlopen.call_args[0][0]
    assert req.full_url == "https://api.telegram.org/botmock_token/sendMessage"
    assert req.method == "POST"

@patch("core.hermes.bridge.urllib.request.urlopen")
@patch("core.hermes.bridge.TelegramBridge.send_telegram_message")
@patch.dict(os.environ, {
    "JARVIS_TELEGRAM_TOKEN": "mock_token",
    "JARVIS_ALLOWED_CHAT_IDS": "12345"
})
def test_telegram_bridge_poll_unauthorized_chat(mock_send, mock_urlopen):
    # Mock update payload from unauthorized chat ID (99999)
    update_payload = {
        "ok": True,
        "result": [
            {
                "update_id": 100,
                "message": {
                    "chat": {"id": 99999},
                    "text": "Focus chrome and type"
                }
            }
        ]
    }
    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps(update_payload).encode("utf-8")
    mock_urlopen.return_value.__enter__.return_value = mock_resp
    
    bridge = TelegramBridge()
    bridge.poll_updates()
    
    # Assert offset was updated
    assert bridge.offset == 101
    # Assert access denied warning message was sent back
    mock_send.assert_called_once_with(99999, "⚠️ *Access Denied:* Your Telegram Chat ID is not whitelisted in Jarvis's configuration.")

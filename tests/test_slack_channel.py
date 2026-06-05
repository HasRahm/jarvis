import pytest
import os
import json
import hmac
import hashlib
import time
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient
from core.hermes.server import app

client = TestClient(app)

def generate_mock_signature(body: str, timestamp: str, secret: str) -> str:
    sig_basestring = f"v0:{timestamp}:{body}".encode("utf-8")
    return "v0=" + hmac.new(secret.encode("utf-8"), sig_basestring, hashlib.sha256).hexdigest()

def test_slack_url_verification():
    payload = {
        "type": "url_verification",
        "challenge": "mock_challenge_123"
    }
    # Test without signature/secret configured (signature verification returns True)
    with patch.dict(os.environ, {"JARVIS_SLACK_SIGNING_SECRET": ""}):
        response = client.post(
            "/api/channels/slack/events",
            json=payload,
            headers={
                "x-slack-request-timestamp": str(int(time.time())),
                "x-slack-signature": "mock"
            }
        )
        assert response.status_code == 200
        assert response.json() == {"challenge": "mock_challenge_123"}

def test_slack_signature_verification_failure():
    payload = {
        "type": "url_verification",
        "challenge": "mock_challenge_123"
    }
    # When signing secret is set, an invalid signature must return 403
    with patch.dict(os.environ, {"JARVIS_SLACK_SIGNING_SECRET": "my_secret"}):
        response = client.post(
            "/api/channels/slack/events",
            json=payload,
            headers={
                "x-slack-request-timestamp": str(int(time.time())),
                "x-slack-signature": "v0=invalid_sig_here"
            }
        )
        assert response.status_code == 403
        assert "Invalid Slack signature" in response.json()["detail"]

def test_slack_signature_verification_success():
    payload = {
        "type": "url_verification",
        "challenge": "mock_challenge_123"
    }
    body_str = json.dumps(payload)
    timestamp = str(int(time.time()))
    secret = "my_secret"
    sig = generate_mock_signature(body_str, timestamp, secret)
    
    with patch.dict(os.environ, {"JARVIS_SLACK_SIGNING_SECRET": secret}):
        response = client.post(
            "/api/channels/slack/events",
            content=body_str,
            headers={
                "Content-Type": "application/json",
                "x-slack-request-timestamp": timestamp,
                "x-slack-signature": sig
            }
        )
        assert response.status_code == 200
        assert response.json() == {"challenge": "mock_challenge_123"}

@patch("core.hermes.channels.slack.send_slack_message")
@patch("core.hermes.channels.slack.execute_slack_prompt")
def test_slack_whitelisted_user_and_workspace(mock_execute, mock_send):
    payload = {
        "type": "event_callback",
        "team_id": "T_ALLOWED",
        "event": {
            "type": "message",
            "user": "U_ALLOWED",
            "text": "run disk cleanup",
            "channel": "C123",
            "ts": "123456.78"
        }
    }
    
    # Configure whitelists
    env_vars = {
        "JARVIS_SLACK_SIGNING_SECRET": "",
        "JARVIS_SLACK_ALLOWED_USERS": "U_ALLOWED,U_OTHER",
        "JARVIS_SLACK_ALLOWED_WORKSPACES": "T_ALLOWED,T_OTHER"
    }
    
    with patch.dict(os.environ, env_vars):
        # 1. Allowed user and workspace
        response = client.post(
            "/api/channels/slack/events",
            json=payload,
            headers={
                "x-slack-request-timestamp": str(int(time.time())),
                "x-slack-signature": "mock"
            }
        )
        assert response.status_code == 200
        assert response.json() == {"status": "event_queued"}
        
        # Give a small slice of time for the background thread to register (or yield)
        time.sleep(0.1)
        mock_execute.assert_called_once_with("C123", "run disk cleanup", "123456.78")
        mock_send.assert_not_called()
        
        # Reset mocks
        mock_execute.reset_mock()
        mock_send.reset_mock()
        
        # 2. Unauthorized user
        payload["event"]["user"] = "U_BLOCKED"
        response = client.post(
            "/api/channels/slack/events",
            json=payload,
            headers={
                "x-slack-request-timestamp": str(int(time.time())),
                "x-slack-signature": "mock"
            }
        )
        assert response.status_code == 200
        assert response.json() == {"status": "unauthorized_user"}
        mock_execute.assert_not_called()
        mock_send.assert_called_once_with(
            "C123",
            "⚠️ *Access Denied:* Your Slack User ID is not whitelisted in Jarvis's configuration.",
            "123456.78"
        )
        
        # Reset mocks
        mock_execute.reset_mock()
        mock_send.reset_mock()
        
        # 3. Unauthorized workspace
        payload["event"]["user"] = "U_ALLOWED"
        payload["team_id"] = "T_BLOCKED"
        response = client.post(
            "/api/channels/slack/events",
            json=payload,
            headers={
                "x-slack-request-timestamp": str(int(time.time())),
                "x-slack-signature": "mock"
            }
        )
        assert response.status_code == 200
        assert response.json() == {"status": "unauthorized_workspace"}
        mock_execute.assert_not_called()
        mock_send.assert_called_once_with(
            "C123",
            "⚠️ *Access Denied:* This Slack Workspace is not whitelisted in Jarvis's configuration.",
            "123456.78"
        )

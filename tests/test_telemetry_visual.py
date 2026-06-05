import os
import json
import time
import pytest
from unittest import mock
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta

from agents.base_agent import BaseAgent, check_pricing_freshness, PRICING
from agents.qa_agent import QAAgent
pytest.importorskip("playwright", reason="playwright not installed")
from tools.browser import browser_navigate, browser_screenshot, shutdown_browser
from core.orchestrator.distributed_sync import agents_md_lock


class DummyAgent(BaseAgent):
    """Minimal subclass to test BaseAgent capabilities."""
    def __init__(self):
        super().__init__(role="qa")

    def run(self, task: str) -> dict:
        return {"status": "success", "output": "dummy"}


def test_pricing_freshness_warning():
    """Verify that a pricing staleness check alerts if PRICING_LAST_UPDATED is >90 days old."""
    with mock.patch("agents.base_agent.PRICING_LAST_UPDATED", "2020-01-01"):
        with mock.patch("builtins.print") as mock_print:
            check_pricing_freshness()
            # Assert printing a warning to console
            mock_print.assert_called()
            args, kwargs = mock_print.call_args
            assert "[WARNING] Operational pricing rules are STALE" in args[0]


def test_telemetry_logging_on_api_call():
    """Test that a raw agent call writes a clean atomic telemetry object to telemetry.json."""
    agent = DummyAgent()
    telemetry_path = os.path.join(agent.workspace, "..", "telemetry.json")
    
    # Clean previous records
    if os.path.exists(telemetry_path):
        try:
            os.remove(telemetry_path)
        except Exception:
            pass

    # Run raw call mock
    with mock.patch.dict(os.environ, {"JARVIS_CI": "true"}):
        agent._raw_call("google", "gemini-3.1-flash", "System Prompt", "User Prompt")

    # Assert telemetry file is created and has valid entries
    assert os.path.exists(telemetry_path)
    with open(telemetry_path, "r", encoding="utf-8") as f:
        records = json.load(f)
        assert len(records) > 0
        latest = records[-1]
        assert latest["role"] == "qa"
        assert latest["model"] == "gemini-3.1-flash"
        assert latest["status"] == "success"
        assert "cost_usd" in latest
        assert latest["cost_type"] == "estimated, verify against provider dashboard"


def test_visual_verifier_escalation():
    """Verify QAAgent escalates to 3.1-pro-preview when Gemini-3.1-flash returns low confidence."""
    qa = QAAgent()
    
    # Create a real dummy file to pass the file existence check
    dummy_img = "dummy.png"
    with open(dummy_img, "wb") as f:
        f.write(b"dummy png bytes")
    
    import sys
    mock_genai = mock.MagicMock()
    original_genai = sys.modules.get("google.genai")
    sys.modules["google.genai"] = mock_genai
    
    try:
        with mock.patch.dict(os.environ, {"JARVIS_CI": "false"}):
            # Mock the new google.genai Client structure
            mock_client_instance = mock.MagicMock()
            mock_genai.Client.return_value = mock_client_instance
            
            # Case A: High confidence returns immediately
            mock_high_confidence = mock.MagicMock()
            mock_high_confidence.text = json.dumps({
                "passed": True,
                "issues": [],
                "confidence": 0.95
            })
            
            # Setup the generate_content to return high confidence first
            mock_client_instance.models.generate_content.return_value = mock_high_confidence
            
            res = qa.verify_ui_layout_visually(dummy_img, "<html></html>")
            assert res["passed"] is True
            assert mock_client_instance.models.generate_content.call_count == 1  # Only default model was invoked

            # Case B: Low confidence (< 0.8) escalates to pro model
            mock_client_instance.models.generate_content.reset_mock()
            
            mock_low_confidence = mock.MagicMock()
            mock_low_confidence.text = json.dumps({
                "passed": False,
                "issues": [{"message": "Overlap detected"}],
                "confidence": 0.65
            })
            
            mock_escalation = mock.MagicMock()
            mock_escalation.text = json.dumps({
                "passed": False,
                "issues": [{"message": "Overlap resolved by second verifier"}],
                "confidence": 0.9
            })
            
            mock_client_instance.models.generate_content.side_effect = [mock_low_confidence, mock_escalation]
            
            res_esc = qa.verify_ui_layout_visually(dummy_img, "<html></html>")
            assert res_esc["passed"] is False
            assert "Overlap resolved" in res_esc["issues"][0]["message"]
            assert mock_client_instance.models.generate_content.call_count == 2  # Both flash and pro called
    finally:
        # Restore original module state
        if original_genai is not None:
            sys.modules["google.genai"] = original_genai
        else:
            sys.modules.pop("google.genai", None)

        if os.path.exists(dummy_img):
            try:
                os.remove(dummy_img)
            except Exception:
                pass


def test_file_lock_concurrent_writer_regression():
    """Assert that the cross-platform file-based lock prevents data collision under high concurrency."""
    import tempfile
    
    # Create a temporary file to simulate AGENTS.md
    with tempfile.NamedTemporaryFile(delete=False, mode="w", suffix=".md") as temp_file:
        temp_file.write("INITIAL_REGISTRY\n")
        temp_path = temp_file.name
        
    lock_path = temp_path + ".lock"
    
    def worker(worker_id):
        # Access lock and modify shared file safely
        for _ in range(3):  # each worker makes 3 writes
            with agents_md_lock(lock_path):
                # Read, wait to induce race overlaps, append, and save
                with open(temp_path, "r") as r:
                    lines = r.readlines()
                
                # short sleep to force concurrent competition
                time.sleep(0.02)
                
                lines.append(f"WORKER_{worker_id}\n")
                
                with open(temp_path, "w") as w:
                    w.writelines(lines)
            time.sleep(0.01)

    # Spawn 5 concurrent threads executing the worker loop
    num_workers = 5
    with ThreadPoolExecutor(max_workers=num_workers) as executor:
        futures = [executor.submit(worker, i) for i in range(num_workers)]
        for f in futures:
            f.result()

    # Verify that all 15 appends are fully registered in linear serial order
    with open(temp_path, "r") as f:
        final_content = f.read()
        
    # Clean up temporary test files
    try:
        os.remove(temp_path)
        if os.path.exists(lock_path):
            os.remove(lock_path)
    except Exception:
        pass
        
    lines = final_content.strip().split("\n")
    assert lines[0] == "INITIAL_REGISTRY"
    # We expect exactly 16 lines (1 initial + 3 writes * 5 workers)
    assert len(lines) == 16
    
    # Verify we got 3 entries for each worker
    for i in range(num_workers):
        assert lines.count(f"WORKER_{i}") == 3

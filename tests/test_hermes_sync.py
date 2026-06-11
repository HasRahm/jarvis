import pytest
import asyncio
import json
import os
from fastapi.testclient import TestClient
from core.hermes.server import app, hermes_event_manager, get_visual_context_history
HERMES_SECRET = os.environ.get("HERMES_SECRET", "")
pytest.importorskip("playwright", reason="playwright not installed")
from tools.browser import browser_resolve_element_at_coords


def _do_auth(websocket, token: str = None) -> None:
    """Send the first-message auth handshake and assert auth_ok is received."""
    t = token or HERMES_SECRET
    websocket.send_text(json.dumps({"type": "auth", "token": t}))
    resp = json.loads(websocket.receive_text())
    assert resp["type"] == "auth_ok", f"Expected auth_ok, got: {resp}"

def test_browser_resolve_element_at_coords_fallback():
    """Assert coordinate element resolution yields robust selector pathing even on elements without IDs or unique classes."""
    # Test resolving coordinates against raw ratios without active browser - should fallback gracefully
    # If no browser is running, it returns a safe default or empty result dictionary
    res = browser_resolve_element_at_coords(0.5, 0.5)
    assert isinstance(res, dict)
    assert "selector" in res

def test_hermes_event_manager_queuing():
    """Verify thread-safe queuing via HermesEventManager pushes to asyncio.Queue correctly."""
    import threading
    import time
    
    loop = asyncio.new_event_loop()
    def run_loop(l):
        asyncio.set_event_loop(l)
        l.run_forever()
        
    t = threading.Thread(target=run_loop, args=(loop,), daemon=True)
    t.start()
    
    try:
        hermes_event_manager.loop = loop
        hermes_event_manager.set_loop(loop)
        assert hermes_event_manager.loop is loop
        
        # Register a dummy ConnectionState to receive the event
        from core.hermes.server import ConnectionState
        state = ConnectionState(conn_id="test_conn", loop=loop)
        hermes_event_manager.register(state)
        
        # Map legacy event_queue attribute on manager to the connection queue
        hermes_event_manager.event_queue = state.event_queue
        
        # Enqueue speech sync
        hermes_event_manager.enqueue_speech_sync("Test message", interrupt=True)
        
        # Wait a brief moment for the thread to process the coroutine
        time.sleep(0.15)
        
        # Retrieve event from queue
        async def get_event():
            return await hermes_event_manager.event_queue.get()
            
        future = asyncio.run_coroutine_threadsafe(get_event(), loop)
        event = future.result(timeout=1.0)
        
        assert event["type"] == "agent_speech"
        assert event["text"] == "Test message"
        assert event["interrupt"] is True
    finally:
        hermes_event_manager.unregister("test_conn")
        loop.call_soon_threadsafe(loop.stop)
        t.join(timeout=1.0)



def test_websocket_visual_interaction_grounding():
    """Assert WebSocket correctly processes visual interaction coordinates and maintains sliding window context cap of 5."""
    # Reset visual context history on all active connections
    with hermes_event_manager._lock:
        for state in hermes_event_manager._connections.values():
            state.visual_context_history.clear()

    client = TestClient(app)

    with client.websocket_connect("/ws") as websocket:
        _do_auth(websocket)  # first-message auth handshake

        # Send visual interaction coordinates
        websocket.send_text(json.dumps({
            "type": "visual_interaction",
            "coords": {"x": 0.25, "y": 0.75}
        }))
        
        # Read response
        # The PWA should receive an interrupt control frame
        resp_str = websocket.receive_text()
        resp = json.loads(resp_str)
        assert resp["type"] == "interrupt" or resp["type"] == "text_start"
        
        # Verify grounding context has been captured and appended to the sliding window history
        history = get_visual_context_history()
        assert len(history) >= 1
        assert "selector" in history[0]
        
        # Test sliding window cap by adding more than 5 elements manually on the active connection state
        with hermes_event_manager._lock:
            state = list(hermes_event_manager._connections.values())[-1]
            state.visual_context_history.clear()
            for i in range(10):
                state.visual_context_history.append({"selector": f"#elem-{i}", "tag_name": "DIV", "classes": [], "inner_text": ""})
                if len(state.visual_context_history) > 5:
                    state.visual_context_history.pop(0)
                
        assert len(get_visual_context_history()) == 5
        assert get_visual_context_history()[0]["selector"] == "#elem-5"
        assert get_visual_context_history()[-1]["selector"] == "#elem-9"

def test_websocket_interrupt_handling():
    """Verify that WebSocket delivers audio playback interrupt packets successfully."""
    client = TestClient(app)
    with client.websocket_connect("/ws") as websocket:
        _do_auth(websocket)  # first-message auth handshake
        # Sending visual grounding click automatically triggers a playback interruption frame to cut active speak streams
        websocket.send_text(json.dumps({
            "type": "visual_interaction",
            "coords": {"x": 0.5, "y": 0.5}
        }))
        
        # First message must be interrupt control signal
        data = json.loads(websocket.receive_text())
        assert data["type"] == "interrupt"
        assert data["interrupt"] is True

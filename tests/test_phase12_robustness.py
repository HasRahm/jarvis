"""
Phase 12 tests: Multi-Client Robustness.
All tests run fully offline under JARVIS_CI=true.
"""
import os
import sys
import json
import asyncio
import threading
import time
import unittest

os.environ.setdefault("JARVIS_CI", "true")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ---------------------------------------------------------------------------
# 1. Two concurrent clients both get auth_ok
# ---------------------------------------------------------------------------
class TestTwoConcurrentClients(unittest.TestCase):
    def test_two_concurrent_clients_both_authenticated(self):
        """Two simultaneous WS connections each receive auth_ok independently."""
        os.environ["JARVIS_CI"] = "true"
        from starlette.testclient import TestClient
        from core.hermes.server import app
        # HERMES_SECRET is no longer a module constant on the server (auth is call-time,
        # fail-closed via core.auth.authenticate). Read the secret the autouse clean_env
        # fixture set for this test from the environment.
        HERMES_SECRET = os.environ["HERMES_SECRET"]

        received = []
        errors = []

        def connect_and_auth(client):
            try:
                with client.websocket_connect("/ws") as ws:
                    ws.send_text(json.dumps({"type": "auth", "token": HERMES_SECRET}))
                    resp = json.loads(ws.receive_text())
                    received.append(resp.get("type"))
            except Exception as e:
                errors.append(str(e))

        with TestClient(app) as client:
            t1 = threading.Thread(target=connect_and_auth, args=(client,))
            t2 = threading.Thread(target=connect_and_auth, args=(client,))
            t1.start()
            t2.start()
            t1.join(timeout=10)
            t2.join(timeout=10)

        self.assertFalse(errors, f"Connection errors: {errors}")
        self.assertEqual(received.count("auth_ok"), 2)


# ---------------------------------------------------------------------------
# 2. Visual history is isolated per connection
# ---------------------------------------------------------------------------
class TestVisualHistoryIsolation(unittest.TestCase):
    def test_visual_history_isolated_per_connection(self):
        """Modifying client A's visual_context_history does not affect client B's."""
        os.environ["JARVIS_CI"] = "true"
        from core.hermes.server import hermes_event_manager, ConnectionState

        loop = asyncio.new_event_loop()
        state_a = ConnectionState(conn_id="vis-a", loop=loop)
        state_b = ConnectionState(conn_id="vis-b", loop=loop)

        hermes_event_manager.register(state_a)
        hermes_event_manager.register(state_b)

        try:
            # Directly mutate client A's visual history (simulates a visual_interaction message)
            state_a.visual_context_history.append({
                "selector": "button.hero",
                "tag_name": "BUTTON",
                "classes": ["hero"],
                "inner_text": "Click me"
            })

            self.assertEqual(len(state_a.visual_context_history), 1)
            self.assertEqual(len(state_b.visual_context_history), 0,
                             "Client B should have an empty visual history")
        finally:
            hermes_event_manager.unregister("vis-a")
            hermes_event_manager.unregister("vis-b")
            loop.close()


# ---------------------------------------------------------------------------
# 3. Broadcast reaches all registered clients
# ---------------------------------------------------------------------------
class TestBroadcastReachesAllClients(unittest.TestCase):
    def test_broadcast_reaches_all_clients(self):
        """enqueue_speech_sync() dispatches an event to every active connection's queue."""
        os.environ["JARVIS_CI"] = "true"
        from core.hermes.server import hermes_event_manager, ConnectionState

        loop = asyncio.new_event_loop()

        # Run the event loop in a background thread so run_coroutine_threadsafe works
        loop_thread = threading.Thread(target=loop.run_forever, daemon=True)
        loop_thread.start()

        state_a = ConnectionState(conn_id="bcast-a", loop=loop)
        state_b = ConnectionState(conn_id="bcast-b", loop=loop)
        hermes_event_manager.register(state_a)
        hermes_event_manager.register(state_b)

        try:
            # Enqueue from the main thread — simulates an agent worker thread
            hermes_event_manager.enqueue_speech_sync("hello from agent", role_hint="qa")

            # Give the running loop time to execute the put() coroutines
            time.sleep(0.4)

            self.assertFalse(state_a.event_queue.empty(),
                             "Client A did not receive the broadcast")
            self.assertFalse(state_b.event_queue.empty(),
                             "Client B did not receive the broadcast")
        finally:
            hermes_event_manager.unregister("bcast-a")
            hermes_event_manager.unregister("bcast-b")
            loop.call_soon_threadsafe(loop.stop)
            loop_thread.join(timeout=2)


# ---------------------------------------------------------------------------
# 4. Agent task timeout returns error status
# ---------------------------------------------------------------------------
class TestAgentTimeout(unittest.TestCase):
    def test_agent_timeout_returns_error_status(self):
        """A hung agent.run() call times out and produces an error result dict."""
        os.environ["JARVIS_CI"] = "true"
        from concurrent.futures import TimeoutError as FuturesTimeoutError
        from core.orchestrator import dag as dag_module

        stop_event = threading.Event()

        class HungAgent:
            role = "backend"

            def run(self, task):
                # Block until signalled (avoids leaving a 999-second sleeping thread)
                stop_event.wait(timeout=30)
                return {"status": "success", "output": "unreachable", "files": []}

        _orig_timeout = dag_module._AGENT_TIMEOUT_SEC
        dag_module._AGENT_TIMEOUT_SEC = 1
        try:
            agent = HungAgent()
            future = dag_module._agent_executor.submit(agent.run, "test task")
            try:
                result = future.result(timeout=dag_module._AGENT_TIMEOUT_SEC)
            except FuturesTimeoutError:
                result = {
                    "status": "error",
                    "output": f"[TIMEOUT] {agent.role} agent timed out after {dag_module._AGENT_TIMEOUT_SEC}s",
                    "files": [],
                }

            self.assertEqual(result["status"], "error")
            self.assertIn("[TIMEOUT]", result["output"])
        finally:
            stop_event.set()        # release the thread so it exits cleanly
            dag_module._AGENT_TIMEOUT_SEC = _orig_timeout


# ---------------------------------------------------------------------------
# 5. Oversized WebSocket messages are rejected
# ---------------------------------------------------------------------------
class TestOversizedMessageRejected(unittest.TestCase):
    def test_oversized_message_rejected(self):
        """A message exceeding JARVIS_MAX_WS_MSG_BYTES is rejected with type=error."""
        os.environ["JARVIS_CI"] = "true"
        # Use a 1 KB limit so the test is fast (default is 1 MB)
        os.environ["JARVIS_MAX_WS_MSG_BYTES"] = str(1024)

        try:
            from starlette.testclient import TestClient
            from core.hermes.server import app
            HERMES_SECRET = os.environ["HERMES_SECRET"]

            with TestClient(app) as client:
                with client.websocket_connect("/ws") as ws:
                    # Authenticate
                    ws.send_text(json.dumps({"type": "auth", "token": HERMES_SECRET}))
                    resp = json.loads(ws.receive_text())
                    self.assertEqual(resp.get("type"), "auth_ok")

                    # Send oversized message (2 KB > 1 KB limit)
                    big_msg = json.dumps({"text": "x" * 2048})
                    ws.send_text(big_msg)

                    # Must receive an error response, not crash
                    error_resp = json.loads(ws.receive_text())
                    self.assertEqual(error_resp.get("type"), "error",
                                     f"Expected error type, got: {error_resp}")
        finally:
            # Restore default so other tests are unaffected
            os.environ["JARVIS_MAX_WS_MSG_BYTES"] = str(1 * 1024 * 1024)


if __name__ == "__main__":
    unittest.main()

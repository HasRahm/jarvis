import asyncio
import websockets
import json

async def _hermes_roundtrip():
    """Manual integration check: run with `python tests/test_hermes_ws.py` while Hermes is live."""
    uri = "ws://localhost:9000/ws"
    print(f"Connecting to {uri}...")
    async with websockets.connect(uri) as ws:
        print("Connected! Sending auth handshake...")
        # Send auth as first message
        await ws.send(json.dumps({"type": "auth", "token": "jarvis_hermes_2026"}))
        
        # Receive auth_ok response
        auth_resp = await ws.recv()
        print(f"Auth Response: {auth_resp}")
        
        # Send actual text message
        await ws.send(json.dumps({"text": "Hello Jarvis, can you hear me?", "type": "message"}))
        resp = await ws.recv()
        print(f"Response: {resp}")
        print("SUCCESS: WebSocket round-trip complete!")

if __name__ == "__main__":
    asyncio.run(_hermes_roundtrip())

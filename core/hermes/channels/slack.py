import os
import sys
import time
import json
import urllib.request
import urllib.error
import subprocess
import threading
import logging
import re
import hmac
import hashlib
from fastapi import APIRouter, Request, Header, HTTPException

# Set up logging
logger = logging.getLogger("slack_channel")

router = APIRouter()

def verify_slack_signature(request_body: str, timestamp: str, signature: str) -> bool:
    print(f"[TRACE] core.hermes.channels.slack.verify_slack_signature: enter", file=sys.stderr, flush=True)
    signing_secret = os.environ.get("JARVIS_SLACK_SIGNING_SECRET", "").strip()
    if not signing_secret:
        # If signing secret is not configured, bypass signature verification (useful for dev/testing)
        return True
        
    # Check if request timestamp is within 5 minutes of local time to prevent replay attacks
    try:
        if abs(time.time() - int(timestamp)) > 60 * 5:
            return False
    except ValueError:
        print(f"[TRACE] core.hermes.channels.slack.verify_slack_signature: except ValueError", file=sys.stderr, flush=True)
        return False
        
    sig_basestring = f"v0:{timestamp}:{request_body}".encode("utf-8")
    my_signature = "v0=" + hmac.new(
        signing_secret.encode("utf-8"),
        sig_basestring,
        hashlib.sha256
    ).hexdigest()
    
    return hmac.compare_digest(my_signature, signature)

def send_slack_message(channel: str, text: str, thread_ts: str = None) -> str:
    print(f"[TRACE] core.hermes.channels.slack.send_slack_message: enter", file=sys.stderr, flush=True)
    token = os.environ.get("JARVIS_SLACK_BOT_TOKEN", "").strip()
    if not token:
        logger.info(f"[MOCK SEND] Channel {channel}: {text}")
        return "mock_ts"
        
    url = "https://slack.com/api/chat.postMessage"
    payload = {
        "channel": channel,
        "text": text[:4000],
    }
    if thread_ts:
        payload["thread_ts"] = thread_ts
        
    try:
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json; charset=utf-8",
                "Authorization": f"Bearer {token}"
            },
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if data.get("ok"):
                return data.get("ts")
    except Exception as e:
        print(f"[TRACE] core.hermes.channels.slack.send_slack_message: except {str(e)[:80]}", file=sys.stderr, flush=True)
        logger.error(f"Failed to send Slack message: {e}")
    return ""

def update_slack_message(channel: str, ts: str, text: str):
    print(f"[TRACE] core.hermes.channels.slack.update_slack_message: enter", file=sys.stderr, flush=True)
    token = os.environ.get("JARVIS_SLACK_BOT_TOKEN", "").strip()
    if not token:
        logger.info(f"[MOCK UPDATE] Channel {channel} TS {ts}: {text}")
        return
        
    url = "https://slack.com/api/chat.update"
    payload = {
        "channel": channel,
        "ts": ts,
        "text": text[:4000]
    }
    try:
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json; charset=utf-8",
                "Authorization": f"Bearer {token}"
            },
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            resp.read()
    except Exception as e:
        print(f"[TRACE] core.hermes.channels.slack.update_slack_message: except {str(e)[:80]}", file=sys.stderr, flush=True)
        logger.error(f"Failed to update Slack message: {e}")

def execute_slack_prompt(channel: str, prompt: str, thread_ts: str):
    print(f"[TRACE] core.hermes.channels.slack.execute_slack_prompt: enter", file=sys.stderr, flush=True)
    logger.info(f"[Slack] Routing prompt: '{prompt}' to Jarvis CLI...")
    msg_ts = None
    try:
        # Send initial progress message
        msg_ts = send_slack_message(channel, "⏳ *Jarvis is processing your request...*", thread_ts)
        
        # Escape single quotes safely for powershell
        safe_prompt = prompt.replace("'", "''")
        cmd = f"echo '{safe_prompt}' | .venv\\Scripts\\python.exe core/gemma4_loop.py"
        
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
        
        proc = subprocess.Popen(
            ["powershell", "-Command", cmd],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=project_root
        )
        
        ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
        output_buffer = []
        last_update_time = time.time()
        
        while True:
            line = proc.stdout.readline()
            if not line and proc.poll() is not None:
                break
            if line:
                if "[INFO]" not in line and "httpx:" not in line and "[Tool Call]" not in line and "Environmental scan" not in line:
                    output_buffer.append(line)
                
                # Update Slack every 2 seconds to stream output
                if time.time() - last_update_time > 2.0 and msg_ts:
                    current_output = "".join(output_buffer).strip()
                    current_output = ansi_escape.sub('', current_output)
                    current_output = current_output.replace("jarvis>", "").strip()
                    current_output = current_output.replace("Exiting Jarvis...", "").strip()
                    if current_output:
                        update_slack_message(channel, msg_ts, f"⏳ *Jarvis is processing...*\n\n```\n{current_output[-3500:]}\n```")
                    last_update_time = time.time()
                    
        stdout, stderr = proc.communicate()
        if stdout:
            for line in stdout.split("\n"):
                if "[INFO]" not in line and "httpx:" not in line and "[Tool Call]" not in line and "Environmental scan" not in line:
                    output_buffer.append(line + "\n")
                    
        clean_output = "".join(output_buffer).strip()
        clean_output = ansi_escape.sub('', clean_output)
        clean_output = clean_output.replace("jarvis>", "").strip()
        clean_output = clean_output.replace("Exiting Jarvis...", "").strip()
        
        if not clean_output:
            clean_output = "Task completed successfully, but returned empty stdout."
            
        update_slack_message(channel, msg_ts, f"✅ *Task Completed!*\n\n```\n{clean_output[:3800]}\n```")
    except Exception as e:
        print(f"[TRACE] core.hermes.channels.slack.execute_slack_prompt: except {str(e)[:80]}", file=sys.stderr, flush=True)
        logger.error(f"Failed executing Slack prompt: {e}")
        if msg_ts:
            update_slack_message(channel, msg_ts, f"❌ *Error executing task:* {e}")
        else:
            send_slack_message(channel, f"❌ *Error executing task:* {e}", thread_ts)

def _parse_list(s: str) -> set[str]:
    print(f"[TRACE] core.hermes.channels.slack._parse_list: enter", file=sys.stderr, flush=True)
    if not s or not s.strip():
        return set()
    return {item.strip() for item in s.split(",") if item.strip()}

@router.post("/events")
async def slack_events(
    request: Request,
    x_slack_request_timestamp: str = Header(default=""),
    x_slack_signature: str = Header(default="")
):
    print(f"[TRACE] core.hermes.channels.slack.slack_events: enter", file=sys.stderr, flush=True)
    body = await request.body()
    body_str = body.decode("utf-8")
    
    if not verify_slack_signature(body_str, x_slack_request_timestamp, x_slack_signature):
        raise HTTPException(status_code=403, detail="Invalid Slack signature")
        
    try:
        payload = json.loads(body_str)
    except Exception:
        print(f"[TRACE] core.hermes.channels.slack.slack_events: except Exception", file=sys.stderr, flush=True)
        raise HTTPException(status_code=400, detail="Invalid JSON body")
    
    if payload.get("type") == "url_verification":
        return {"challenge": payload.get("challenge")}
        
    event = payload.get("event", {})
    if event.get("bot_id") or event.get("subtype") == "bot_message":
        return {"status": "ignored"}
        
    if event.get("type") == "message" and "text" in event:
        user_id = event.get("user")
        team_id = payload.get("team_id")
        channel = event.get("channel")
        text = event.get("text", "").strip()
        thread_ts = event.get("thread_ts") or event.get("ts")
        
        allowed_users = _parse_list(os.environ.get("JARVIS_SLACK_ALLOWED_USERS", ""))
        allowed_teams = _parse_list(os.environ.get("JARVIS_SLACK_ALLOWED_WORKSPACES", ""))
        
        if allowed_users and user_id not in allowed_users:
            send_slack_message(channel, "⚠️ *Access Denied:* Your Slack User ID is not whitelisted in Jarvis's configuration.", thread_ts)
            return {"status": "unauthorized_user"}
            
        if allowed_teams and team_id not in allowed_teams:
            send_slack_message(channel, "⚠️ *Access Denied:* This Slack Workspace is not whitelisted in Jarvis's configuration.", thread_ts)
            return {"status": "unauthorized_workspace"}
            
        # Run prompt execution in background thread to avoid webhook timeout (3 seconds limit)
        threading.Thread(
            target=execute_slack_prompt,
            args=(channel, text, thread_ts),
            daemon=True
        ).start()
        
    return {"status": "event_queued"}

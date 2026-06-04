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
from colorama import Fore, Style, init

# Resolve sys.path to project root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from core.logging_config import configure_logging

configure_logging("bridge")
logger = logging.getLogger("bridge")

init()

class TelegramBridge:
    def __init__(self):
        self.token = os.environ.get("JARVIS_TELEGRAM_TOKEN", "").strip()
        self.allowed_chats = self._parse_allowed_chats()
        self.offset = 0
        self.running = True
        
    def _parse_allowed_chats(self) -> set[int]:
        chats_str = os.environ.get("JARVIS_ALLOWED_CHAT_IDS", "").strip()
        if not chats_str:
            return set()
        chats = set()
        for c in chats_str.split(","):
            try:
                chats.add(int(c.strip()))
            except ValueError:
                continue
        return chats

    def send_telegram_message(self, chat_id: int, text: str):
        """Sends a text message back to the whitelisted Telegram Chat ID."""
        if not self.token:
            print(f"[MOCK SEND] Chat {chat_id}: {text}")
            return
            
        url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": text[:4000],  # Telegram limit is 4096 characters
            "parse_mode": "Markdown"
        }
        
        try:
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                resp.read()
        except Exception as e:
            logger.error(f"Failed to send Telegram message: {e}")

    def execute_prompt(self, chat_id: int, prompt: str):
        """Executes a prompt through Jarvis's CLI pipeline and returns the result."""
        self.send_telegram_message(chat_id, "⏳ *Jarvis is processing your request...*")
        
        try:
            print(f"  [BRIDGE] Routing prompt: '{prompt}' to Jarvis CLI...")
            
            # Escape single quotes safely for powershell
            safe_prompt = prompt.replace("'", "''")
            cmd = f"echo '{safe_prompt}' | .venv\\Scripts\\python.exe core/gemma4_loop.py"
            
            project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            
            proc = subprocess.Popen(
                ["powershell", "-Command", cmd],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                cwd=project_root
            )
            
            stdout, stderr = proc.communicate(timeout=120)
            
            # Clean up the output to send back to the user
            # Filter out standard logging lines and ANSI colors
            lines = stdout.split("\n")
            filtered_lines = []
            for line in lines:
                if "[INFO]" not in line and "httpx:" not in line and "[Tool Call]" not in line and "Environmental scan" not in line:
                    filtered_lines.append(line)
                    
            clean_output = "\n".join(filtered_lines).strip()
            
            # Remove ANSI color escapes
            ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
            clean_output = ansi_escape.sub('', clean_output)
            
            # Filter out the repeating 'jarvis>' prompt line
            clean_output = clean_output.replace("jarvis>", "").strip()
            clean_output = clean_output.replace("Exiting Jarvis...", "").strip()
            
            if not clean_output:
                clean_output = "Task completed successfully, but returned empty stdout."
                
            self.send_telegram_message(chat_id, f"✅ *Task Completed!*\n\n```\n{clean_output[:3800]}\n```")
        except Exception as e:
            logger.error(f"Failed executing prompt: {e}")
            self.send_telegram_message(chat_id, f"❌ *Error executing task:* {e}")

    def poll_updates(self):
        """Polls for new messages from Telegram Bot API."""
        if not self.token:
            print(Fore.YELLOW + "[BRIDGE] Telegram Bot Token (JARVIS_TELEGRAM_TOKEN) is not configured in .env.")
            print("[BRIDGE] Bot Bridge is running in MOCK mode. Standing by...\n" + Style.RESET_ALL)
            time.sleep(10)
            return

        url = f"https://api.telegram.org/bot{self.token}/getUpdates?offset={self.offset}&timeout=10"
        
        try:
            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req, timeout=12) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                
                if not data.get("ok"):
                    logger.error(f"Telegram API error: {data}")
                    time.sleep(5)
                    return
                    
                for update in data.get("result", []):
                    self.offset = update["update_id"] + 1
                    message = update.get("message")
                    if not message or "text" not in message:
                        continue
                        
                    chat_id = message["chat"]["id"]
                    text = message["text"].strip()
                    
                    # Authenticate chat_id
                    if self.allowed_chats and chat_id not in self.allowed_chats:
                        logger.warning(f"Ignored unauthorized message from chat {chat_id}: {text}")
                        self.send_telegram_message(chat_id, "⚠️ *Access Denied:* Your Telegram Chat ID is not whitelisted in Jarvis's configuration.")
                        continue
                        
                    print(Fore.GREEN + f"  [BRIDGE] Received authenticated command from {chat_id}: '{text}'" + Style.RESET_ALL)
                    
                    # Route slash commands quickly
                    if text.startswith("/"):
                        if text == "/help":
                            self.send_telegram_message(
                                chat_id, 
                                "🤖 *Jarvis Remote Control Panel*\n"
                                "-------------------------------------\n"
                                "Send any task as a plain-text message to control your desktop.\n\n"
                                "*Slash Commands:*\n"
                                "• `/cleanup` - Run safe auto-clean sweep\n"
                                "• `/optimize` - Reclaim RAM by terminating zombies\n"
                                "• `/telemetry` - Get cost/token spend metrics\n"
                                "• `/status` - Verify active system health"
                            )
                        elif text == "/cleanup":
                            threading.Thread(target=self.execute_prompt, args=(chat_id, "/cleanup")).start()
                        elif text == "/optimize":
                            threading.Thread(target=self.execute_prompt, args=(chat_id, "/optimize")).start()
                        elif text == "/telemetry":
                            threading.Thread(target=self.execute_prompt, args=(chat_id, "/telemetry")).start()
                        elif text == "/status":
                            self.send_telegram_message(chat_id, "🟢 *Jarvis is online and active!* Local environment is healthy.")
                        else:
                            self.send_telegram_message(chat_id, "❌ *Unknown command.* Send any plain text prompt to Jarvis.")
                    else:
                        # Start asynchronous task execution
                        threading.Thread(target=self.execute_prompt, args=(chat_id, text)).start()
                        
        except urllib.error.URLError as e:
            # Silence expected timeouts during polling updates
            time.sleep(2)
        except Exception as e:
            logger.error(f"Bridge polling error: {e}")
            time.sleep(5)

    def start(self):
        print(Fore.CYAN + "====================================")
        print("   Jarvis Secure Messenger Bridge   ")
        print("====================================\n" + Style.RESET_ALL)
        
        while self.running:
            self.poll_updates()

if __name__ == "__main__":
    bridge = TelegramBridge()
    try:
        bridge.start()
    except KeyboardInterrupt:
        print("\nStopping Bot Bridge...")
        bridge.running = False

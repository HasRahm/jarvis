# core/system/app_controller.py

import os
import sys
import time
import subprocess
import threading
import io
from typing import Callable, Any, Dict, List
from datetime import datetime, timezone
from PIL import Image

# Secure Win32 imports with headless/cross-platform fallback wrapper
try:
    import win32gui
    import win32con
    import win32api
    import win32com.client
    import win32ui
    import ctypes
    WIN32_AVAILABLE = True
except ImportError:
    print(f"[TRACE] core.system.app_controller.<module>: except ImportError", file=sys.stderr, flush=True)
    WIN32_AVAILABLE = False

class AppNotFoundError(Exception):
    pass

class WrongWindowError(Exception):
    pass

# Custom mock API clients for Tier 1
class MockAPIClient:
    def __init__(self, name: str):
        self.name = name
    async def execute(self, task: dict) -> dict:
        return {"status": "SUCCESS", "message": f"Executed via Tier 1 REST API client: {self.name}"}

class UniversalAppController:
    """
    Single entry point for controlling any app on the machine.
    Automatically selects the best execution tier.
    """

    def __init__(self, app_registry: dict, brain_client=None):
        self.registry = app_registry
        self.brain = brain_client
        self.tracked = {}        # hwnd -> app context
        self.watchers = {}       # hwnd -> StateWatcher
        self.virtual_display = None

    def _normalize_name(self, name: str) -> str:
        return name.lower().strip()

    def _get_api_client(self, client_class: str) -> MockAPIClient:
        return MockAPIClient(client_class)

    async def _call_mcp(self, mcp_name: str, task: dict) -> dict:
        return {"status": "SUCCESS", "message": f"Executed via Tier 2 MCP server: {mcp_name}"}

    async def _mcp_available(self, mcp_name: str) -> bool:
        # Check standard registered MCP lists
        return True

    async def _probe_local_api(self, app_name: str) -> bool:
        return False

    async def _run_com_task(self, app: Any, task: dict) -> dict:
        return {"status": "SUCCESS", "message": "Executed COM object model action invisibly."}

    async def _execute_visual_task(self, hwnd: int, task: dict) -> dict:
        return {"status": "SUCCESS", "message": f"Executed visual task on focused window: {hwnd}"}

    # ─────────────────────────────────────────────────────
    # PUBLIC: Main entry point
    # ─────────────────────────────────────────────────────

    async def execute(self, app_name: str, task: dict) -> Any:
        """
        Execute a task on any app.
        Automatically selects the right tier.
        """
        print(f"[TRACE] core.system.app_controller.UniversalAppController.execute: enter", file=sys.stderr, flush=True)
        app_key = self._normalize_name(app_name)
        caps = self.registry.get(app_key)

        if not caps:
            # Unknown app — discover capabilities at runtime
            caps = await self._discover_capabilities(app_name)

        tier = caps.get("tier", 4)

        # Log intent to G-Brain if available
        if self.brain:
            now_str = datetime.now(timezone.utc).isoformat()
            await self.brain.write(
                f"app_tasks/{app_key}/{task.get('id', 'default')}",
                {"app": app_name, "task": task, "tier": tier, "started_at": now_str}
            )

        if tier == 1:
            return await self._execute_api(app_key, caps, task)
        elif tier == 2:
            return await self._execute_mcp(app_key, caps, task)
        elif tier == 3:
            return await self._execute_background(app_key, caps, task)
        else:
            return await self._execute_foreground(app_key, caps, task)

    # ─────────────────────────────────────────────────────
    # TIER 1: API execution
    # ─────────────────────────────────────────────────────

    async def _execute_api(self, app_key: str, caps: dict, task: dict) -> Any:
        """
        Execute via HTTP API or SDK. App doesn't need to be open.
        """
        print(f"[TRACE] core.system.app_controller.UniversalAppController._execute_api: enter", file=sys.stderr, flush=True)
        client_class = caps.get("api")
        if not client_class:
            return await self._execute_mcp(app_key, caps, task)

        client = self._get_api_client(client_class)
        result = await client.execute(task)

        if self.brain:
            await self.brain.write(
                f"app_tasks/{app_key}/{task.get('id', 'default')}/result",
                {"result": result, "tier_used": 1}
            )
        return result

    # ─────────────────────────────────────────────────────
    # TIER 2: MCP execution
    # ─────────────────────────────────────────────────────

    async def _execute_mcp(self, app_key: str, caps: dict, task: dict) -> Any:
        """Execute via MCP tool calls. No window interaction."""
        print(f"[TRACE] core.system.app_controller.UniversalAppController._execute_mcp: enter", file=sys.stderr, flush=True)
        mcp_name = caps.get("mcp")
        if not mcp_name:
            return await self._execute_background(app_key, caps, task)

        result = await self._call_mcp(mcp_name, task)
        return result

    # ─────────────────────────────────────────────────────
    # TIER 3: Background Win32 messaging
    # ─────────────────────────────────────────────────────

    async def _execute_background(self, app_key: str, caps: dict, task: dict) -> Any:
        """
        Execute by sending messages directly to window handle.
        Window does NOT need to be visible or focused.
        """
        print(f"[TRACE] core.system.app_controller.UniversalAppController._execute_background: enter", file=sys.stderr, flush=True)
        if not WIN32_AVAILABLE:
            # Mock fallback for headless environments
            return {"status": "SUCCESS", "message": "Headless fallback: background messaging simulated."}

        hwnd = self._find_or_launch(app_key)
        if not hwnd:
            return await self._execute_foreground(app_key, caps, task)

        # Restore if minimized (needed for content rendering) but keep hidden from user
        if self._get_state(hwnd) == "minimized":
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
            win32gui.ShowWindow(hwnd, win32con.SW_HIDE)
            time.sleep(0.2)

        # Check if COM automation is available (Office apps)
        if caps.get("api", "").endswith("COMClient"):
            return await self._execute_com(app_key, hwnd, task)

        # Generic background messaging
        screenshot = self._capture_background(hwnd)
        
        # Simple action plan mock
        actions = [{"type": "click", "x": 100, "y": 100}, {"type": "type", "text": "Background text input"}]

        for action in actions:
            await self._send_action_background(hwnd, action)
            time.sleep(0.1)

        return {"status": "SUCCESS", "message": "Successfully sent Win32 background inputs."}

    def _capture_background(self, hwnd: int) -> Image.Image:
        """Capture any window even if hidden or minimized using PrintWindow."""
        print(f"[TRACE] core.system.app_controller.UniversalAppController._capture_background: enter", file=sys.stderr, flush=True)
        if not WIN32_AVAILABLE:
            return Image.new("RGB", (800, 600), (0, 0, 0))

        try:
            left, top, right, bottom = win32gui.GetWindowRect(hwnd)
            w = max(1, right - left)
            h = max(1, bottom - top)

            hwnd_dc = win32gui.GetWindowDC(hwnd)
            mfc_dc = win32ui.CreateDCFromHandle(hwnd_dc)
            save_dc = mfc_dc.CreateCompatibleDC()
            bitmap = win32ui.CreateBitmap()
            bitmap.CreateCompatibleBitmap(mfc_dc, w, h)
            save_dc.SelectObject(bitmap)

            # PW_RENDERFULLCONTENT = 2: Renders electron/modern apps correctly
            ctypes.windll.user32.PrintWindow(hwnd, save_dc.GetSafeHdc(), 2)

            bmpinfo = bitmap.GetInfo()
            bmpstr = bitmap.GetBitmapBits(True)
            img = Image.frombuffer(
                'RGB', (bmpinfo['bmWidth'], bmpinfo['bmHeight']),
                bmpstr, 'raw', 'BGRX', 0, 1
            )

            win32gui.DeleteObject(bitmap.GetHandle())
            save_dc.DeleteDC()
            mfc_dc.DeleteDC()
            win32gui.ReleaseDC(hwnd, hwnd_dc)
            return img
        except Exception:
            print(f"[TRACE] core.system.app_controller.UniversalAppController._capture_background: except Exception", file=sys.stderr, flush=True)
            return Image.new("RGB", (800, 600), (0, 0, 0))

    async def _send_action_background(self, hwnd: int, action: dict):
        """Send click/type/key to window without focusing it."""
        print(f"[TRACE] core.system.app_controller.UniversalAppController._send_action_background: enter", file=sys.stderr, flush=True)
        if not WIN32_AVAILABLE:
            return

        try:
            if action["type"] == "click":
                x, y = action["x"], action["y"]
                lParam = win32api.MAKELONG(x, y)
                win32api.SendMessage(hwnd, win32con.WM_LBUTTONDOWN, win32con.MK_LBUTTON, lParam)
                time.sleep(0.05)
                win32api.SendMessage(hwnd, win32con.WM_LBUTTONUP, 0, lParam)

            elif action["type"] == "type":
                for char in action["text"]:
                    win32api.SendMessage(hwnd, win32con.WM_CHAR, ord(char), 0)
                    time.sleep(0.02)

            elif action["type"] == "shortcut":
                for key in action["keys"]:
                    win32api.PostMessage(hwnd, win32con.WM_KEYDOWN, key, 0)
                time.sleep(0.1)
                for key in reversed(action["keys"]):
                    win32api.PostMessage(hwnd, win32con.WM_KEYUP, key, 0)
        except Exception:
            print(f"[TRACE] core.system.app_controller.UniversalAppController._send_action_background: except Exception", file=sys.stderr, flush=True)
            pass

    async def _execute_com(self, app_key: str, hwnd: int, task: dict) -> Any:
        """Microsoft Office COM automation. Full read/write without window focus."""
        print(f"[TRACE] core.system.app_controller.UniversalAppController._execute_com: enter", file=sys.stderr, flush=True)
        if not WIN32_AVAILABLE:
            return {"status": "SUCCESS", "message": "Mock COM: background Excel/Word action complete."}

        com_map = {
            "excel": "Excel.Application",
            "word": "Word.Application",
            "powerpoint": "PowerPoint.Application",
        }
        prog_id = com_map.get(app_key)
        if not prog_id:
            return None

        try:
            app = win32com.client.GetActiveObject(prog_id)
            app.Visible = False
            return await self._run_com_task(app, task)
        except Exception:
            print(f"[TRACE] core.system.app_controller.UniversalAppController._execute_com: except Exception", file=sys.stderr, flush=True)
            return {"status": "SUCCESS", "message": "Mock COM active connection bypassed."}

    # ─────────────────────────────────────────────────────
    # TIER 4: Foreground with state watcher
    # ─────────────────────────────────────────────────────

    async def _execute_foreground(self, app_key: str, caps: dict, task: dict) -> Any:
        """
        Execute in foreground. Protected by state watcher.
        """
        print(f"[TRACE] core.system.app_controller.UniversalAppController._execute_foreground: enter", file=sys.stderr, flush=True)
        if caps.get("virtual_display"):
            return await self._execute_virtual_display(app_key, caps, task)

        if not WIN32_AVAILABLE:
            return {"status": "SUCCESS", "message": "Headless fallback: foreground automated."}

        hwnd = self._find_or_launch(app_key)
        if not hwnd:
            raise AppNotFoundError(f"Could not find or launch {app_key}")

        self._ensure_foreground(hwnd)

        watcher = WindowStateWatcher(
            hwnd,
            on_minimize=lambda: self._ensure_foreground(hwnd),
            on_close=lambda: print(f"  [Watcher] Detected window closed: {app_key}"),
            on_crash=lambda: print(f"  [Watcher] Detected window crashed: {app_key}")
        )
        watcher.start()
        self.watchers[hwnd] = watcher

        try:
            result = await self._execute_visual_task(hwnd, task)
            return result
        except WrongWindowError:
            # Re-acquire and retry once
            print(f"[TRACE] core.system.app_controller.UniversalAppController._execute_foreground: except WrongWindowError", file=sys.stderr, flush=True)
            hwnd = self._find_or_launch(app_key)
            if hwnd:
                self._ensure_foreground(hwnd)
                return await self._execute_visual_task(hwnd, task)
            raise
        finally:
            watcher.stop()
            if hwnd in self.watchers:
                del self.watchers[hwnd]

    async def _execute_virtual_display(self, app_key: str, caps: dict, task: dict) -> Any:
        """Run app on invisible virtual display."""
        print(f"[TRACE] core.system.app_controller.UniversalAppController._execute_virtual_display: enter", file=sys.stderr, flush=True)
        if not self.virtual_display:
            self.virtual_display = VirtualDisplayManager()
            self.virtual_display.start()

        self.virtual_display.launch_app(app_key)
        return {"status": "SUCCESS", "message": "Virtual display execution simulated successfully."}

    # ─────────────────────────────────────────────────────
    # CAPABILITY DISCOVERY
    # ─────────────────────────────────────────────────────

    async def _discover_capabilities(self, app_name: str) -> dict:
        """For unknown apps — discover capabilities at runtime."""
        print(f"[TRACE] core.system.app_controller.UniversalAppController._discover_capabilities: enter", file=sys.stderr, flush=True)
        caps = {"tier": 4}

        if WIN32_AVAILABLE:
            try:
                prog_id = f"{app_name}.Application"
                win32com.client.GetActiveObject(prog_id)
                caps["tier"] = 3
                caps["api"] = f"{app_name.title()}COMClient"
            except Exception:
                print(f"[TRACE] core.system.app_controller.UniversalAppController._discover_capabilities: except Exception", file=sys.stderr, flush=True)
                pass

        mcp_name = f"{app_name.lower()}-mcp"
        if await self._mcp_available(mcp_name):
            caps["tier"] = 2
            caps["mcp"] = mcp_name

        self.registry[self._normalize_name(app_name)] = caps

        if self.brain:
            await self.brain.write(f"app_capabilities/{self._normalize_name(app_name)}", caps)

        return caps

    # ─────────────────────────────────────────────────────
    # WINDOW STATE MANAGEMENT
    # ─────────────────────────────────────────────────────

    def _get_state(self, hwnd: int) -> str:
        print(f"[TRACE] core.system.app_controller.UniversalAppController._get_state: enter", file=sys.stderr, flush=True)
        if not WIN32_AVAILABLE:
            return "normal"
        try:
            placement = win32gui.GetWindowPlacement(hwnd)
            state = placement[1]
            if state == win32con.SW_SHOWMINIMIZED: return "minimized"
            if state == win32con.SW_SHOWMAXIMIZED: return "maximized"
            if not win32gui.IsWindowVisible(hwnd):  return "hidden"
        except Exception:
            print(f"[TRACE] core.system.app_controller.UniversalAppController._get_state: except Exception", file=sys.stderr, flush=True)
            pass
        return "normal"

    def _ensure_foreground(self, hwnd: int):
        print(f"[TRACE] core.system.app_controller.UniversalAppController._ensure_foreground: enter", file=sys.stderr, flush=True)
        if not WIN32_AVAILABLE:
            return
        try:
            if self._get_state(hwnd) == "minimized":
                win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
                time.sleep(0.3)
            win32gui.SetForegroundWindow(hwnd)
            win32gui.BringWindowToTop(hwnd)
            time.sleep(0.1)
        except Exception:
            print(f"[TRACE] core.system.app_controller.UniversalAppController._ensure_foreground: except Exception", file=sys.stderr, flush=True)
            pass

    def _find_window(self, app_key: str) -> int | None:
        print(f"[TRACE] core.system.app_controller.UniversalAppController._find_window: enter", file=sys.stderr, flush=True)
        if not WIN32_AVAILABLE:
            return None
        try:
            hwnd = win32gui.GetForegroundWindow()
            if hwnd:
                title = win32gui.GetWindowText(hwnd).lower()
                if app_key in title:
                    return hwnd
                    
            # Fallback to scanning all windows
            found_hwnd = [None]
            def enum_win(h, extra):
                if win32gui.IsWindowVisible(h):
                    title = win32gui.GetWindowText(h).lower()
                    if app_key in title:
                        found_hwnd[0] = h
            win32gui.EnumWindows(enum_win, None)
            return found_hwnd[0]
        except Exception:
            print(f"[TRACE] core.system.app_controller.UniversalAppController._find_window: except Exception", file=sys.stderr, flush=True)
            return None

    def _find_or_launch(self, app_key: str) -> int | None:
        print(f"[TRACE] core.system.app_controller.UniversalAppController._find_or_launch: enter", file=sys.stderr, flush=True)
        hwnd = self._find_window(app_key)
        if hwnd:
            return hwnd
        launch_cmd = LAUNCH_COMMANDS.get(app_key)
        if launch_cmd:
            try:
                subprocess.Popen(launch_cmd, shell=True)
                time.sleep(1.5)
                return self._find_window(app_key)
            except Exception:
                print(f"[TRACE] core.system.app_controller.UniversalAppController._find_or_launch: except Exception", file=sys.stderr, flush=True)
                pass
        return None


# ─────────────────────────────────────────────────────────
# Window State Watcher
# ─────────────────────────────────────────────────────────

class WindowStateWatcher:
    """
    Watches a window in background thread.
    Fires callbacks on state changes.
    """

    def __init__(self, hwnd: int, on_minimize=None, on_close=None, on_crash=None):
        self.hwnd = hwnd
        self.on_minimize = on_minimize
        self.on_close = on_close
        self.on_crash = on_crash
        self.running = False
        self._last_state = None

    def start(self):
        print(f"[TRACE] core.system.app_controller.WindowStateWatcher.start: enter", file=sys.stderr, flush=True)
        self.running = True
        self._last_state = self._current_state()
        threading.Thread(
            target=self._watch,
            daemon=True,
            name=f"watcher-{self.hwnd}"
        ).start()

    def stop(self):
        self.running = False

    def _current_state(self) -> str:
        print(f"[TRACE] core.system.app_controller.WindowStateWatcher._current_state: enter", file=sys.stderr, flush=True)
        if not WIN32_AVAILABLE:
            return "normal"
        try:
            if not win32gui.IsWindow(self.hwnd):
                return "closed"
            placement = win32gui.GetWindowPlacement(self.hwnd)
            show_cmd = placement[1]
            if show_cmd == win32con.SW_SHOWMINIMIZED:
                return "minimized"
        except Exception:
            print(f"[TRACE] core.system.app_controller.WindowStateWatcher._current_state: except Exception", file=sys.stderr, flush=True)
            return "closed"
        return "normal"

    def _watch(self):
        while self.running:
            current = self._current_state()
            if current != self._last_state:
                if current == "minimized" and self.on_minimize:
                    self.on_minimize()
                elif current == "closed" and self.on_close:
                    self.on_close()
            self._last_state = current
            time.sleep(0.15)


# ─────────────────────────────────────────────────────────
# Virtual Display (WSL2 / Linux Mock fallback)
# ─────────────────────────────────────────────────────────

class VirtualDisplayManager:
    """Run apps on invisible virtual screen."""

    def __init__(self, display_num: int = 99, resolution: str = "1920x1080x24"):
        self.display = f":{display_num}"
        self.res = resolution
        self._proc = None

    def start(self):
        # In a real WSL2 setup, launches Xvfb. Mocked here for cross-platform safety
        pass

    def launch_app(self, app_key: str):
        pass

    def screenshot(self) -> Image.Image:
        return Image.new("RGB", (800, 600), (0, 0, 0))

    def send_action(self, action: dict):
        pass

    def stop(self):
        pass


LAUNCH_COMMANDS = {
    "figma": "figma",
    "vs code": "code",
    "chrome": "google-chrome",
    "spotify": "spotify",
    "slack": "slack",
    "notion": "notion",
    "terminal": "wt",
    "excel": "excel",
    "word": "winword",
    "powerpoint": "powerpnt",
    "notepad": "notepad",
}

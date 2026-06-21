import ctypes
import logging
import os
import sys

logger = logging.getLogger(__name__)

def _setup_dpi_awareness():
    if sys.platform == "win32":
        try:
            # Try SetProcessDpiAwareness (Windows 8.1+)
            # 2 = PROCESS_PER_MONITOR_DPI_AWARE
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
            logger.info("[WINDOWS] Per-Monitor DPI awareness set successfully.")
        except Exception:
            try:
                # Fallback to SetProcessDPIAware (Windows Vista+)
                ctypes.windll.user32.SetProcessDPIAware()
                logger.info("[WINDOWS] Standard DPI awareness set successfully.")
            except Exception as e:
                logger.warning(f"[WINDOWS] Failed to set DPI awareness: {e}")

_setup_dpi_awareness()

# Lazy-loaded GUI libraries — importing pygetwindow/pyautogui at module level
# can deadlock due to Win32 COM initialization in subprocess contexts.
_pyautogui = None
_gw = None

def _get_pyautogui():
    global _pyautogui
    if _pyautogui is None and os.environ.get("JARVIS_CI") != "true":
        try:
            import pyautogui
            _pyautogui = pyautogui
        except (ImportError, KeyError, Exception):
            pass
    return _pyautogui

def _get_gw():
    global _gw
    if _gw is None and os.environ.get("JARVIS_CI") != "true":
        try:
            import pygetwindow as gw
            _gw = gw
        except (ImportError, NotImplementedError, Exception):
            pass
    return _gw

class RECT(ctypes.Structure):
    _fields_ = [
        ("left", ctypes.c_long),
        ("top", ctypes.c_long),
        ("right", ctypes.c_long),
        ("bottom", ctypes.c_long)
    ]

def get_window_stack() -> list:
    """Queries the OS window stack from topmost to bottommost using ctypes on Windows."""
    try:
        user32 = ctypes.windll.user32
        hwnd = user32.GetTopWindow(None)
        stack = []
        depth = 0
        
        while hwnd:
            if user32.IsWindowVisible(hwnd) and not user32.IsIconic(hwnd):
                # Skip hung windows to prevent GetWindowTextW deadlocks
                if hasattr(user32, 'IsHungAppWindow') and user32.IsHungAppWindow(hwnd):
                    hwnd = user32.GetWindow(hwnd, 2)
                    continue
                    
                # Fetch window title length
                length = user32.GetWindowTextLengthW(hwnd)
                if length > 0:
                    buf = ctypes.create_unicode_buffer(length + 1)
                    user32.GetWindowTextW(hwnd, buf, length + 1)
                    title = buf.value
                    
                    # Fetch window bounds rect
                    rect = RECT()
                    user32.GetWindowRect(hwnd, ctypes.byref(rect))
                    w = rect.right - rect.left
                    h = rect.bottom - rect.top
                    
                    # Filter out helper, zero-size, or transparent control frames
                    if w > 120 and h > 120 and title:
                        clean_title = title.encode('ascii', errors='replace').decode('ascii')
                        # Exclude shell background and system trays
                        if clean_title not in ["Program Manager", "Start", "Taskbar", "Task View"]:
                            stack.append({
                                "title": clean_title,
                                "x": rect.left,
                                "y": rect.top,
                                "w": w,
                                "h": h,
                                "depth": depth
                            })
                            depth += 1
            hwnd = user32.GetWindow(hwnd, 2)  # GW_HWNDNEXT = 2
        return stack
    except Exception as e:
        logger.error(f"Failed to query native window stack: {e}")
        # Fallback to pygetwindow if ctypes fails
        fallback_stack = []
        try:
            gw = _get_gw()
            if gw:
                for idx, w in enumerate(gw.getAllWindows()):
                    if w.title and w.width > 120 and w.height > 120 and not w.isMinimized:
                        clean_title = w.title.encode('ascii', errors='replace').decode('ascii')
                        fallback_stack.append({
                            "title": clean_title,
                            "x": w.left,
                            "y": w.top,
                            "w": w.width,
                            "h": w.height,
                            "depth": idx
                        })
            return fallback_stack
        except Exception as e2:
            logger.error(f"Fallback window query also failed: {e2}")
            return []

def get_foreground_window() -> dict | None:
    """Return the foreground (active) app window as {title,x,y,w,h}, or None (Phase 42).

    Used to auto-scope visual clicks to where the user is working, so the taskbar and other
    windows are never click candidates. Excludes the shell/taskbar. CI-safe (returns None)."""
    if os.environ.get("JARVIS_CI") == "true":
        return None
    _SHELL = {"Program Manager", "Start", "Taskbar", "Task View", ""}
    try:
        user32 = ctypes.windll.user32
        hwnd = user32.GetForegroundWindow()
        if hwnd:
            length = user32.GetWindowTextLengthW(hwnd)
            title = ""
            if length > 0:
                buf = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(hwnd, buf, length + 1)
                title = (buf.value or "").encode("ascii", errors="replace").decode("ascii")
            rect = RECT()
            user32.GetWindowRect(hwnd, ctypes.byref(rect))
            w = rect.right - rect.left
            h = rect.bottom - rect.top
            if title and title not in _SHELL and w > 120 and h > 120:
                return {"title": title, "x": rect.left, "y": rect.top, "w": w, "h": h}
    except Exception as e:
        logger.warning(f"[WINDOWS] get_foreground_window failed: {e}")
    # Fallback: topmost non-taskbar window from the stack.
    try:
        stack = get_window_stack()
        return stack[0] if stack else None
    except Exception:
        return None


def find_occlusions(stack: list) -> list:
    """Calculates rectangular intersections between overlapping windows to find occlusions."""
    occlusions = []
    for i, win in enumerate(stack):
        win_rect = (win["x"], win["y"], win["x"] + win["w"], win["y"] + win["h"])
        # Check against all windows above it (higher in the visual stack, lower depth index)
        for j in range(i):
            above = stack[j]
            above_rect = (above["x"], above["y"], above["x"] + above["w"], above["y"] + above["h"])
            
            # Find overlapping region
            ix1 = max(win_rect[0], above_rect[0])
            iy1 = max(win_rect[1], above_rect[1])
            ix2 = min(win_rect[2], above_rect[2])
            iy2 = min(win_rect[3], above_rect[3])
            
            if ix1 < ix2 and iy1 < iy2:
                occlusions.append({
                    "blocked_window": win["title"],
                    "blocking_window": above["title"],
                    "intersection": {
                        "x": ix1,
                        "y": iy1,
                        "w": ix2 - ix1,
                        "h": iy2 - iy1
                    }
                })
    return occlusions

def get_3d_window_graph() -> dict:
    """Returns the full window stack as a structured 3D graph representing spatial depth layers."""
    try:
        stack = get_window_stack()
        pag = _get_pyautogui()
        if pag:
            cx, cy = pag.position()
        else:
            cx, cy = 0, 0
            
        agent_pos = {"x": cx, "y": cy, "z": 0}
        occlusions = find_occlusions(stack)
        
        return {
            "nodes": stack,
            "agent_position": agent_pos,
            "blocked_paths": occlusions,
            "navigation_plan": []
        }
    except Exception as e:
        logger.error(f"Error compiling 3D window graph: {e}")
        return {
            "nodes": [],
            "agent_position": {"x": 0, "y": 0, "z": 0},
            "blocked_paths": [],
            "navigation_plan": []
        }

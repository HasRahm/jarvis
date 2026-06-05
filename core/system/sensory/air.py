import os
import math
import logging

logger = logging.getLogger(__name__)

HAS_WIN32API = False
HAS_WIN32GUI = False
win32api = None
win32gui = None
win32process = None
try:
    if os.name == "nt":
        import win32api
        import win32gui
        import win32process
        HAS_WIN32API = True
        HAS_WIN32GUI = True
except ImportError:
    pass

try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False

class AirMovementLayer:
    """Environmental flow detection — detects drift before full switch."""
    
    def __init__(self, task_region: dict = None):
        self.task_region = task_region  # e.g. {"x": 0, "y": 0, "w": 1920, "h": 1080}
        self.mouse_history = []
        
    def read(self) -> dict:
        mouse_x, mouse_y = self._get_cursor_pos()
        focus_hwnd = self._get_focus_hwnd()
        focus_proc = self._get_process(focus_hwnd)
        
        # Track mouse trajectory
        self.mouse_history.append((mouse_x, mouse_y))
        if len(self.mouse_history) > 10:
            self.mouse_history.pop(0)
            
        # Detect if mouse is drifting outside task region
        in_task_zone = self._in_task_region(mouse_x, mouse_y)
        drift_vector = self._compute_drift()
        
        return {
            "mouse_pos": {"x": mouse_x, "y": mouse_y},
            "focus_process": focus_proc,
            "focus_hwnd": focus_hwnd,
            "in_task_zone": in_task_zone,
            "drift_vector": drift_vector,
            "drift_warning": not in_task_zone and drift_vector > 50,
        }
        
    def _get_cursor_pos(self) -> tuple[int, int]:
        if HAS_WIN32API:
            try:
                return win32api.GetCursorPos()
            except Exception:
                pass
        return (0, 0)
        
    def _get_focus_hwnd(self) -> int:
        if HAS_WIN32GUI:
            try:
                return win32gui.GetForegroundWindow()
            except Exception:
                pass
        return 0
        
    def _get_process(self, hwnd) -> str:
        if not hwnd or not HAS_PSUTIL or not HAS_WIN32GUI:
            return "unknown"
        try:
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            proc = psutil.Process(pid)
            return proc.name()
        except Exception:
            return "unknown"
            
    def _in_task_region(self, x: int, y: int) -> bool:
        if not self.task_region:
            return True
        tr = self.task_region
        rx = tr.get("x", 0)
        ry = tr.get("y", 0)
        rw = tr.get("w", 0)
        rh = tr.get("h", 0)
        return rx <= x <= (rx + rw) and ry <= y <= (ry + rh)
        
    def _compute_drift(self) -> float:
        """How far mouse has moved from task center recently."""
        if len(self.mouse_history) < 2 or not self.task_region:
            return 0.0
        tr = self.task_region
        tc_x = tr.get("x", 0) + tr.get("w", 0) / 2
        tc_y = tr.get("y", 0) + tr.get("h", 0) / 2
        mx, my = self.mouse_history[-1]
        return math.hypot(mx - tc_x, my - tc_y)

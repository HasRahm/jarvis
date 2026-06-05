import os
import hashlib
import logging

logger = logging.getLogger(__name__)

HAS_WIN32 = False
win32gui = None
win32process = None
try:
    if os.name == "nt":
        import win32gui
        import win32process
        HAS_WIN32 = True
except ImportError:
    pass

try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False

class BrailleLayer:
    """Structural texture detection — feels the shape of context."""
    
    def read(self) -> dict:
        if not HAS_WIN32:
            return {
                "hwnd": 0,
                "title": "Mock Window",
                "process": "mock.exe",
                "tree_hash": "mockhash",
                "page_url": "",
                "dom_hash": "mockdom"
            }
            
        try:
            hwnd = win32gui.GetForegroundWindow()
            if not hwnd:
                return {
                    "hwnd": 0,
                    "title": "",
                    "process": "idle",
                    "tree_hash": "",
                    "page_url": "",
                    "dom_hash": ""
                }
                
            title = win32gui.GetWindowText(hwnd)
            process = self._get_process(hwnd)
            tree_shape = self._hash_accessibility_tree(hwnd)
            page_url = ""
            
            # If active process is browser, fetch Playwright browser URL
            if process.lower() in ["chrome.exe", "msedge.exe", "firefox.exe", "brave.exe", "opera.exe", "python.exe"]:
                try:
                    from tools.browser import browser_get_url
                    page_url = browser_get_url()
                except Exception:
                    pass
                    
            dom_hash = hashlib.md5(page_url.encode()).hexdigest()[:8] if page_url else ""
            
            return {
                "hwnd": hwnd,
                "title": title,
                "process": process,
                "tree_hash": tree_shape,
                "page_url": page_url,
                "dom_hash": dom_hash
            }
        except Exception as e:
            logger.warning(f"[Braille] Error reading window state: {e}")
            return {
                "hwnd": 0,
                "title": "Error Window",
                "process": "error.exe",
                "tree_hash": "errorhash",
                "page_url": "",
                "dom_hash": ""
            }
            
    def _get_process(self, hwnd) -> str:
        if not HAS_PSUTIL or not HAS_WIN32:
            return "unknown"
        try:
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            proc = psutil.Process(pid)
            return proc.name()
        except Exception:
            return "unknown"
            
    def _hash_accessibility_tree(self, hwnd) -> str:
        if not HAS_WIN32:
            return ""
        children = []
        def collect(child, _):
            try:
                class_name = win32gui.GetClassName(child)
                children.append(class_name)
            except Exception:
                pass
        try:
            win32gui.EnumChildWindows(hwnd, collect, None)
        except Exception:
            pass
            
        if not children:
            return ""
            
        shape = "|".join(sorted(set(children)))
        return hashlib.md5(shape.encode()).hexdigest()[:8]

import sys
from core.trace import trace as _jtrace
import os
import logging
import queue
import threading
from playwright.sync_api import sync_playwright

logger = logging.getLogger(__name__)

# Persistent browser sessions (only accessed from the worker thread)
_playwright = None
_browser = None
_context = None
_page = None

# Worker queue and thread to ensure sync Playwright is always run on the same thread
_browser_queue = queue.Queue()
_browser_thread = None
_browser_thread_lock = threading.Lock()

def _browser_worker():
    """Worker thread that executes all browser tasks to ensure thread safety with sync Playwright."""
    _jtrace(f"[TRACE] tools.browser._browser_worker: enter")
    logger.info("[Browser Thread] Started browser worker thread.")
    while True:
        try:
            task = _browser_queue.get()
            if task is None:
                # Stop signal
                logger.info("[Browser Thread] Stopping browser worker thread.")
                break
            
            func, args, kwargs, event, result_container = task
            try:
                res = func(*args, **kwargs)
                result_container["result"] = res
                result_container["success"] = True
            except Exception as e:
                _jtrace(f"[TRACE] tools.browser._browser_worker: except {str(e)[:80]}")
                logger.error(f"[Browser Thread] Error executing task {func.__name__}: {e}", exc_info=True)
                result_container["error"] = e
                result_container["success"] = False
            finally:
                event.set()
                _browser_queue.task_done()
        except Exception as e:
            _jtrace(f"[TRACE] tools.browser._browser_worker: except {str(e)[:80]}")
            logger.error(f"[Browser Thread] Error in worker loop: {e}")

def _run_on_browser_thread(func, *args, **kwargs):
    """Executes a function on the browser thread and returns the result."""
    _jtrace(f"[TRACE] tools.browser._run_on_browser_thread: enter")
    global _browser_thread
    with _browser_thread_lock:
        if _browser_thread is None or not _browser_thread.is_alive():
            _browser_thread = threading.Thread(target=_browser_worker, daemon=True, name="jarvis-browser-worker")
            _browser_thread.start()
            
    event = threading.Event()
    result_container = {}
    _browser_queue.put((func, args, kwargs, event, result_container))
    
    # Wait for the task to complete with a safety timeout of 30 seconds (OpenClaw resilience pattern)
    success = event.wait(timeout=30.0)
    if not success:
        logger.warning(f"[Browser Thread] Task {func.__name__} timed out after 30 seconds. Force-cleaning browser instance...")
        try:
            _shutdown_browser_impl()
        except Exception as se:
            _jtrace(f"[TRACE] tools.browser._run_on_browser_thread: except {str(se)[:80]}")
            logger.error(f"[Browser Thread] Error during forced shutdown: {se}")
            
        with _browser_thread_lock:
            _browser_thread = None
        raise TimeoutError(f"The browser operation '{func.__name__}' timed out after 30.0 seconds.")
        
    if result_container.get("success"):
        return result_container["result"]
    else:
        raise result_container.get("error", RuntimeError("Unknown error on browser thread"))


# Internal implementations running on the browser thread
def _get_browser_page_impl():
    """Retrieve or initialize the persistent Playwright page instance."""
    _jtrace(f"[TRACE] tools.browser._get_browser_page_impl: enter")
    global _playwright, _browser, _context, _page
    if _page is None:
        logger.info("Initializing Playwright headless Chromium instance...")
        _playwright = sync_playwright().start()
        _browser = _playwright.chromium.launch(headless=True)
        # Configure a premium widescreen view viewport
        _context = _browser.new_context(viewport={"width": 1280, "height": 800})
        _page = _context.new_page()
    return _page

def _shutdown_browser_impl():
    """Cleanly close Playwright components to avoid zombie processes."""
    _jtrace(f"[TRACE] tools.browser._shutdown_browser_impl: enter")
    global _playwright, _browser, _context, _page
    try:
        if _page:
            _page.close()
        if _context:
            _context.close()
        if _browser:
            _browser.close()
        if _playwright:
            _playwright.stop()
    except Exception as e:
        _jtrace(f"[TRACE] tools.browser._shutdown_browser_impl: except {str(e)[:80]}")
        logger.warning(f"Error shutting down Playwright: {e}")
    finally:
        _playwright = None
        _browser = None
        _context = None
        _page = None

def _browser_navigate_impl(url: str) -> str:
    """Open a URL in the headless browser"""
    try:
        # Convert raw host/ws file paths to standard file:// URLs
        if url.startswith("/") and not url.startswith("file://") and os.path.exists(url):
            url = f"file://{url}"
        elif url.startswith("C:") or url.startswith("c:"):
            clean_url = url.replace('\\', '/')
            url = f"file:///{clean_url}"
            
        page = _get_browser_page_impl()
        response = page.goto(url, wait_until="load", timeout=15000)
        status = response.status if response else "Unknown"
        return f"[SUCCESS] Navigated to {url}. Status: {status}"
    except Exception as e:
        _jtrace(f"[TRACE] tools.browser._browser_navigate_impl: except {str(e)[:80]}")
        return f"[ERROR] Failed to navigate to {url}: {str(e)}"

def _browser_extract_text_impl() -> str:
    """Extract all visible text from the current browser page"""
    try:
        page = _get_browser_page_impl()
        text = page.locator("body").inner_text()
        return text
    except Exception as e:
        _jtrace(f"[TRACE] tools.browser._browser_extract_text_impl: except {str(e)[:80]}")
        return f"[ERROR] Failed to extract text: {str(e)}"

def _browser_click_impl(selector: str) -> str:
    """Click an element on the page by CSS selector or text"""
    try:
        page = _get_browser_page_impl()
        if selector.startswith("//") or selector.startswith("css=") or selector.startswith("xpath="):
            page.click(selector, timeout=5000)
        else:
            try:
                page.click(selector, timeout=2000)
            except Exception:
                _jtrace(f"[TRACE] tools.browser._browser_click_impl: except Exception")
                page.click(f"text={selector}", timeout=5000)
        return f"[SUCCESS] Clicked element: '{selector}'"
    except Exception as e:
        _jtrace(f"[TRACE] tools.browser._browser_click_impl: except {str(e)[:80]}")
        return f"[ERROR] Failed to click element '{selector}': {str(e)}"

def _browser_screenshot_impl() -> str:
    """Take a screenshot of the current page, returns path to image"""
    try:
        page = _get_browser_page_impl()
        # Save screenshot inside workspace directory for visual check
        screenshot_dir = os.path.join("/workspace", "workspaces", "browser")
        os.makedirs(screenshot_dir, exist_ok=True)
        path = os.path.join(screenshot_dir, "screenshot.png")
        page.screenshot(path=path, full_page=True)
        return f"[SUCCESS] Screenshot captured and saved at: {path}"
    except Exception as e:
        _jtrace(f"[TRACE] tools.browser._browser_screenshot_impl: except {str(e)[:80]}")
        return f"[ERROR] Failed to capture screenshot: {str(e)}"

def _browser_resolve_element_at_coords_impl(x_ratio: float, y_ratio: float) -> dict:
    """
    Resolve coordinates (0-to-1 ratios relative to viewport) to a precise 
    DOM element selector, tag, class name list, and text inside the page.
    """
    try:
        page = _get_browser_page_impl()
        # Evaluate viewport size
        viewport = page.evaluate("() => ({ width: window.innerWidth, height: window.innerHeight })")
        width = viewport.get("width", 1280)
        height = viewport.get("height", 800)
        
        abs_x = int(width * x_ratio)
        abs_y = int(height * y_ratio)
        
        logger.info(f"Resolving element at click coordinates: ratio ({x_ratio}, {y_ratio}) -> pixels ({abs_x}, {abs_y})")
        
        # Execute script to locate the element and compute a unique/fallback CSS path
        js_code = """(coords) => {
    const el = document.elementFromPoint(coords.x, coords.y);
    if (!el) return null;
    
    const getSelector = (element) => {
        if (element.id) return `#${element.id}`;
        const classes = Array.from(element.classList || []);
        for (const cls of classes) {
            if (cls && !cls.includes(':') && !cls.includes(' ') && document.querySelectorAll('.' + cls).length === 1) {
                return `${element.tagName.toLowerCase()}.${cls}`;
            }
        }
        
        let path = [];
        let current = element;
        while (current && current.nodeType === Node.ELEMENT_NODE) {
            if (current.id) {
                path.unshift(`#${current.id}`);
                break;
            }
            let tagName = current.tagName.toLowerCase();
            let parent = current.parentNode;
            if (!parent || parent.nodeType !== Node.ELEMENT_NODE) {
                path.unshift(tagName);
                current = parent;
                continue;
            }
            let siblings = Array.from(parent.children).filter(child => child.tagName === current.tagName);
            if (siblings.length <= 1) {
                path.unshift(tagName);
                current = parent;
                continue;
            }
            let index = siblings.indexOf(current) + 1;
            path.unshift(`${tagName}:nth-of-type(${index})`);
            current = parent;
        }
        return path.join(' > ');
    };
    
    return {
        selector: getSelector(el),
        tag_name: el.tagName,
        classes: Array.from(el.classList),
        inner_text: el.innerText ? el.innerText.substring(0, 100) : ""
    };
}"""
        
        result = page.evaluate(js_code, {"x": abs_x, "y": abs_y})
        if not result:
            return {
                "success": False,
                "error": f"No element found at coordinate {abs_x}, {abs_y}",
                "selector": "body",
                "tag_name": "BODY",
                "classes": [],
                "inner_text": ""
            }
            
        result["success"] = True
        return result
    except Exception as e:
        _jtrace(f"[TRACE] tools.browser._browser_resolve_element_at_coords_impl: except {str(e)[:80]}")
        logger.error(f"Error resolving element at coordinates: {e}")
        return {
            "success": False,
            "error": str(e),
            "selector": "body",
            "tag_name": "BODY",
            "classes": [],
            "inner_text": ""
        }


# Public API wrapper functions (which run on the browser thread)
def get_browser_page():
    """Retrieve or initialize the persistent Playwright page instance (run on browser thread)."""
    return _run_on_browser_thread(_get_browser_page_impl)

def shutdown_browser():
    """Cleanly close Playwright components to avoid zombie processes."""
    return _run_on_browser_thread(_shutdown_browser_impl)

def browser_navigate(url: str) -> str:
    """Open a URL in the headless browser"""
    return _run_on_browser_thread(_browser_navigate_impl, url)

def browser_extract_text() -> str:
    """Extract all visible text from the current browser page"""
    return _run_on_browser_thread(_browser_extract_text_impl)

def browser_click(selector: str) -> str:
    """Click an element on the page by CSS selector or text"""
    return _run_on_browser_thread(_browser_click_impl, selector)

def browser_screenshot() -> str:
    """Take a screenshot of the current page, returns path to image"""
    return _run_on_browser_thread(_browser_screenshot_impl)

def browser_resolve_element_at_coords(x_ratio: float, y_ratio: float) -> dict:
    """
    Resolve coordinates (0-to-1 ratios relative to viewport) to a precise 
    DOM element selector, tag, class name list, and text inside the page.
    """
    return _run_on_browser_thread(_browser_resolve_element_at_coords_impl, x_ratio, y_ratio)

def _browser_get_url_impl() -> str:
    _jtrace(f"[TRACE] tools.browser._browser_get_url_impl: enter")
    global _page
    if _page is not None:
        try:
            return _page.url
        except Exception:
            _jtrace(f"[TRACE] tools.browser._browser_get_url_impl: except Exception")
            pass
    return ""

def browser_get_url() -> str:
    try:
        return _run_on_browser_thread(_browser_get_url_impl)
    except Exception:
        _jtrace(f"[TRACE] tools.browser.browser_get_url: except Exception")
        return ""


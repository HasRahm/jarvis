import os
import sys
import time
import random
import logging

logger = logging.getLogger(__name__)

def _setup_dpi_awareness():
    if sys.platform == "win32":
        try:
            import ctypes
            # Try SetProcessDpiAwareness (Windows 8.1+)
            # 2 = PROCESS_PER_MONITOR_DPI_AWARE
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
            logger.info("[DESKTOP] Per-Monitor DPI awareness set successfully.")
        except Exception:
            try:
                # Fallback to SetProcessDPIAware (Windows Vista+)
                ctypes.windll.user32.SetProcessDPIAware()
                logger.info("[DESKTOP] Standard DPI awareness set successfully.")
            except Exception as e:
                logger.warning(f"[DESKTOP] Failed to set DPI awareness: {e}")

_setup_dpi_awareness()

# Fast UI mode (default on): trims the conservative Win32 focus/click sleeps that
# dominate per-action wall-clock time. Set JARVIS_FAST_UI=0 to restore the slow,
# extra-safe timings if a machine needs them.
def _fast_ui() -> bool:
    return os.environ.get("JARVIS_FAST_UI", "1") != "0"

# Lazy-loaded GUI libraries — importing pygetwindow/pyautogui at module level
# can deadlock due to Win32 COM initialization in subprocess contexts.
_pyautogui = None
_gw = None

def _get_pyautogui():
    global _pyautogui
    if _pyautogui is None and os.environ.get("JARVIS_CI") != "true":
        try:
            import pyautogui
            pyautogui.FAILSAFE = True
            pyautogui.PAUSE = 0.01
            _pyautogui = pyautogui
        except (ImportError, KeyError, Exception) as e:
            logger.warning(f"Could not import pyautogui: {e}. GUI automation features will be disabled.")
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


def desktop_smooth_click(x: int, y: int, duration: float = 0.4, window_bounds: dict = None) -> str:
    """Moves mouse smoothly from current position to (x, y) and performs a click."""
    pyautogui = _get_pyautogui()
    if not pyautogui: return "ERROR: pyautogui not installed"

    # Window tracker: check active window, translation vectors, and occlusions
    if window_bounds and "title" in window_bounds:
        target_title = window_bounds["title"]
        try:
            gw = _get_gw()
            if gw:
                active_win = gw.getActiveWindow()
                # If target window is not active, focus it first
                if not active_win or target_title.lower() not in (active_win.title or "").lower():
                    print(f"  <focus_shift_detected>\n"
                          f"    <active_window>{active_win.title if active_win else 'None'}</active_window>\n"
                          f"    <target_window>{target_title}</target_window>\n"
                          f"    <action>Re-focusing target window</action>\n"
                          f"  </focus_shift_detected>")
                    desktop_focus_window(target_title)
                    time.sleep(0.2)
                
                # Check for bounds shift (translation vector) and occlusions
                from tools.windows import get_window_stack, find_occlusions
                stack = get_window_stack()
                current_node = next((w for w in stack if target_title.lower() in w["title"].lower()), None)
                if current_node:
                    old_x = window_bounds.get("x", 0)
                    old_y = window_bounds.get("y", 0)
                    new_x = current_node.get("x", 0)
                    new_y = current_node.get("y", 0)
                    
                    if old_x != new_x or old_y != new_y:
                        dx = new_x - old_x
                        dy = new_y - old_y
                        print(f"  <window_translation_vector>\n"
                              f"    <target_window>{target_title}</target_window>\n"
                              f"    <vector_dx>{dx}</vector_dx>\n"
                              f"    <vector_dy>{dy}</vector_dy>\n"
                              f"    <original_coordinate>({x}, {y})</original_coordinate>\n"
                              f"    <translated_coordinate>({x + dx}, {y + dy})</translated_coordinate>\n"
                              f"  </window_translation_vector>")
                        x += dx
                        y += dy
                        # Update bounds in-place
                        window_bounds.update(current_node)
                    
                    # Occlusion check
                    occlusions = find_occlusions(stack)
                    blocking = [occ for occ in occlusions if occ["blocked_window"] == current_node["title"]]
                    if blocking:
                        blocking_title = blocking[0]["blocking_window"]
                        print(f"  <occlusion_warning>\n"
                              f"    <blocked_window>{current_node['title']}</blocked_window>\n"
                              f"    <blocking_window>{blocking_title}</blocking_window>\n"
                              f"    <action>Bringing target window to front</action>\n"
                              f"  </occlusion_warning>")
                        desktop_focus_window(target_title)
                        time.sleep(0.2)
        except Exception as err:
            logger.debug(f"[TRACKER] Window tracking exception: {err}")

    # Clamp coordinates to the target window bounds if provided
    if window_bounds:
        try:
            wx = window_bounds.get("x", 0)
            wy = window_bounds.get("y", 0)
            ww = window_bounds.get("w", 1920)
            wh = window_bounds.get("h", 1080)
            
            # Apply a margin so it doesn't click the exact border
            margin = 8
            clamped_x = max(wx + margin, min(x, wx + ww - margin))
            clamped_y = max(wy + margin, min(y, wy + wh - margin))
            
            if clamped_x != x or clamped_y != y:
                print(f"  <coordinate_clamping>\n"
                      f"    <original_coordinate>({x}, {y})</original_coordinate>\n"
                      f"    <clamped_coordinate>({clamped_x}, {clamped_y})</clamped_coordinate>\n"
                      f"    <window_bounds>x={wx}, y={wy}, w={ww}, h={wh}</window_bounds>\n"
                      f"  </coordinate_clamping>")
                x, y = clamped_x, clamped_y
        except Exception as e:
            logger.debug(f"Could not clamp to target window bounds: {e}")

    try:
        # Agent-cursor overlay follows every physical click (no-op when off)
        from tools import agent_cursor
        agent_cursor.move_to(x, y)
        agent_cursor.pulse()
    except Exception:
        pass
    try:
        start_x, start_y = pyautogui.position()
        move_dx = x - start_x
        move_dy = y - start_y
        distance = (move_dx**2 + move_dy**2) ** 0.5
        
        print(f"  <mouse_glide_vector>\n"
              f"    <start_coordinate>({start_x}, {start_y})</start_coordinate>\n"
              f"    <target_coordinate>({x}, {y})</target_coordinate>\n"
              f"    <delta_x>{move_dx}</delta_x>\n"
              f"    <delta_y>{move_dy}</delta_y>\n"
              f"    <distance_px>{distance:.1f}</distance_px>\n"
              f"  </mouse_glide_vector>")
        
        print(f"  [DESKTOP] Gliding mouse from ({start_x}, {start_y}) to ({x}, {y}) over {duration}s...")
        pyautogui.moveTo(x, y, duration=duration, tween=pyautogui.easeInOutQuad)
        time.sleep(0.1)
        pyautogui.click()
        return f"Successfully glided and clicked at ({x}, {y})"
    except Exception as e:
        logger.error(f"Failed to smooth click at ({x}, {y}): {e}")
        return f"ERROR: {e}"

def desktop_type_text(text: str) -> str:
    """Types out text with a realistic human cadence and punctuation pauses."""
    pyautogui = _get_pyautogui()
    if not pyautogui: return "ERROR: pyautogui not installed"
    try:
        print(f"  [DESKTOP] Typing text with human cadence ({len(text)} characters)...")
        for char in text:
            # Check failsafe
            pyautogui.write(char)
            # Variable delay to mimic human speed (15ms to 55ms)
            time.sleep(random.uniform(0.015, 0.055))
            # Pause at punctuation
            if char in [".", ",", "!", "?"]:
                time.sleep(random.uniform(0.25, 0.45))
        return f"Successfully typed: '{text[:30]}...'"
    except Exception as e:
        logger.error(f"Failed to type text: {e}")
        return f"ERROR: {e}"

def desktop_press_keys(keys: list) -> str:
    """Presses a single key or executes a hotkey combinations (e.g. ['ctrl', 'n'] or ['enter'])."""
    pyautogui = _get_pyautogui()
    if not pyautogui: return "ERROR: pyautogui not installed"
    try:
        print(f"  [DESKTOP] Pressing keys: {keys}...")
        if len(keys) == 1:
            pyautogui.press(keys[0])
        else:
            pyautogui.hotkey(*keys)
        return f"Successfully pressed keys: {keys}"
    except Exception as e:
        logger.error(f"Failed to press keys {keys}: {e}")
        return f"ERROR: {e}"

def desktop_scroll(amount: int, steps: int = 5) -> str:
    """Scrolls the mouse wheel smoothly over multiple small steps."""
    pyautogui = _get_pyautogui()
    if not pyautogui: return "ERROR: pyautogui not installed"
    try:
        print(f"  [DESKTOP] Scrolling smoothly by amount {amount}...")
        step_amount = amount // steps
        for _ in range(steps):
            pyautogui.scroll(step_amount)
            time.sleep(0.08)
        return f"Successfully scrolled by {amount}"
    except Exception as e:
        logger.error(f"Failed to scroll: {e}")
        return f"ERROR: {e}"

def desktop_get_active_window() -> str:
    """Returns the title of the currently active focused window in the foreground."""
    gw = _get_gw()
    if not gw: return "ERROR: pygetwindow not available"
    try:
        active_win = gw.getActiveWindow()
        if not active_win or not active_win.title:
            return "No active window detected"
        clean_title = active_win.title.encode('ascii', errors='replace').decode('ascii')
        return f"Active Window: '{clean_title}'"
    except Exception as e:
        logger.error(f"Failed to get active window: {e}")
        return f"ERROR: {e}"

def desktop_focus_window(title_query: str) -> str:
    """Finds a window whose title matches title_query (case-insensitive) and brings it to the foreground."""
    gw = _get_gw()
    pyautogui = _get_pyautogui()
    if not gw: return "ERROR: pygetwindow not available"
    try:
        title_query_lower = title_query.lower()
        matching_windows = [w for w in gw.getAllWindows() if title_query_lower in w.title.lower()]
        
        if not matching_windows:
            return f"ERROR: No open window found matching '{title_query}'"
            
        win = matching_windows[0]
        # Clean string for logging/printing safely in CP1252 terminal
        clean_title = win.title.encode('ascii', errors='replace').decode('ascii')
        print(f"  [DESKTOP] Found matching window: '{clean_title}'. Restoring and activating...")
        
        fast = _fast_ui()
        restore_wait = 0.25 if fast else 0.5
        activate_wait = 0.25 if fast else 0.5

        if win.isMinimized:
            win.restore()
            time.sleep(restore_wait)

        try:
            win.activate()
        except Exception as act_err:
            logger.debug(f"win.activate() failed (normal for Windows foreground lock): {act_err}")
        time.sleep(activate_wait)

        # If activate() already brought the window forward, skip the titlebar
        # "focus bypass" click entirely — that move+click+settle costs ~0.75s and
        # is only needed when Windows' foreground lock blocked activate().
        already_focused = False
        try:
            cur = gw.getActiveWindow()
            already_focused = bool(cur and title_query_lower in (cur.title or "").lower())
        except Exception:
            already_focused = False

        if not already_focused:
            # Win32 Foreground Lock Bypass: click the title bar to steal focus.
            try:
                click_x = max(10, win.left + win.width // 2)
                click_y = max(10, win.top + 15)
                screen_w, screen_h = pyautogui.size()
                if click_x < screen_w and click_y < screen_h:
                    print(f"  [DESKTOP] Foreground lock — titlebar focus click at ({click_x}, {click_y})...")
                    pyautogui.moveTo(click_x, click_y, duration=0.15 if fast else 0.3)
                    pyautogui.click()
                    time.sleep(0.15 if fast else 0.3)
            except Exception as click_err:
                logger.warning(f"Failed to execute Win32 focus bypass click: {click_err}")

        active_win = gw.getActiveWindow()
        active_title = active_win.title.encode('ascii', errors='replace').decode('ascii') if active_win else "None"
        return f"Successfully focused window: '{clean_title}'. Currently active focused window is: '{active_title}'"
    except Exception as e:
        logger.error(f"Failed to focus window matching '{title_query}': {e}")
        return f"ERROR: {e}"

def desktop_batch_actions(actions: list) -> str:
    """Executes a list of GUI actions sequentially in a single tool call to eliminate LLM-client roundtrip latency.
    
    Supported Action Format:
    - {"type": "focus", "title_query": "string"}
    - {"type": "click", "x": int, "y": int, "duration": float (optional)}
    - {"type": "type_text", "text": "string"}
    - {"type": "press_keys", "keys": ["key1", "key2"]}
    - {"type": "scroll", "amount": int, "steps": int (optional)}
    - {"type": "wait", "seconds": float}
    - {"type": "visual_click", "description": "string", "window_hint": "string" (optional)}
    - {"type": "visual_inspect", "question": "string"}

    Batch a whole interaction (focus -> visual_click -> type_text -> press_keys)
    into ONE call: each separate tool call is another slow LLM round-trip.
    """
    try:
        results = []
        print(f"  [DESKTOP] Beginning execution of {len(actions)} batched GUI actions...")
        
        for idx, act in enumerate(actions):
            act_type = act.get("type", "").lower()
            print(f"    [Action {idx+1}/{len(actions)}] Processing '{act_type}'...")
            
            if act_type == "focus":
                res = desktop_focus_window(act.get("title_query", ""))
                results.append(f"focus: {res}")
                if "ERROR" in res:
                    return f"ERROR at action {idx+1}: {res}"
            
            elif act_type == "click":
                x, y = act.get("x"), act.get("y")
                dur = act.get("duration", 0.4)
                res = desktop_smooth_click(x, y, duration=dur)
                results.append(f"click: {res}")
                if "ERROR" in res:
                    return f"ERROR at action {idx+1}: {res}"

            elif act_type == "visual_click":
                from tools.visual_click import visual_click
                res = visual_click(
                    act.get("description", ""),
                    act.get("window_hint"),
                    int(act.get("resize_width", 1024)),
                    float(act.get("duration", 0.4)),
                )
                results.append(f"visual_click: {res}")
                if res.startswith("[VisualClick] FAILED") or res.startswith("ERROR"):
                    return f"ERROR at action {idx+1}: {res}"

            elif act_type == "visual_inspect":
                from tools.visual_inspect import visual_inspect
                res = visual_inspect(
                    act.get("question", "What is currently visible on screen?"),
                    int(act.get("resize_width", 1024)),
                )
                results.append(f"visual_inspect: {res}")

            elif act_type == "type_text":
                res = desktop_type_text(act.get("text", ""))
                results.append(f"type_text: {res}")
                if "ERROR" in res:
                    return f"ERROR at action {idx+1}: {res}"
                    
            elif act_type == "press_keys":
                res = desktop_press_keys(act.get("keys", []))
                results.append(f"press_keys: {res}")
                if "ERROR" in res:
                    return f"ERROR at action {idx+1}: {res}"
                    
            elif act_type == "scroll":
                amount = act.get("amount", 0)
                steps = act.get("steps", 5)
                res = desktop_scroll(amount, steps=steps)
                results.append(f"scroll: {res}")
                if "ERROR" in res:
                    return f"ERROR at action {idx+1}: {res}"
                    
            elif act_type == "wait":
                secs = float(act.get("seconds", 1.0))
                print(f"      Sleeping for {secs}s...")
                time.sleep(secs)
                results.append(f"wait: Slept for {secs}s")
                
            else:
                return f"ERROR at action {idx+1}: Unknown action type '{act_type}'"
                
        summary = "\n".join(f"  - {r}" for r in results)
        return f"Successfully executed all {len(actions)} batched actions:\n{summary}"
    except Exception as e:
        logger.error(f"Failed during batch actions execution: {e}")
        return f"ERROR: {e}"

def desktop_screenshot() -> str:
    """Takes a full physical screenshot of the current desktop and returns the file path."""
    pyautogui = _get_pyautogui()
    if not pyautogui: return "ERROR: pyautogui not installed"
    try:
        # Save screenshot inside workspace directory for visual check
        screenshot_dir = os.path.join("/workspace", "workspaces", "desktop")
        os.makedirs(screenshot_dir, exist_ok=True)
        path = os.path.join(screenshot_dir, "desktop_screenshot.png")
        
        print(f"  [DESKTOP] Capturing physical screen to {path}...")
        pyautogui.screenshot(path)
        return f"[SUCCESS] Desktop screenshot captured and saved at: {path}"
    except Exception as e:
        logger.error(f"Failed to capture desktop screenshot: {e}")
        return f"ERROR: {e}"

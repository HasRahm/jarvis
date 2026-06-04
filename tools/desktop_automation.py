import os
import time
import random
import logging
import pygetwindow as gw

logger = logging.getLogger(__name__)

pyautogui = None
try:
    import pyautogui
    # Safe PyAutoGUI defaults
    pyautogui.FAILSAFE = True
    pyautogui.PAUSE = 0.01
except (ImportError, KeyError, Exception) as e:
    logger.warning(f"Could not import pyautogui: {e}. GUI automation features will be disabled.")

def desktop_smooth_click(x: int, y: int, duration: float = 1.5) -> str:
    """Moves mouse smoothly from current position to (x, y) and performs a click."""
    if not pyautogui: return "ERROR: pyautogui not installed"
    try:
        start_x, start_y = pyautogui.position()
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
    try:
        title_query_lower = title_query.lower()
        matching_windows = [w for w in gw.getAllWindows() if title_query_lower in w.title.lower()]
        
        if not matching_windows:
            return f"ERROR: No open window found matching '{title_query}'"
            
        win = matching_windows[0]
        # Clean string for logging/printing safely in CP1252 terminal
        clean_title = win.title.encode('ascii', errors='replace').decode('ascii')
        print(f"  [DESKTOP] Found matching window: '{clean_title}'. Restoring and activating...")
        
        if win.isMinimized:
            win.restore()
            time.sleep(0.5)
            
        win.activate()
        time.sleep(0.5)
        
        # Win32 Foreground Lock Bypass: Click the title bar to guarantee active focus
        try:
            click_x = max(10, win.left + win.width // 2)
            click_y = max(10, win.top + 15)
            # Ensure coordinates are within display boundaries
            screen_w, screen_h = pyautogui.size()
            if click_x < screen_w and click_y < screen_h:
                print(f"  [DESKTOP] Triggering Win32 focus click at titlebar coordinate ({click_x}, {click_y})...")
                # Move smoothly and click to steal focus
                pyautogui.moveTo(click_x, click_y, duration=0.3)
                pyautogui.click()
                time.sleep(0.3)
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
                dur = act.get("duration", 1.5)
                res = desktop_smooth_click(x, y, duration=dur)
                results.append(f"click: {res}")
                if "ERROR" in res:
                    return f"ERROR at action {idx+1}: {res}"
                    
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

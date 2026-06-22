import os
import sys
import json
import time
import logging
import tempfile
# pyautogui imported lazily inside desktop_interact_with_element to prevent
# module-level hang when desktop_automation is already in sys.modules (pyautogui
# blocks on second init in the same process context).


logger = logging.getLogger(__name__)

# Cache file in scratch folder
SCRATCH_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scratch")
CACHE_FILE = os.path.join(SCRATCH_DIR, "desktop_ui_cache.json")

INTERACTIVE_ROLES = {
    "ButtonControl", "EditControl", "CheckBoxControl", "RadioButtonControl",
    "ComboBoxControl", "ListControl", "ListItemControl", "MenuItemControl",
    "HyperlinkControl", "TabItemControl", "TreeItemControl", "SliderControl",
    "SpinnerControl", "DocumentControl", "WindowControl"
}

def desktop_get_ui_tree(max_depth: int = 8, search_query: str = None) -> str:
    """
    Returns the interactive semantic UI tree of the focused desktop window.
    Saves a cached mapping to scratch/desktop_ui_cache.json so elements can be clicked by index.
    """
    print(f"[TRACE] tools.desktop_ui_tree.desktop_get_ui_tree: enter", file=sys.stderr, flush=True)
    try:
        import uiautomation as auto
    except ImportError:
        print(f"[TRACE] tools.desktop_ui_tree.desktop_get_ui_tree: except ImportError", file=sys.stderr, flush=True)
        return "ERROR: 'uiautomation' library is not available."

    try:
        fg = auto.GetForegroundControl()
        if not fg:
            return "ERROR: No active window detected in foreground."

        # Walk up to find top-level application window (parent just under RootControl)
        root = auto.GetRootControl()
        top = fg
        while top and top.GetParentControl() and top.GetParentControl() != root:
            top = top.GetParentControl()

        if not top:
            top = fg

        window_name = top.Name or "Unknown Window"
        process_id = top.ProcessId
        
        elements = []
        element_idx = 0

        # Walk controls recursively
        for control, depth in auto.WalkControl(top, maxDepth=max_depth):
            if control.IsOffscreen:
                continue
                
            role = control.ControlTypeName
            name = control.Name
            
            if role in INTERACTIVE_ROLES:
                rect = control.BoundingRectangle
                if not rect:
                    continue
                w = rect.right - rect.left
                h = rect.bottom - rect.top
                
                # Filter out zero-size containers
                if w <= 0 or h <= 0:
                    continue
                
                clean_role = role.replace("Control", "")
                safe_name = name if name else ""
                
                # Filter by query if specified
                if search_query:
                    sq = search_query.lower()
                    if sq not in safe_name.lower() and sq not in clean_role.lower() and sq not in (control.AutomationId or "").lower():
                        continue
                
                el_info = {
                    "index": element_idx,
                    "name": safe_name,
                    "role": clean_role,
                    "x": rect.left,
                    "y": rect.top,
                    "w": w,
                    "h": h,
                    "auto_id": control.AutomationId or "",
                    "is_enabled": control.IsEnabled
                }
                elements.append(el_info)
                element_idx += 1

        # Save to cache file
        os.makedirs(SCRATCH_DIR, exist_ok=True)
        try:
            with open(CACHE_FILE, "w", encoding="utf-8") as f:
                json.dump(elements, f, indent=2)
        except Exception as e:
            print(f"[TRACE] tools.desktop_ui_tree.desktop_get_ui_tree: except {str(e)[:80]}", file=sys.stderr, flush=True)
            logger.warning(f"Failed to write UI cache file: {e}")

        # Construct readable string for LLM
        output = [f"Active Window: '{window_name}' (Process ID: {process_id})", "=" * 60]
        for el in elements[:100]:  # Limit output length to prevent context flooding
            output.append(
                f"[{el['index']}] [{el['role']}] '{el['name']}' at ({el['x']}, {el['y']}, w={el['w']}, h={el['h']}) AutoId={el['auto_id']}"
            )
            
        if len(elements) > 100:
            output.append(f"... and {len(elements) - 100} more elements. Refine search using search_query.")
            
        return "\n".join(output)

    except Exception as e:
        print(f"[TRACE] tools.desktop_ui_tree.desktop_get_ui_tree: except {str(e)[:80]}", file=sys.stderr, flush=True)
        logger.error(f"Failed to get active window UI tree: {e}")
        return f"ERROR: {e}"


def desktop_interact_with_element(index: int, action: str = "click", text: str = None) -> str:
    """
    Looks up a cached control by index from scratch/desktop_ui_cache.json
    and performs a mouse click, hover, right_click, or types text into it.
    """
    print(f"[TRACE] tools.desktop_ui_tree.desktop_interact_with_element: enter", file=sys.stderr, flush=True)
    if not os.path.exists(CACHE_FILE):
        return "ERROR: No active UI cache found. Call desktop_get_ui_tree first."

    try:
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            elements = json.load(f)
    except Exception as e:
        print(f"[TRACE] tools.desktop_ui_tree.desktop_interact_with_element: except {str(e)[:80]}", file=sys.stderr, flush=True)
        return f"ERROR: Failed to read UI cache: {e}"

    # Search for element index
    target = None
    for el in elements:
        if el["index"] == index:
            target = el
            break

    if not target:
        return f"ERROR: Element index {index} not found in cache. Re-run desktop_get_ui_tree."

    x_center = target["x"] + target["w"] // 2
    y_center = target["y"] + target["h"] // 2

    # ── Virtual input first (Phase 24): act through UIA patterns without
    #    moving the physical mouse. hover/right_click have no UIA equivalent
    #    and always use the physical path. On failure we fall through to the
    #    original pyautogui block, prefixed so the agent learns which apps
    #    need physical/vision interaction.
    action = action.lower()
    virtual_note = ""
    if action == "click" or (action == "type" and text):
        try:
            from tools.virtual_input import virtual_interact, virtual_input_enabled
            from tools.agent_view import AgentViewSession
            if virtual_input_enabled():
                vs = AgentViewSession(f"element_{index}")
                ok, vmsg, need_physical = virtual_interact(target, action, text, vs)
                vs.add_note(f"element {index} {action}: {vmsg}")
                vs.save()
                if ok:
                    return (f"[virtual] Successfully performed '{action}' on element {index} "
                            f"({target['role']} '{target['name']}') -> {vmsg}")
                virtual_note = f"[physical-fallback: {vmsg[:120]}] "
        except Exception as e:
            print(f"[TRACE] tools.desktop_ui_tree.desktop_interact_with_element: except {str(e)[:80]}", file=sys.stderr, flush=True)
            virtual_note = f"[physical-fallback: virtual input error {e}] "

    try:
        from tools.desktop_automation import desktop_smooth_click, desktop_type_text, desktop_press_keys, _get_pyautogui
        pyautogui = _get_pyautogui()
        if not pyautogui:
            return "ERROR: pyautogui not available"

        # Bring focus back or verify bounds
        screen_w, screen_h = pyautogui.size()
        if not (0 <= x_center < screen_w and 0 <= y_center < screen_h):
            return f"ERROR: Element coordinates ({x_center}, {y_center}) are offscreen."

        if action == "click":
            res = desktop_smooth_click(x_center, y_center, duration=0.8)
            return f"{virtual_note}Successfully clicked element {index} ({target['role']} '{target['name']}') -> {res}"

        elif action == "hover":
            pyautogui.moveTo(x_center, y_center, duration=0.8, tween=pyautogui.easeInOutQuad)
            return f"Successfully hovered over element {index}"

        elif action == "right_click":
            pyautogui.moveTo(x_center, y_center, duration=0.8, tween=pyautogui.easeInOutQuad)
            pyautogui.rightClick()
            return f"Successfully right-clicked element {index}"

        elif action == "type":
            if not text:
                return "ERROR: Text parameter is required for 'type' action."
            # Click first to focus, then type
            desktop_smooth_click(x_center, y_center, duration=0.5)
            time.sleep(0.2)
            # Clear text using Ctrl+A and Backspace if it's an Edit control
            if target["role"] == "Edit":
                pyautogui.hotkey("ctrl", "a")
                time.sleep(0.1)
                pyautogui.press("backspace")
                time.sleep(0.1)
            res = desktop_type_text(text)
            return f"{virtual_note}Successfully typed into element {index} -> {res}"
            
        else:
            return f"ERROR: Unknown action type '{action}'."
            
    except Exception as e:
        print(f"[TRACE] tools.desktop_ui_tree.desktop_interact_with_element: except {str(e)[:80]}", file=sys.stderr, flush=True)
        logger.error(f"Failed to interact with element {index}: {e}")
        return f"ERROR: {e}"

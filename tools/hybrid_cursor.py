# tools/hybrid_cursor.py
"""
Hybrid 3-Layer Cursor Location System (Phase 22c)

Provides hybrid_locate_click(target, window_hint, verify_text, max_retries)
which attempts to find and click a UI element using three layers in order:

  Layer 1 — Graph        : Win32 window stack confirms window exists + focuses it.
                           Returns the window bounds node for Layer 2b.
  Layer 2b — Mouse Braille: Auto.ControlFromPoint(x, y) probes grid points INSIDE
                           the target window's bounds — like a finger sliding along
                           braille. Never touches taskbar/other-window coordinates.
  Layer 3 — OCR           : mss screenshot + pytesseract text bounding-box fallback.

Each layer is tried in order; on the first success the function optionally verifies
the outcome using screen_imprint change detection + OCR text presence check, and
retries the full layer sequence if verification fails.

Changes from Phase 22b:
- Layer 2 (UIAutomation WalkControl) REPLACED by Mouse Braille (ControlFromPoint)
  → eliminates the cross-window bleeding bug (taskbar SearchButton at y=1008)
- _verify_outcome() added: imprint delta check + optional expected-text OCR scan
- _check_text_on_screen() added: OCR check without clicking
- hybrid_locate_click gains verify_text + max_retries params
- _layer1_graph_focus now returns 3-tuple (ok, msg, window_node) for bounds
"""

import os
import json
import logging
import sys
import time

logger = logging.getLogger(__name__)

# Cache written by desktop_get_ui_tree (kept for reference; Layer 2b no longer uses it)
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_CACHE_FILE = os.path.join(_PROJECT_ROOT, "scratch", "desktop_ui_cache.json")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _setup_tesseract():
    """
    Configure the Tesseract binary path on Windows, mirroring jarvis-cli.py
    health-check logic.  Returns the pytesseract module, or None if unavailable.
    """
    try:
        import pytesseract
        if sys.platform == "win32":
            tess_path = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
            if os.path.exists(tess_path):
                # Handle both module layouts across pytesseract versions
                if hasattr(pytesseract, "pytesseract"):
                    pytesseract.pytesseract.tesseract_cmd = tess_path
                else:
                    pytesseract.tesseract_cmd = tess_path
        return pytesseract
    except ImportError:
        return None


# ---------------------------------------------------------------------------
# Layer 1 — Graph (Win32 window stack)
# ---------------------------------------------------------------------------

def _layer1_graph_focus(window_hint: str, view_session=None) -> tuple:
    """
    Verify the target window exists in the Win32 stack and bring it to the
    foreground.

    Returns:
        (success: bool, message: str, window_node: dict | None)
        success=True only when the correct window is confirmed as active.
        window_node contains {title, x, y, w, h, depth} for use by Layer 2b.
    """
    from tools.windows import get_3d_window_graph
    from tools.desktop_automation import desktop_focus_window, desktop_get_active_window

    try:
        graph = get_3d_window_graph()
        if view_session is not None:
            view_session.add_window_graph(graph)
        nodes = graph.get("nodes", [])
        hint_lower = window_hint.lower()

        matching = [n for n in nodes if hint_lower in n.get("title", "").lower()]
        if not matching:
            all_titles = [n.get("title", "") for n in nodes[:6]]
            return False, f"'{window_hint}' not found in window graph. Visible: {all_titles}", None

        window_node = matching[0]  # best match (first = topmost)

        # Bring the window to the foreground
        focus_result = desktop_focus_window(window_hint)
        if "ERROR" in focus_result:
            return False, f"desktop_focus_window failed: {focus_result}", None

        # Verify focus actually landed on the right window
        active = desktop_get_active_window()
        if hint_lower in active.lower():
            return True, active, window_node
        else:
            return False, f"Focus attempted but active window is: {active}", None

    except Exception as exc:
        logger.error("[HybridCursor] Layer 1 exception: %s", exc)
        return False, f"Layer 1 exception: {exc}", None


# ---------------------------------------------------------------------------
# Layer 2b — Mouse Braille (ControlFromPoint grid scan)
# ---------------------------------------------------------------------------

def _layer2_mouse_braille(target: str, window_node: dict, view_session=None) -> tuple:
    """
    Scan a grid of points INSIDE the target window's pixel bounds using
    auto.ControlFromPoint(x, y) — the mouse cursor acts as a braille-reading
    finger sliding across the surface of the window.

    Key advantage over UIAutomation tree walk:
      - Probe coordinates are clamped to [wx..wx+ww, wy..wy+wh]
      - The Windows taskbar lives at y≈1008 — unreachable when probing inside
        a normal application window rectangle
      - ControlFromPoint is a single Win32 COM call (~1ms) vs full tree
        traversal (2-5s for max_depth=8)

    Scan strategy (two passes):
      Pass 1 — coarse (60px step), top 40% of window height
               Most toolbars/navbars/search bars sit in the top 300-400px
      Pass 2 — fine   (25px step), full window height
               Only runs if Pass 1 misses

    On match: the cursor is already near the element → smooth_click immediately
    without a separate move step.

    Returns:
        (success: bool, message: str)
    """
    try:
        import uiautomation as auto
    except ImportError:
        return False, "uiautomation not installed — run: pip install uiautomation"

    from tools.desktop_automation import desktop_smooth_click

    wx  = window_node.get("x", 0)
    wy  = window_node.get("y", 0)
    ww  = window_node.get("w", 1920)
    wh  = window_node.get("h", 1080)
    target_lower = target.lower()

    # Skip titlebar (~35px), keep 5px margin from edges
    y_start = wy + 35
    x_start = wx + 5
    x_end   = wx + ww - 5

    def probe_grid(step: int, y_end: int) -> tuple:
        for py in range(y_start, y_end, step):
            for px in range(x_start, x_end, step):
                try:
                    ctrl = auto.ControlFromPoint(px, py)
                    if ctrl is None:
                        continue
                    ctrl_name = (ctrl.Name or "").strip()
                    if not ctrl_name:
                        if view_session is not None:
                            view_session.add_probe(px, py, hit=False)
                        continue
                    if target_lower in ctrl_name.lower():
                        rect = ctrl.BoundingRectangle
                        cx = rect.left + rect.width() // 2
                        cy = rect.top + rect.height() // 2
                        if view_session is not None:
                            view_session.add_probe(px, py, hit=True)
                            view_session.add_match_box(
                                rect.left, rect.top, rect.width(), rect.height(),
                                ctrl_name)

                        # Virtual input first: invoke the control through UIA
                        # patterns without moving the physical mouse.
                        from tools.virtual_input import (
                            virtual_input_enabled, select_strategies, execute_strategy)
                        if virtual_input_enabled():
                            from tools import agent_cursor
                            agent_cursor.move_to(cx, cy)
                            agent_cursor.pulse()
                            role = ctrl.ControlTypeName.replace("Control", "")
                            for strategy in select_strategies(role, "click"):
                                if strategy == "physical":
                                    break
                                v_ok, v_msg = execute_strategy(ctrl, strategy)
                                if v_ok:
                                    return True, (
                                        f"mouse-braille: '{ctrl_name}' [{ctrl.ControlTypeName}] "
                                        f"at ({cx},{cy}) probe=({px},{py}) -> {v_msg} (virtual)"
                                    )

                        click_result = desktop_smooth_click(cx, cy, duration=0.5, window_bounds=window_node)
                        return True, (
                            f"mouse-braille: '{ctrl_name}' [{ctrl.ControlTypeName}] "
                            f"at ({cx},{cy}) probe=({px},{py}) -> {click_result} (physical)"
                        )
                    if view_session is not None:
                        view_session.add_probe(px, py, hit=False)
                except Exception:
                    continue
        return False, None

    # Pass 1: coarse grid, top 40% of window (fast path for toolbars/navbars)
    y_top40 = wy + int(wh * 0.4)
    ok, msg = probe_grid(step=60, y_end=y_top40)
    if ok:
        return True, msg

    # Pass 2: fine grid, full window height
    ok, msg = probe_grid(step=25, y_end=wy + wh - 5)
    if ok:
        return True, msg

    return False, f"mouse-braille: '{target}' not found in {ww}x{wh} window bounds"


# ---------------------------------------------------------------------------
# Layer 3 — Screenshot OCR fallback
# ---------------------------------------------------------------------------

def _layer3_ocr(target: str, view_session=None, window_bounds=None) -> tuple:
    """
    Capture the current screen with mss and use pytesseract to locate *target*
    text by bounding box, then smooth-click the center.

    Single-word targets: exact match (conf > 50), then partial (conf > 30).
    Multi-word targets:  adjacent tokens in same block_num + line_num,
                         min conf > 30, click center of combined bounding box.

    Returns:
        (success: bool, message: str)
    """
    pytesseract = _setup_tesseract()
    if pytesseract is None:
        return False, "pytesseract not installed — run: pip install pytesseract"

    try:
        import mss
        from PIL import Image
        from tools.desktop_automation import desktop_smooth_click
        from tools.agent_cursor import cursor_hidden

        # Capture the primary monitor directly via mss (overlay ring hidden)
        with cursor_hidden():
            with mss.mss() as sct:
                raw = sct.grab(sct.monitors[1])
                img = Image.frombytes(
                    "RGB", (raw.width, raw.height), raw.bgra, "raw", "BGRX"
                )

        data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)
        if view_session is not None:
            view_session.add_ocr_words(data)
        texts = data["text"]
        target_lower = target.lower()
        target_words = target_lower.split()

        # ---- Single-word search ----------------------------------------
        if len(target_words) == 1:
            # Pass 1: exact match, high confidence
            for i, tok in enumerate(texts):
                if tok.strip().lower() == target_lower and int(data["conf"][i]) > 50:
                    cx = data["left"][i] + data["width"][i] // 2
                    cy = data["top"][i] + data["height"][i] // 2
                    click_result = desktop_smooth_click(cx, cy, duration=0.8, window_bounds=window_bounds)
                    return True, (
                        f"exact match '{tok}' at ({cx},{cy}) "
                        f"conf={data['conf'][i]}% -> {click_result}"
                    )
            # Pass 2: partial/substring match, lower confidence
            for i, tok in enumerate(texts):
                if target_lower in tok.strip().lower() and int(data["conf"][i]) > 30:
                    cx = data["left"][i] + data["width"][i] // 2
                    cy = data["top"][i] + data["height"][i] // 2
                    click_result = desktop_smooth_click(cx, cy, duration=0.8, window_bounds=window_bounds)
                    return True, (
                        f"partial match '{tok}' (contains '{target}') at ({cx},{cy}) "
                        f"conf={data['conf'][i]}% -> {click_result}"
                    )
            return False, f"text '{target}' not found on screen (single-word search)"

        # ---- Multi-word search -----------------------------------------
        n = len(texts)
        nw = len(target_words)
        for i in range(n - nw + 1):
            window = [texts[i + k].strip().lower() for k in range(nw)]
            if window != target_words:
                continue

            # Must be in the same block and same line
            same_block = len(set(data["block_num"][i : i + nw])) == 1
            same_line  = len(set(data["line_num"][i : i + nw])) == 1
            if not (same_block and same_line):
                continue

            confs = [int(data["conf"][i + k]) for k in range(nw)]
            if min(confs) <= 30:
                continue

            lefts   = [data["left"][i + k] for k in range(nw)]
            tops    = [data["top"][i + k] for k in range(nw)]
            rights  = [data["left"][i + k] + data["width"][i + k]  for k in range(nw)]
            bottoms = [data["top"][i + k]  + data["height"][i + k] for k in range(nw)]
            cx = (min(lefts) + max(rights))  // 2
            cy = (min(tops)  + max(bottoms)) // 2
            matched_str = " ".join(texts[i : i + nw])
            click_result = desktop_smooth_click(cx, cy, duration=0.8, window_bounds=window_bounds)
            return True, (
                f"multi-word match '{matched_str}' at ({cx},{cy}) "
                f"min_conf={min(confs)}% -> {click_result}"
            )

        return False, f"text '{target}' not found on screen (multi-word search)"

    except Exception as exc:
        logger.error("[HybridCursor] Layer 3 exception: %s", exc)
        return False, f"Layer 3 exception: {exc}"


# ---------------------------------------------------------------------------
# Verification helpers
# ---------------------------------------------------------------------------

def _check_text_on_screen(text: str, min_conf: int = 40) -> tuple:
    """
    Check whether *text* is visible on screen using pytesseract OCR.
    Returns (found: bool, location_desc: str).
    Does NOT click anything.
    """
    pytesseract = _setup_tesseract()
    if pytesseract is None:
        return False, "pytesseract unavailable"
    try:
        import mss
        from PIL import Image
        from tools.agent_cursor import cursor_hidden
        with cursor_hidden():
            with mss.mss() as sct:
                raw = sct.grab(sct.monitors[1])
                img = Image.frombytes("RGB", (raw.width, raw.height), raw.bgra, "raw", "BGRX")
        data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)
        text_lower = text.lower()
        for i, tok in enumerate(data["text"]):
            if text_lower in (tok or "").strip().lower() and int(data["conf"][i]) >= min_conf:
                cx = data["left"][i] + data["width"][i] // 2
                cy = data["top"][i] + data["height"][i] // 2
                return True, f"found '{tok}' at ({cx},{cy}) conf={data['conf'][i]}"
        return False, f"'{text}' not visible on screen"
    except Exception as exc:
        return False, f"OCR check error: {exc}"


def _verify_outcome(
    expected_text: str = None,
    pre_action_imprint: dict = None,
    timeout: float = 3.0
) -> tuple:
    """
    Verify an action produced a visible change on screen.

    Step 1 (fast, ~100ms/frame): Poll ScreenImprintGraph until density matrix
    changes vs *pre_action_imprint* baseline.  Max wait = min(timeout, 3.0)s.

    Step 2 (OCR, ~1s): If expected_text given, run _check_text_on_screen().

    Args:
        expected_text:     Text to look for on screen after the action.
        pre_action_imprint: The 'imprint' sub-dict captured BEFORE the action.
                           If None, captures a baseline now and polls for further
                           changes (less reliable — pass it when possible).
        timeout:           Max seconds to wait for a screen change.

    Returns:
        (success: bool, message: str)
    """
    from core.system.screen_imprint import ScreenImprintGraph

    imprinter = ScreenImprintGraph()

    if pre_action_imprint is not None:
        # Use caller-supplied baseline — detects changes that happened during action
        imprinter.last_imprint = pre_action_imprint
    else:
        # Seed now; only catches changes AFTER this point
        imprinter.imprint()

    # Hide the agent-cursor ring while polling — its pixels would register as
    # a density delta and produce false "screen changed" results.
    from tools import agent_cursor
    agent_cursor.hide()
    try:
        start = time.time()
        changed = False
        top_region = {}
        while (time.time() - start) < min(timeout, 3.0):
            result = imprinter.imprint()
            if result["changes"]["changed"]:
                changed = True
                regions = result["changes"].get("regions", [])
                top_region = regions[0] if regions else {}
                break
            time.sleep(0.1)
    finally:
        agent_cursor.show()

    if not changed:
        return False, "Screen did not change after action"

    if expected_text:
        ok, loc = _check_text_on_screen(expected_text)
        if not ok:
            return False, f"Screen changed but '{expected_text}' not visible ({loc})"
        return True, f"Screen changed and '{expected_text}' found: {loc}"

    return True, f"Screen changed — top region: {top_region}"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def hybrid_locate_click(
    target: str,
    window_hint: str = None,
    verify_text: str = None,
    max_retries: int = 2,
) -> str:
    """
    Locate a UI element and click it using a hybrid 3-layer approach.

    Layer 1  (Graph):        Verify window exists in Win32 stack, bring to front.
                             Returns window bounds for Layer 2b.
    Layer 2b (Mouse Braille): ControlFromPoint grid scan INSIDE window bounds —
                             cursor slides like a finger reading braille. Cannot
                             accidentally probe the taskbar or other windows.
    Layer 3  (OCR):          mss screenshot + pytesseract text-location fallback.

    If Layer 1 focus fails, Layer 2b is skipped (no valid bounds) and execution
    jumps directly to Layer 3.

    If *verify_text* is provided, after each successful click the function:
      1. Checks whether the screen visually changed (imprint delta).
      2. Checks whether *verify_text* is visible via OCR.
    If verification fails, the full layer sequence is retried up to *max_retries*
    times before returning FAILED.

    Args:
        target:       Text label of the UI element to click
                      (e.g. 'Search', 'Community', 'Note taking app').
        window_hint:  Partial title of the window to focus first
                      (e.g. 'Figma', 'Spotify').  Optional but strongly
                      recommended to avoid clicking the wrong window.
        verify_text:  Text expected to appear on screen after clicking
                      (e.g. 'Search results' or 'scheduling app').
                      If provided, the function retries if the text isn't found.
        max_retries:  How many retry attempts to make when verification fails.
                      Default 2.

    Returns:
        A human-readable trace string showing which layers ran, what each
        found, verification results, and the final success/failure status.
    """
    if not target or not target.strip():
        return "ERROR: hybrid_locate_click requires a non-empty 'target' parameter"

    target = target.strip()
    overall_trace = []

    from tools.agent_view import AgentViewSession

    for attempt in range(max_retries + 1):
        attempt_label = f"[Attempt {attempt + 1}/{max_retries + 1}]"
        trace = []
        view_session = AgentViewSession(f"hybrid_{target[:20]}")

        # ---------------------------------------------------------------- #
        # Pre-click baseline snapshot (for verify_outcome)                  #
        # ---------------------------------------------------------------- #
        pre_click_imprint = None
        if verify_text:
            try:
                from core.system.screen_imprint import ScreenImprintGraph
                _snap = ScreenImprintGraph()
                pre_click_imprint = _snap.imprint()["imprint"]
            except Exception as _e:
                logger.warning("[HybridCursor] Pre-click imprint failed: %s", _e)

        # ---------------------------------------------------------------- #
        # Layer 1 — Graph: confirm window exists and focus it               #
        # ---------------------------------------------------------------- #
        window_node = None
        if window_hint:
            l1_ok, l1_msg, window_node = _layer1_graph_focus(window_hint, view_session)
            label = "OK" if l1_ok else "FAILED"
            trace.append(f"Layer 1 (Graph): {label} — {l1_msg}")

            if not l1_ok:
                # Focus failed — jump straight to OCR
                logger.warning("[HybridCursor] Layer 1 failed. Jumping to Layer 3.")
                l3_ok, l3_msg = _layer3_ocr(target, view_session, window_bounds=window_node)
                trace.append("Layer 2b (MouseBraille): SKIPPED — Layer 1 focus failed")
                trace.append(f"Layer 3 (OCR): {'OK' if l3_ok else 'FAILED'} — {l3_msg}")
                click_ok = l3_ok
            else:
                # -------------------------------------------------------- #
                # Layer 2b — Mouse Braille: ControlFromPoint grid scan      #
                # -------------------------------------------------------- #
                l2_ok, l2_msg = _layer2_mouse_braille(target, window_node, view_session)
                trace.append(f"Layer 2b (MouseBraille): {'OK' if l2_ok else 'FAILED'} — {l2_msg}")

                if l2_ok:
                    click_ok = True
                else:
                    # ---------------------------------------------------- #
                    # Layer 3 — OCR fallback                                 #
                    # ---------------------------------------------------- #
                    logger.warning("[HybridCursor] Layer 2b failed. Falling back to Layer 3.")
                    l3_ok, l3_msg = _layer3_ocr(target, view_session, window_bounds=window_node)
                    trace.append(f"Layer 3 (OCR): {'OK' if l3_ok else 'FAILED'} — {l3_msg}")
                    click_ok = l3_ok
        else:
            trace.append("Layer 1 (Graph): SKIPPED — no window_hint provided")
            trace.append("Layer 2b (MouseBraille): SKIPPED — no window bounds")
            # Jump straight to OCR
            l3_ok, l3_msg = _layer3_ocr(target, view_session, window_bounds=window_node)
            trace.append(f"Layer 3 (OCR): {'OK' if l3_ok else 'FAILED'} — {l3_msg}")
            click_ok = l3_ok

        # ---------------------------------------------------------------- #
        # Verification                                                       #
        # ---------------------------------------------------------------- #
        if click_ok and verify_text:
            v_ok, v_msg = _verify_outcome(
                expected_text=verify_text,
                pre_action_imprint=pre_click_imprint,
                timeout=4.0,
            )
            trace.append(f"Verify ('{verify_text}'): {'OK' if v_ok else 'FAILED'} — {v_msg}")

            overall_trace.append(f"{attempt_label}\n  " + "\n  ".join(trace))
            view_session.add_note("\n".join(trace))
            view_session.save()

            if v_ok:
                return f"[HybridCursor] SUCCESS\n" + "\n".join(overall_trace)

            # Verification failed — retry if attempts remain
            if attempt < max_retries:
                logger.warning(
                    "[HybridCursor] Verify failed (%s). Retrying in 0.5s…", v_msg
                )
                time.sleep(0.5)
                continue
            else:
                return f"[HybridCursor] FAILED (verification exhausted after {max_retries + 1} attempts)\n" + "\n".join(overall_trace)

        else:
            # No verify requested, or click itself failed
            overall_trace.append(f"{attempt_label}\n  " + "\n  ".join(trace))
            view_session.add_note("\n".join(trace))
            view_session.save()
            status = "SUCCESS" if click_ok else "FAILED"
            return f"[HybridCursor] {status}\n" + "\n".join(overall_trace)

    # Should not reach here
    return f"[HybridCursor] FAILED (max retries reached)\n" + "\n".join(overall_trace)

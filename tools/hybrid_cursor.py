# tools/hybrid_cursor.py
"""
Hybrid 3-Layer Cursor Location System (Phase 22b)

Provides hybrid_locate_click(target, window_hint) which attempts to find
and click a UI element using three layers in order:

  Layer 1 — Graph    : Win32 window stack confirms window exists + focuses it
  Layer 2 — Braille  : UIAutomation accessibility tree lookup (uiautomation)
  Layer 3 — OCR      : mss screenshot + pytesseract text bounding-box fallback

Each layer is tried in order; on the first success the function returns.
On Layer 1 focus failure the system skips directly to Layer 3 (no point
querying the UIAutomation tree on the wrong window).
"""

import os
import json
import logging
import sys

logger = logging.getLogger(__name__)

# Cache written by desktop_get_ui_tree — same path pattern as desktop_ui_tree.py
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

def _layer1_graph_focus(window_hint: str) -> tuple:
    """
    Verify the target window exists in the Win32 stack and bring it to the
    foreground.

    Returns:
        (success: bool, message: str)
        success=True only when the correct window is confirmed as active.
    """
    from tools.windows import get_3d_window_graph
    from tools.desktop_automation import desktop_focus_window, desktop_get_active_window

    try:
        graph = get_3d_window_graph()
        nodes = graph.get("nodes", [])
        hint_lower = window_hint.lower()

        matching = [n for n in nodes if hint_lower in n.get("title", "").lower()]
        if not matching:
            all_titles = [n.get("title", "") for n in nodes[:6]]
            return False, f"'{window_hint}' not found in window graph. Visible: {all_titles}"

        # Bring the window to the foreground
        focus_result = desktop_focus_window(window_hint)
        if "ERROR" in focus_result:
            return False, f"desktop_focus_window failed: {focus_result}"

        # Verify focus actually landed on the right window
        # desktop_get_active_window returns: "Active Window: 'title'"
        active = desktop_get_active_window()
        if hint_lower in active.lower():
            return True, active
        else:
            return False, f"Focus attempted but active window is: {active}"

    except Exception as exc:
        logger.error("[HybridCursor] Layer 1 exception: %s", exc)
        return False, f"Layer 1 exception: {exc}"


# ---------------------------------------------------------------------------
# Layer 2 — Braille (UIAutomation accessibility tree)
# ---------------------------------------------------------------------------

def _layer2_braille(target: str) -> tuple:
    """
    Query the UIAutomation tree of the currently-focused window (already
    confirmed correct by Layer 1) and click the element matching *target*.

    Returns:
        (success: bool, message: str)
    """
    from tools.desktop_ui_tree import desktop_get_ui_tree, desktop_interact_with_element

    try:
        # Re-query the tree filtered to target to refresh the cache
        tree_result = desktop_get_ui_tree(max_depth=8, search_query=target)

        if tree_result.startswith("ERROR"):
            return False, f"UIAutomation error: {tree_result}"

        if not os.path.exists(_CACHE_FILE):
            return False, "Cache file not written after ui tree query"

        with open(_CACHE_FILE, "r", encoding="utf-8") as f:
            elements = json.load(f)

        if not elements:
            return False, f"No elements matching '{target}' in accessibility tree"

        # Prefer exact name match, then partial match
        target_lower = target.lower()
        exact = next(
            (e for e in elements if e.get("name", "").lower() == target_lower), None
        )
        partial = next(
            (e for e in elements if target_lower in e.get("name", "").lower()), None
        )
        chosen = exact or partial

        if not chosen:
            return False, (
                f"No element named '{target}' among {len(elements)} cached element(s). "
                f"Names: {[e.get('name','') for e in elements[:5]]}"
            )

        click_result = desktop_interact_with_element(chosen["index"], action="click")
        if "ERROR" in click_result:
            return False, f"Click on element {chosen['index']} failed: {click_result}"

        return True, (
            f"clicked [{chosen.get('role','')}] '{chosen.get('name','')}' "
            f"at ({chosen.get('x')}, {chosen.get('y')}) index={chosen['index']}"
        )

    except Exception as exc:
        logger.error("[HybridCursor] Layer 2 exception: %s", exc)
        return False, f"Layer 2 exception: {exc}"


# ---------------------------------------------------------------------------
# Layer 3 — Screenshot OCR fallback
# ---------------------------------------------------------------------------

def _layer3_ocr(target: str) -> tuple:
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

        # Capture the primary monitor directly via mss
        # (avoids the /workspace Docker path used by desktop_screenshot())
        with mss.mss() as sct:
            raw = sct.grab(sct.monitors[1])
            img = Image.frombytes(
                "RGB", (raw.width, raw.height), raw.bgra, "raw", "BGRX"
            )

        data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)
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
                    click_result = desktop_smooth_click(cx, cy, duration=0.8)
                    return True, (
                        f"exact match '{tok}' at ({cx},{cy}) "
                        f"conf={data['conf'][i]}% -> {click_result}"
                    )
            # Pass 2: partial/substring match, lower confidence
            for i, tok in enumerate(texts):
                if target_lower in tok.strip().lower() and int(data["conf"][i]) > 30:
                    cx = data["left"][i] + data["width"][i] // 2
                    cy = data["top"][i] + data["height"][i] // 2
                    click_result = desktop_smooth_click(cx, cy, duration=0.8)
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
            click_result = desktop_smooth_click(cx, cy, duration=0.8)
            return True, (
                f"multi-word match '{matched_str}' at ({cx},{cy}) "
                f"min_conf={min(confs)}% -> {click_result}"
            )

        return False, f"text '{target}' not found on screen (multi-word search)"

    except Exception as exc:
        logger.error("[HybridCursor] Layer 3 exception: %s", exc)
        return False, f"Layer 3 exception: {exc}"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def hybrid_locate_click(target: str, window_hint: str = None) -> str:
    """
    Locate a UI element and click it using a 3-layer hybrid approach.

    Layer 1 (Graph):   Verify window exists in Win32 stack, bring it to front.
    Layer 2 (Braille): UIAutomation accessibility tree lookup on focused window.
    Layer 3 (OCR):     mss screenshot + pytesseract text-location fallback.

    If Layer 1 (focus) fails, Layer 2 is skipped entirely and execution jumps
    directly to Layer 3, because querying UIAutomation on the wrong window
    would return meaningless results and cause the agent to loop.

    Args:
        target:      Text label of the UI element to click
                     (e.g. 'Search', 'Community', 'Note taking app').
        window_hint: Partial title of the window to focus first
                     (e.g. 'Figma', 'Spotify').  Optional but strongly
                     recommended to avoid clicking the wrong window.

    Returns:
        A human-readable trace string showing which layers ran, what each
        found, and the final success/failure status — e.g.:

            [HybridCursor] SUCCESS
            Layer 1 (Graph): OK — Successfully focused window: 'Community - Figma'
            Layer 2 (Braille): OK — clicked [Edit] 'Search' at (450, 90) index=3
    """
    if not target or not target.strip():
        return "ERROR: hybrid_locate_click requires a non-empty 'target' parameter"

    target = target.strip()
    trace = []

    # ------------------------------------------------------------------ #
    # Layer 1 — Graph: confirm window exists and focus it                  #
    # ------------------------------------------------------------------ #
    if window_hint:
        l1_ok, l1_msg = _layer1_graph_focus(window_hint)
        label = "OK" if l1_ok else "FAILED"
        trace.append(f"Layer 1 (Graph): {label} — {l1_msg}")

        if not l1_ok:
            # Focus failed — UIAutomation would query the wrong window.
            # Skip Layer 2 and go straight to the screenshot fallback.
            logger.warning("[HybridCursor] Layer 1 failed (%s). Jumping to Layer 3.", l1_msg)
            l3_ok, l3_msg = _layer3_ocr(target)
            trace.append(f"Layer 2 (Braille): SKIPPED — Layer 1 focus failed")
            trace.append(f"Layer 3 (OCR): {'OK' if l3_ok else 'FAILED'} — {l3_msg}")
            status = "SUCCESS" if l3_ok else "FAILED"
            return f"[HybridCursor] {status}\n" + "\n".join(trace)
    else:
        trace.append("Layer 1 (Graph): SKIPPED — no window_hint provided")

    # ------------------------------------------------------------------ #
    # Layer 2 — Braille: UIAutomation tree on the now-focused window       #
    # ------------------------------------------------------------------ #
    l2_ok, l2_msg = _layer2_braille(target)
    trace.append(f"Layer 2 (Braille): {'OK' if l2_ok else 'FAILED'} — {l2_msg}")
    if l2_ok:
        return f"[HybridCursor] SUCCESS\n" + "\n".join(trace)

    # ------------------------------------------------------------------ #
    # Layer 3 — OCR: screenshot + pytesseract text detection               #
    # ------------------------------------------------------------------ #
    logger.warning("[HybridCursor] Layer 2 failed (%s). Falling back to Layer 3.", l2_msg)
    l3_ok, l3_msg = _layer3_ocr(target)
    trace.append(f"Layer 3 (OCR): {'OK' if l3_ok else 'FAILED'} — {l3_msg}")
    status = "SUCCESS" if l3_ok else "FAILED"
    return f"[HybridCursor] {status}\n" + "\n".join(trace)

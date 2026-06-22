"""
verify_location (Phase 39) — scroll-assisted verification that you're "at the right place".

Implements the user's verification step: after acting, scroll up and down while OCR-reading the
screen to confirm the expected content/context is actually present. Returns a structured result
the agent reasons over instead of assuming the action landed correctly.

Safe/no-op without a display (returns found=False with a note); never raises.
"""
import sys

import os
import logging

logger = logging.getLogger(__name__)


def _read() -> str:
    """Short OCR/clipboard read of the current screen ('' on failure)."""
    print(f"[TRACE] tools.verify_location._read: enter", file=sys.stderr, flush=True)
    try:
        from tools.clipboard_reader import read_screen_text
        txt = read_screen_text("all")
        if txt and not txt.startswith("[clipboard]"):
            return txt
    except Exception as e:
        print(f"[TRACE] tools.verify_location._read: except {str(e)[:80]}", file=sys.stderr, flush=True)
        logger.debug(f"[verify_location] read failed: {e}")
    return ""


def verify_location(expected_text: str, scroll_amount: int = 400) -> dict:
    """Confirm `expected_text` is visible at/near the current location by scrolling up then down.

    Returns {"found": bool, "where": "current"|"above"|"below"|"none", "snippet": str}.
    """
    print(f"[TRACE] tools.verify_location.verify_location: enter", file=sys.stderr, flush=True)
    expected = (expected_text or "").strip().lower()
    if not expected:
        return {"found": False, "where": "none", "snippet": "", "note": "no expected_text given"}

    if os.environ.get("JARVIS_CI") == "true":
        return {"found": False, "where": "none", "snippet": "", "note": "CI: no display"}

    try:
        from tools.desktop_automation import desktop_scroll
    except Exception as e:
        print(f"[TRACE] tools.verify_location.verify_location: except {str(e)[:80]}", file=sys.stderr, flush=True)
        return {"found": False, "where": "none", "snippet": "", "note": f"scroll unavailable: {e}"}

    # 1. Check where we are now.
    cur = _read()
    if expected in cur.lower():
        return {"found": True, "where": "current", "snippet": cur[:300]}

    # 2. Scroll UP and look (expected content may be above the viewport).
    try:
        desktop_scroll(scroll_amount)  # positive = up
    except Exception:
        print(f"[TRACE] tools.verify_location.verify_location: except Exception", file=sys.stderr, flush=True)
        pass
    up = _read()
    if expected in up.lower():
        return {"found": True, "where": "above", "snippet": up[:300]}

    # 3. Scroll DOWN past the origin and look.
    try:
        desktop_scroll(-2 * scroll_amount)  # negative = down (net: one screen below origin)
    except Exception:
        print(f"[TRACE] tools.verify_location.verify_location: except Exception", file=sys.stderr, flush=True)
        pass
    down = _read()
    if expected in down.lower():
        return {"found": True, "where": "below", "snippet": down[:300]}

    # 4. Restore roughly to the original position.
    try:
        desktop_scroll(scroll_amount)
    except Exception:
        print(f"[TRACE] tools.verify_location.verify_location: except Exception", file=sys.stderr, flush=True)
        pass

    return {"found": False, "where": "none",
            "snippet": (cur or up or down)[:300],
            "note": f"'{expected_text}' not found on screen after scrolling up and down"}

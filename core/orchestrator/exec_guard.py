"""
Execution Guard — harness-enforced verification (Phase 29).

Implements the UI-TARS-style "observe-after-act" + "finished requires verification"
discipline so the agent physically cannot report success it hasn't verified:
  - is_consequential(tool): did this tool change the world (click/type/open/etc.)?
  - observe_change(baseline): fresh screen observation after an action.
  - should_challenge(final_text, pending_unverified): block an unverified "done".

Pure logic is unit-testable; screen functions degrade to no-ops without a display.
"""

import re
import logging

logger = logging.getLogger(__name__)

# Tools that change the world — their effects must be observed/verified.
CONSEQUENTIAL_TOOLS = {
    "desktop_smooth_click", "desktop_type_text", "desktop_press_keys",
    "desktop_batch_actions", "visual_click", "smart_fill",
    "hybrid_locate_click", "open_app", "desktop_interact_with_element",
    "visual_servo_click", "browser_click",
}

# Tools that count as verifying the last action.
VERIFY_TOOLS = {"verify_outcome", "screen_ocr", "visual_inspect", "read_screen_text",
                "element_graph", "screen_imprint", "desktop_get_active_window"}

# Success language that, if unverified, should be challenged.
_SUCCESS_RE = re.compile(
    r"\b(done|complete[d]?|success(?:full|fully)?|finished|opened|created|"
    r"saved|sent|installed|launched|ready|all set)\b",
    re.IGNORECASE,
)


def is_consequential(tool_name: str) -> bool:
    return tool_name in CONSEQUENTIAL_TOOLS


def is_verify(tool_name: str) -> bool:
    return tool_name in VERIFY_TOOLS


def should_challenge(final_text: str, pending_unverified: bool) -> bool:
    """True if the model claims success while the last action is unverified."""
    if not pending_unverified:
        return False
    return bool(_SUCCESS_RE.search(final_text or ""))


def capture_baseline():
    """Return a screen-imprint baseline dict, or None if unavailable (no display/CI)."""
    try:
        import os
        if os.environ.get("JARVIS_CI") == "true":
            return None
        from core.system.screen_imprint import ScreenImprintGraph
        g = ScreenImprintGraph()
        result = g.imprint()
        return result.get("imprint")
    except Exception as e:
        logger.warning(f"[exec_guard] baseline capture failed: {e}")
        return None


def observe_change(baseline) -> tuple[bool, str]:
    """Compare the current screen to *baseline*. Returns (changed, observation_str).

    Cheap tier: density delta (changed YES/NO). Content tier: if changed, append a
    short fresh read of what's on screen (clipboard-safe app -> read_screen_text,
    else a screen_ocr head)."""
    try:
        import os
        if os.environ.get("JARVIS_CI") == "true" or baseline is None:
            return False, ""
        from core.system.screen_imprint import ScreenImprintGraph
        g = ScreenImprintGraph()
        g.last_imprint = baseline
        result = g.imprint()
        changed = bool(result.get("changes", {}).get("changed"))
        if not changed:
            return False, "[observe] screen did NOT change since your last action — it may not have worked. Verify or try get_unstuck."

        regions = result.get("changes", {}).get("regions", [])
        delta = regions[0].get("delta") if regions else None
        msg = f"[observe] screen changed since your last action (delta={delta:.0f})." if delta else "[observe] screen changed since your last action."

        # Content tier — a short fresh read so the model sees the actual new state.
        snippet = _quick_read()
        if snippet:
            msg += f" Current screen text (head):\n{snippet}"
        return True, msg
    except Exception as e:
        logger.warning(f"[exec_guard] observe failed: {e}")
        return False, ""


def _quick_read(limit: int = 600) -> str:
    """A short, cheap read of current on-screen text. '' on failure."""
    try:
        from tools.clipboard_reader import read_screen_text
        txt = read_screen_text("all")
        if txt and not txt.startswith("[clipboard]"):
            return txt[:limit]
    except Exception:
        pass
    return ""

"""
Execution Guard — harness-enforced verification (Phase 29).

Implements the UI-TARS-style "observe-after-act" + "finished requires verification"
discipline so the agent physically cannot report success it hasn't verified:
  - is_consequential(tool): did this tool change the world (click/type/open/etc.)?
  - observe_change(baseline): fresh screen observation after an action.
  - should_challenge(final_text, pending_unverified): block an unverified "done".

Pure logic is unit-testable; screen functions degrade to no-ops without a display.
"""
import sys
from core.trace import trace as _jtrace

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
                "element_graph", "screen_imprint", "desktop_get_active_window",
                "verify_location"}

# Success language that, if unverified, should be challenged.
_SUCCESS_RE = re.compile(
    r"\b(done|complete[d]?|success(?:full|fully)?|finished|opened|created|"
    r"saved|sent|installed|launched|ready|all set)\b",
    re.IGNORECASE,
)

# Deferral / hand-back-a-to-do-list language. When the model writes these in a FINAL
# response (no tool calls) it is punting work back to the user instead of doing it.
_DEFERRAL_RE = re.compile(
    r"(recommended?\s+next\s+steps?|next\s+steps?\s*[:\-]|"
    r"you\s+(can|could|should|may want to|might want to|'ll want to|will want to)\b|"
    r"once\s+(the\s+)?(page|you|it|that)\b.*\b(you|we)\b|"
    r"proceed\s+with\b|to\s+continue\b|if\s+you('|\s+wo)?u?ld\s+like|"
    r"i\s+(recommend|suggest)\s+(you|that you)\b|"
    r"the\s+next\s+step\s+(is|would be)\b|"
    r"verify\b.*\bthen\b.*\b(extract|capture|proceed|continue)\b)",
    re.IGNORECASE,
)
MAX_CONTINUES = 5  # cap on autonomy nudges so a stubborn model can't loop forever

# Give-up / premature exit language. When the model admits failure without retrying.
_GIVE_UP_RE = re.compile(
    r"("
    r"i\s+was\s+unable"                                # "I was unable to..."
    r"|i\s+was(n't|\s+not)\s+able"                     # "I wasn't able to..."
    r"|i\s+could(n't|\s+not)"                          # "I couldn't / I could not"
    r"|i\s+can(not|'t)"                                # "I cannot / I can't"
    r"|i\s+am\s+(unable|not\s+able)"                   # "I am unable to..."
    r"|unfortunately"                                   # "Unfortunately, ..."
    r"|i\s+apologize"                                   # "I apologize..."
    r"|i'm\s+sorry.{0,20}(but|unable|can't|couldn't)"  # "I'm sorry but I can't..."
    r"|unable\s+to\s+(complete|finish|accomplish|find|locate|open)"
    r"|failed\s+to|i\s+failed"                         # "I failed to..."
    r"|wasn't\s+able|not\s+able\s+to"                  # "wasn't able to..."
    r"|couldn't\s+(find|locate|click|open|complete|access|reach)"
    r"|it\s+did(n't|\s+not)\s+(work|succeed)"          # "It didn't work"
    r"|did\s+not\s+(work|succeed)"                     # "did not work"
    r"|doesn't\s+seem\s+to\s+work"                    # "doesn't seem to work"
    r"|appears?\s+to\s+(have\s+)?fail"                 # "appears to have failed"
    r"|it\s+(didn't|doesn't|won't|isn't)"              # "It didn't / doesn't / won't"
    r")",
    re.IGNORECASE,
)
MIN_TOOL_TURNS = 3  # model must make at least 3 tool-calling turns before it can give up

# Risky / irreversible action detection (Phase 39 Part 3). These need explicit user yes/no.
_RISKY_TOOLS = {
    "send_email", "send_message", "browser_submit", "submit_form", "make_payment",
    "purchase", "post_tweet", "delete_file", "remove_file",
}
_RISKY_CMD_RE = re.compile(
    r"\b(rm\s+-rf|rm\s+|del\s+|rmdir|remove-item|format\s+|mkfs|"
    r"shutdown|restart-computer|reg\s+delete|drop\s+table|drop\s+database|"
    r"git\s+push\s+--force|git\s+reset\s+--hard|taskkill)\b",
    re.IGNORECASE,
)
_RISKY_ARG_RE = re.compile(
    r"\b(send|submit|purchase|pay|checkout|delete|deactivate|uninstall|"
    r"post\b|publish|transfer|wire|withdraw)\b",
    re.IGNORECASE,
)


def is_consequential(tool_name: str) -> bool:
    return tool_name in CONSEQUENTIAL_TOOLS


def is_verify(tool_name: str) -> bool:
    return tool_name in VERIFY_TOOLS


def should_challenge(final_text: str, pending_unverified: bool) -> bool:
    """True if the model claims success while the last action is unverified."""
    _jtrace(f"[TRACE] core.orchestrator.exec_guard.should_challenge: enter")
    if not pending_unverified:
        return False
    return bool(_SUCCESS_RE.search(final_text or ""))


def is_deferral(final_text: str) -> bool:
    """True if a FINAL response hands a to-do list back to the user instead of doing the work."""
    return bool(_DEFERRAL_RE.search(final_text or ""))


def is_premature_exit(final_text: str, tool_turns: int) -> bool:
    """True if the model is giving up too early — admits failure before MIN_TOOL_TURNS.
    
    Catches patterns like 'I couldn't find the search box', 'Unfortunately I was unable'
    when the model hasn't even made enough tool-calling attempts yet.
    """
    _jtrace(f"[TRACE] core.orchestrator.exec_guard.is_premature_exit: enter")
    if tool_turns >= MIN_TOOL_TURNS:
        return False  # model has tried enough, let it exit
    return bool(_GIVE_UP_RE.search(final_text or ""))


def is_risky(tool_name: str, args) -> tuple[bool, str]:
    """Return (risky, reason) for a tool call that needs explicit user permission.

    Risky = destructive (delete/format/drop/force-push) or outward-facing/irreversible
    (send email, submit form, purchase, post). Pure reads/navigation are never risky."""
    _jtrace(f"[TRACE] core.orchestrator.exec_guard.is_risky: enter")
    name = (tool_name or "").lower()
    if name in _RISKY_TOOLS:
        return True, f"{tool_name} is an irreversible/outward-facing action"

    # Inspect string args (dict or raw string) for risky commands/keywords.
    blob = ""
    if isinstance(args, dict):
        blob = " ".join(str(v) for v in args.values())
    else:
        blob = str(args or "")

    if name in ("run_command", "shell", "desktop_run") or "command" in (args or {} if isinstance(args, dict) else {}):
        if _RISKY_CMD_RE.search(blob):
            return True, "destructive shell command"
    if _RISKY_CMD_RE.search(blob):
        return True, "destructive command pattern"
    if name in ("write_file", "save_file") and _RISKY_ARG_RE.search(blob):
        return True, "overwrites/transfers data"
    return False, ""


def active_window_title() -> str:
    """Best-effort current foreground window title ('' on failure / CI). Used for pre-act
    grounding so the agent confirms it is acting in the right app."""
    try:
        import os
        if os.environ.get("JARVIS_CI") == "true":
            return ""
        from tools.desktop_automation import desktop_get_active_window
        info = desktop_get_active_window()
        return str(info)[:200] if info else ""
    except Exception as e:
        _jtrace(f"[TRACE] core.orchestrator.exec_guard.active_window_title: except {str(e)[:80]}")
        logger.warning(f"[exec_guard] active_window_title failed: {e}")
        return ""


_HEADLESS_MODE = False

def capture_baseline():
    """Return a lightweight screen hash baseline, or None if unavailable (no display/CI).
    
    Uses a fast downscaled grayscale thumbnail CRC instead of the full
    ScreenImprintGraph. Runs in ~5ms.
    """
    _jtrace(f"[TRACE] core.orchestrator.exec_guard.capture_baseline: enter")
    global _HEADLESS_MODE
    try:
        import os
        if os.environ.get("JARVIS_CI") == "true" or _HEADLESS_MODE:
            return None
        import mss
        import hashlib
        with mss.mss() as sct:
            monitor = sct.monitors[1]
            screenshot = sct.grab(monitor)
            # Fast: hash only every 64th pixel byte to save CPU and memory allocation
            pixel_hash = hashlib.md5(screenshot.rgb[::64]).hexdigest()
            return {"hash": pixel_hash, "w": monitor["width"], "h": monitor["height"]}
    except Exception as e:
        _jtrace(f"[TRACE] core.orchestrator.exec_guard.capture_baseline: except {str(e)[:80]}")
        logger.warning(f"[exec_guard] baseline capture failed (disabling future captures): {e}")
        _HEADLESS_MODE = True
        return None


def observe_change(baseline) -> tuple[bool, str]:
    """Compare the current screen hash to *baseline*. Returns (changed, observation_str).

    Fast pixel-hash comparison (~5ms). No clipboard grabbing — the old _quick_read()
    was destructive (Ctrl+A/Ctrl+C on active window). The model can call
    read_screen_text explicitly if it needs on-screen content.
    """
    _jtrace(f"[TRACE] core.orchestrator.exec_guard.observe_change: enter")
    global _HEADLESS_MODE
    try:
        import os
        if os.environ.get("JARVIS_CI") == "true" or _HEADLESS_MODE or baseline is None:
            return False, ""
        import mss
        import hashlib
        with mss.mss() as sct:
            monitor = sct.monitors[1]
            screenshot = sct.grab(monitor)
            current_hash = hashlib.md5(screenshot.rgb[::64]).hexdigest()
        
        changed = current_hash != baseline.get("hash", "")
        if not changed:
            return False, ("[observe] screen did NOT change since your last action — "
                          "it may not have worked. Call verify_outcome or get_unstuck.")
        return True, "[observe] screen changed since your last action. Use read_screen_text or verify_outcome to check the result."
    except Exception as e:
        _jtrace(f"[TRACE] core.orchestrator.exec_guard.observe_change: except {str(e)[:80]}")
        logger.warning(f"[exec_guard] observe failed (disabling future captures): {e}")
        _HEADLESS_MODE = True
        return False, ""

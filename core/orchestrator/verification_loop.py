"""
Verification Loop — confirm an action actually changed the screen (Phase 28a).

Reuses the proven primitives in tools/hybrid_cursor.py (one source of truth):
  - _verify_outcome: density-delta poll + optional OCR text check
  - _check_text_on_screen: pytesseract OCR location check

Exposes a clean dict-returning public API so the model can call verify_outcome as a
tool after consequential actions instead of assuming success. Never raises.
"""
import sys
from core.trace import trace as _jtrace

import logging

logger = logging.getLogger(__name__)


def verify_outcome(expected_text: str | None = None, timeout: float = 3.0) -> dict:
    """Verify the last action produced a visible change.

    Step 1: poll the screen density matrix until it changes (<= timeout).
    Step 2: if expected_text is given, confirm it is visible via OCR.

    Returns {"success": bool, "message": str}.
    """
    try:
        from tools.hybrid_cursor import _verify_outcome
        ok, message = _verify_outcome(expected_text=expected_text, timeout=timeout)
        return {"success": bool(ok), "message": message}
    except Exception as e:
        _jtrace(f"[TRACE] core.orchestrator.verification_loop.verify_outcome: except {str(e)[:80]}")
        logger.warning(f"[verify] verify_outcome failed: {e}")
        return {"success": False, "message": f"verification error: {e}"}


def check_text_on_screen(text: str, min_conf: int = 40) -> dict:
    """Check whether *text* is currently visible on screen via OCR (no click)."""
    try:
        from tools.hybrid_cursor import _check_text_on_screen
        found, location = _check_text_on_screen(text, min_conf=min_conf)
        return {"found": bool(found), "location": location}
    except Exception as e:
        _jtrace(f"[TRACE] core.orchestrator.verification_loop.check_text_on_screen: except {str(e)[:80]}")
        logger.warning(f"[verify] check_text_on_screen failed: {e}")
        return {"found": False, "location": f"error: {e}"}

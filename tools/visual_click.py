# tools/visual_click.py
"""
Visual Click — Vision-Guided Element Clicking (Phase 22e)

Finds a UI element by visual description and clicks it. Works for ANY rendered
surface: HTML/DOM, WebGL canvas, Electron, native apps — ControlFromPoint and
pytesseract are not used.

This is the same technique Claude Computer Use and OpenAI Operator use:
  screenshot → vision model identifies element coordinates → click at those coords

Flow:
  mss screenshot → PIL resize (1280px)
    → Claude Vision: "Find [description] → reply FOUND x y"
    → parse (x, y) from resized image
    → scale to actual screen resolution
    → desktop_smooth_click(actual_x, actual_y)

Reuses _call_anthropic_vision / _call_gemini_vision from tools/visual_inspect.py
to avoid duplicating the API-call logic.
"""

import os
import io
import re
import sys
import base64
import logging

logger = logging.getLogger(__name__)


def visual_click(
    description: str,
    resize_width: int = 1280,
    duration: float = 0.8,
) -> str:
    """
    Find a UI element by visual description and click it using Claude Vision.

    Designed for WebGL/canvas/Electron UIs where ``hybrid_locate_click`` (which
    uses UIAutomation ControlFromPoint) fails because the element is rendered
    inside a pixel canvas rather than the OS accessibility tree.

    Args:
        description: What to find and click, e.g.:
                     "search bar in the Figma Community main area"
                     "Community tab in the Figma left sidebar"
                     "the blue Submit button near the bottom of the form"
        resize_width: Screenshot is resized to this width before sending
                      (default 1280px). Coordinates are scaled back to the
                      full screen resolution automatically.
        duration:     Mouse movement duration for smooth_click (seconds).
                      Default 0.8s gives a natural-looking movement.

    Returns:
        A trace string, e.g.:
          "[VisualClick] SUCCESS
           Vision: FOUND 847 92
           Scaled: (1270, 138) on 1920x1080 screen
           Click: Moved to (1270, 138) and clicked"

        On failure:
          "[VisualClick] FAILED: vision model could not locate '...' ..."
    """
    if not description or not description.strip():
        return "ERROR: visual_click requires a non-empty 'description' parameter"
    description = description.strip()

    # ------------------------------------------------------------------ #
    # 1. Capture screen + get actual resolution for coordinate scaling     #
    # ------------------------------------------------------------------ #
    try:
        import mss
        from PIL import Image

        with mss.mss() as sct:
            mon = sct.monitors[1]
            screen_w = mon["width"]
            screen_h = mon["height"]
            raw = sct.grab(mon)
            img = Image.frombytes("RGB", (raw.width, raw.height), raw.bgra, "raw", "BGRX")
    except Exception as exc:
        return f"[VisualClick] FAILED: screenshot capture error: {exc}"

    # ------------------------------------------------------------------ #
    # 2. Resize proportionally                                             #
    # ------------------------------------------------------------------ #
    try:
        orig_w, orig_h = img.size
        scale = resize_width / orig_w
        new_h = int(orig_h * scale)
        img = img.resize((resize_width, new_h), Image.LANCZOS)
    except Exception as exc:
        return f"[VisualClick] FAILED: resize error: {exc}"

    # ------------------------------------------------------------------ #
    # 3. Encode as base64 PNG                                              #
    # ------------------------------------------------------------------ #
    try:
        buf = io.BytesIO()
        img.save(buf, format="PNG", optimize=True)
        b64_data = base64.b64encode(buf.getvalue()).decode("utf-8")
    except Exception as exc:
        return f"[VisualClick] FAILED: encoding error: {exc}"

    # ------------------------------------------------------------------ #
    # 4. Build strict coordinate-extraction prompt                         #
    # ------------------------------------------------------------------ #
    prompt = (
        f"You are a GUI automation assistant.\n"
        f"Find the UI element described as: \"{description}\"\n\n"
        f"This screenshot is {resize_width}x{new_h} pixels.\n\n"
        f"Reply with EXACTLY one line — nothing else:\n"
        f"  FOUND x y\n"
        f"  NOT FOUND\n\n"
        f"Where x and y are INTEGER pixel coordinates of the CENTER of the element "
        f"in the {resize_width}x{new_h} resized image. "
        f"If multiple matches exist, pick the most prominent one. "
        f"No explanation. Just the single line."
    )

    # ------------------------------------------------------------------ #
    # 5. Call vision API                                                   #
    # ------------------------------------------------------------------ #
    from tools.visual_inspect import _call_nvidia_vision, _call_anthropic_vision, _call_gemini_vision

    vision_response = None

    # Primary: NVIDIA kimi-k2.6
    nvidia_key = os.environ.get("NVIDIA_API_KEY", "").strip()
    if nvidia_key:
        vision_response = _call_nvidia_vision(b64_data, prompt, nvidia_key)
        if vision_response.startswith("ERROR:"):
            logger.warning("[VisualClick] NVIDIA failed: %s. Trying Anthropic.", vision_response)
            vision_response = None

    # Fallback 1: Anthropic Claude Vision
    if vision_response is None:
        anthropic_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
        if anthropic_key:
            vision_response = _call_anthropic_vision(b64_data, prompt, anthropic_key)
            if vision_response.startswith("ERROR:"):
                logger.warning("[VisualClick] Anthropic failed: %s. Trying Gemini.", vision_response)
                vision_response = None

    # Fallback 2: Gemini Vision
    if vision_response is None:
        gemini_key = os.environ.get("GEMINI_API_KEY", "").strip()
        if gemini_key:
            vision_response = _call_gemini_vision(b64_data, prompt, gemini_key)
        else:
            return "[VisualClick] FAILED: No vision API key available (NVIDIA_API_KEY / ANTHROPIC_API_KEY / GEMINI_API_KEY)"

    if vision_response is None or vision_response.startswith("ERROR:"):
        return f"[VisualClick] FAILED: vision API error — {vision_response}"

    # ------------------------------------------------------------------ #
    # 6. Parse coordinates — two-pass robust extraction                   #
    # ------------------------------------------------------------------ #
    parsed_x = parsed_y = None

    # Pass 1: strict "FOUND x y" format
    m = re.search(r'FOUND\s+(\d+)\s+(\d+)', vision_response, re.IGNORECASE)
    if m:
        parsed_x, parsed_y = int(m.group(1)), int(m.group(2))

    # Pass 2: any "(x, y)" or "(x y)" pattern in the response
    if parsed_x is None:
        m = re.search(r'\((\d+)[,\s]+(\d+)\)', vision_response)
        if m:
            parsed_x, parsed_y = int(m.group(1)), int(m.group(2))

    # Pass 3: any "x, y" number pair after a colon or similar
    if parsed_x is None:
        m = re.search(r':\s*(\d+)[,\s]+(\d+)', vision_response)
        if m:
            parsed_x, parsed_y = int(m.group(1)), int(m.group(2))

    if parsed_x is None:
        return (
            f"[VisualClick] FAILED: could not parse coordinates from vision response.\n"
            f"Description: '{description}'\n"
            f"Vision response: {vision_response[:300]}"
        )

    # Check for "NOT FOUND" explicitly
    if re.search(r'NOT\s+FOUND', vision_response, re.IGNORECASE) and parsed_x is None:
        return (
            f"[VisualClick] FAILED: vision model reported NOT FOUND for '{description}'.\n"
            f"Vision response: {vision_response[:300]}"
        )

    # ------------------------------------------------------------------ #
    # 7. Scale from resized-image coords to actual screen coords           #
    # ------------------------------------------------------------------ #
    actual_x = int(parsed_x * screen_w / resize_width)
    actual_y = int(parsed_y * screen_h / new_h)

    # Clamp to screen bounds with a small margin
    actual_x = max(5, min(actual_x, screen_w - 5))
    actual_y = max(5, min(actual_y, screen_h - 5))

    # ------------------------------------------------------------------ #
    # 8. Click                                                             #
    # ------------------------------------------------------------------ #
    try:
        from tools.desktop_automation import desktop_smooth_click
        click_result = desktop_smooth_click(actual_x, actual_y, duration=duration)
    except Exception as exc:
        return (
            f"[VisualClick] FAILED: smooth_click error at ({actual_x},{actual_y}): {exc}\n"
            f"Vision response: {vision_response[:200]}"
        )

    return (
        f"[VisualClick] SUCCESS\n"
        f"Description: '{description}'\n"
        f"Vision response: {vision_response.strip()[:120]}\n"
        f"Parsed image coords: ({parsed_x}, {parsed_y}) in {resize_width}x{new_h}\n"
        f"Scaled screen coords: ({actual_x}, {actual_y}) on {screen_w}x{screen_h}\n"
        f"Click result: {click_result}"
    )

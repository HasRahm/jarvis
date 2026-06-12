# tools/visual_click.py
"""
Visual Click — Vision-Guided Element Clicking (Phase 22e/f)

Finds a UI element by visual description and clicks it. Works for ANY rendered
surface: HTML/DOM, WebGL canvas, Electron, native apps — ControlFromPoint and
pytesseract are not used.

This is the same technique Claude Computer Use and OpenAI Operator use:
  screenshot → vision model identifies element coordinates → click at those coords

Flow (with window_hint):
  mss full screenshot
    → get_3d_window_graph() → crop to target window bounds (wx, wy, ww, wh)
    → resize CROP to 1280px  [smaller image → faster + cheaper API call]
    → kimi-k2.6: "Find [description] → reply FOUND x y"  (coords in cropped image)
    → scale back: actual_x = wx + int(parsed_x * ww / resize_width)
    → desktop_smooth_click(actual_x, actual_y)   [guaranteed inside target window]

Without window_hint: full screen is sent (fallback, same as before).

Reuses _call_nvidia_vision / _call_anthropic_vision / _call_gemini_vision
from tools/visual_inspect.py — no code duplication.
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
    window_hint: str = None,
    resize_width: int = 1024,
    duration: float = 0.4,
) -> str:
    """
    Find a UI element by visual description and click it using kimi-k2.6 Vision.

    Designed for WebGL/canvas/Electron UIs where ``hybrid_locate_click`` (which
    uses UIAutomation ControlFromPoint) fails because the element is rendered
    inside a pixel canvas rather than the OS accessibility tree.

    Args:
        description:  What to find and click, e.g.:
                      "search bar in the Figma Community main area"
                      "Community tab in the Figma left sidebar"
                      "the blue Submit button near the bottom of the form"
        window_hint:  Partial window title (e.g. "Figma", "Chrome"). When
                      provided the screenshot is CROPPED to that window's
                      pixel bounds before being sent to vision — improves
                      accuracy and reduces API cost. Uses get_3d_window_graph
                      to find the window. If the window is not found, falls
                      back to the full-screen image.
        resize_width: Width to resize the image before sending (default 1280).
                      Applied AFTER cropping when window_hint is used.
        duration:     Mouse movement smoothness in seconds (default 0.8s).

    Returns:
        "[VisualClick] SUCCESS / FAILED" trace string with coords at each stage.
    """
    if not description or not description.strip():
        return "ERROR: visual_click requires a non-empty 'description' parameter"
    description = description.strip()

    # ------------------------------------------------------------------ #
    # 1. Capture full screen + get resolution                              #
    # ------------------------------------------------------------------ #
    try:
        import mss
        from PIL import Image
        from tools.agent_cursor import cursor_hidden

        with cursor_hidden():
            with mss.mss() as sct:
                mon = sct.monitors[1]
                screen_w = mon["width"]
                screen_h = mon["height"]
                raw = sct.grab(mon)
                img = Image.frombytes("RGB", (raw.width, raw.height), raw.bgra, "raw", "BGRX")
    except Exception as exc:
        return f"[VisualClick] FAILED: screenshot capture error: {exc}"

    # Agent view session (no-op unless JARVIS_AGENT_VIEW=1)
    from tools.agent_view import AgentViewSession
    view_session = AgentViewSession(f"visual_{description[:20]}")

    # ------------------------------------------------------------------ #
    # 1b. Graph method — crop to target window bounds if window_hint given  #
    # ------------------------------------------------------------------ #
    crop_offset_x = 0  # window origin in screen coords (added back after scaling)
    crop_offset_y = 0
    crop_w = screen_w   # dimensions of the region sent to vision
    crop_h = screen_h
    graph_note = "full screen (no window_hint)"

    if window_hint:
        try:
            from tools.windows import get_3d_window_graph
            graph = get_3d_window_graph()
            view_session.add_window_graph(graph)
            nodes = graph.get("nodes", [])
            hint_lower = window_hint.lower()
            match = next((n for n in nodes if hint_lower in n.get("title", "").lower()), None)

            if match:
                wx  = max(0, match["x"])
                wy  = max(0, match["y"])
                ww  = min(match["w"], screen_w - wx)
                wh  = min(match["h"], screen_h - wy)

                if ww > 50 and wh > 50:   # sanity check — ignore zero-size windows
                    img = img.crop((wx, wy, wx + ww, wy + wh))
                    crop_offset_x = wx
                    crop_offset_y = wy
                    crop_w, crop_h = ww, wh
                    graph_note = f"cropped to '{match['title']}' @ ({wx},{wy}) {ww}x{wh}"
                else:
                    graph_note = f"window '{match['title']}' bounds too small ({ww}x{wh}), using full screen"
            else:
                titles = [n.get("title", "") for n in nodes[:5]]
                graph_note = f"window_hint '{window_hint}' not found in graph {titles}, using full screen"
        except Exception as exc:
            graph_note = f"graph lookup failed ({exc}), using full screen"

    # ------------------------------------------------------------------ #
    # 2. Resize proportionally (applied to cropped region)                 #
    # ------------------------------------------------------------------ #
    try:
        scale = resize_width / crop_w
        new_h = int(crop_h * scale)
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

    # visual_click only needs a single "FOUND x y" line — cap output tokens low
    # so the model stops generating immediately (faster completion).
    VC_MAX_TOKENS = 64

    # Primary: NVIDIA kimi-k2.6
    nvidia_key = os.environ.get("NVIDIA_API_KEY", "").strip()
    if nvidia_key:
        vision_response = _call_nvidia_vision(b64_data, prompt, nvidia_key, max_tokens=VC_MAX_TOKENS)
        if vision_response.startswith("ERROR:"):
            logger.warning("[VisualClick] NVIDIA failed: %s. Trying Anthropic.", vision_response)
            vision_response = None

    # Fallback 1: Anthropic Claude Vision
    if vision_response is None:
        anthropic_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
        if anthropic_key:
            vision_response = _call_anthropic_vision(b64_data, prompt, anthropic_key, max_tokens=VC_MAX_TOKENS)
            if vision_response.startswith("ERROR:"):
                logger.warning("[VisualClick] Anthropic failed: %s. Trying Gemini.", vision_response)
                vision_response = None

    # Fallback 2: Gemini Vision
    if vision_response is None:
        gemini_key = os.environ.get("GEMINI_API_KEY", "").strip()
        if gemini_key:
            vision_response = _call_gemini_vision(b64_data, prompt, gemini_key, max_tokens=VC_MAX_TOKENS)
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
    # 7. Scale from resized-image coords back to actual screen coords      #
    #    Vision coords are in the resized crop → scale to crop dims        #
    #    then add the window's screen offset (crop_offset_x/y)             #
    # ------------------------------------------------------------------ #
    actual_x = crop_offset_x + int(parsed_x * crop_w / resize_width)
    actual_y = crop_offset_y + int(parsed_y * crop_h / new_h)

    # Clamp to screen bounds with a small margin
    actual_x = max(5, min(actual_x, screen_w - 5))
    actual_y = max(5, min(actual_y, screen_h - 5))

    # Record what the model saw and where it pointed, then save (pre-click)
    view_session.add_vision_crop(
        (crop_offset_x, crop_offset_y, crop_w, crop_h),
        (actual_x, actual_y),
        note=vision_response.strip()[:120],
    )
    view_session.add_note(f"visual_click '{description[:60]}' -> screen ({actual_x},{actual_y})")
    view_session.save()

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
        f"Graph: {graph_note}\n"
        f"Vision response: {vision_response.strip()[:120]}\n"
        f"Parsed image coords: ({parsed_x}, {parsed_y}) in {resize_width}x{new_h}\n"
        f"Scaled screen coords: ({actual_x}, {actual_y}) on {screen_w}x{screen_h}\n"
        f"Click result: {click_result}"
    )

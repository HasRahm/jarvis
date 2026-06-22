# tools/visual_inspect.py
"""
Visual Inspect — Give Jarvis Eyes (Phase 22d)

Captures the screen and asks a vision-capable AI model to describe what it sees.
Solves the OCR dead-zone problem: pytesseract only reads HTML/DOM text, making it
blind to WebGL/canvas-rendered UIs (Figma Community, Electron apps, browser SPAs).

Architecture:
  mss screenshot → PIL resize → base64 PNG
    → Claude claude-sonnet-4-6 (Anthropic API)       [primary]
    → gemini-2.0-flash (Google GenAI API)              [fallback]

Usage pattern (in agent tool calls):
    visual_inspect("What Pokémon designs are shown in the Figma Community results?")
    → "I can see 6 design cards in the main grid:
       1. 'Pokémon GO UI Kit' at approximately (180, 320) — green map-style UI
       2. 'Pokemon App Design Kit' at approximately (420, 320) — character selection screen
       ..."
"""

import os
import sys
import io
import base64
import logging

logger = logging.getLogger(__name__)


def visual_inspect(question: str, resize_width: int = 1280) -> str:
    """
    Take a screenshot of the primary monitor and ask a vision AI what it sees.

    Use this when `screen_ocr` returns only sidebar/navigation content and fails to
    read the main content area (WebGL canvas, Electron, browser SPA).

    Sends the screenshot to Claude claude-sonnet-4-6 via Anthropic API (falls back to
    Gemini 2.0 Flash if ANTHROPIC_API_KEY is not set).

    Args:
        question:     Natural-language question about the screen content, e.g.:
                      "What search results are showing in the Figma Community grid?"
                      "Where is the search bar? Give me its (x, y) coordinates."
                      "Did the search for 'pokemon' produce results? List them."
        resize_width: Width to resize before sending to the vision API.
                      Default 1280px. Lower = cheaper/faster; higher = more detail.
                      Height is scaled proportionally.

    Returns:
        Natural-language description from the vision model, including approximate
        pixel coordinates for any UI elements described. On failure returns an
        "ERROR: ..." string (never raises).
    """
    # ------------------------------------------------------------------ #
    # 1. Capture screen via mss (same approach as screen_ocr in dispatcher)
    # ------------------------------------------------------------------ #
    print(f"[TRACE] tools.visual_inspect.visual_inspect: enter", file=sys.stderr, flush=True)
    try:
        import mss
        from PIL import Image
        from tools.agent_cursor import cursor_hidden

        with cursor_hidden():
            with mss.mss() as sct:
                raw = sct.grab(sct.monitors[1])
                img = Image.frombytes("RGB", (raw.width, raw.height), raw.bgra, "raw", "BGRX")
    except Exception as exc:
        print(f"[TRACE] tools.visual_inspect.visual_inspect: except {str(exc)[:80]}", file=sys.stderr, flush=True)
        return f"ERROR: screenshot capture failed: {exc}"

    # Agent view: record that the full screen was sent to the vision model
    try:
        from tools.agent_view import AgentViewSession
        _vs = AgentViewSession("visual_inspect")
        _vs.add_vision_crop((0, 0, img.size[0], img.size[1]), None,
                            note=f"inspect: {question[:100]}")
        _vs.save()
    except Exception:
        print(f"[TRACE] tools.visual_inspect.visual_inspect: except Exception", file=sys.stderr, flush=True)
        pass

    # ------------------------------------------------------------------ #
    # 2. Resize proportionally to control API cost
    # ------------------------------------------------------------------ #
    try:
        orig_w, orig_h = img.size
        scale = resize_width / orig_w
        new_h = int(orig_h * scale)
        img = img.resize((resize_width, new_h), Image.LANCZOS)
    except Exception as exc:
        print(f"[TRACE] tools.visual_inspect.visual_inspect: except {str(exc)[:80]}", file=sys.stderr, flush=True)
        return f"ERROR: resize failed: {exc}"

    # ------------------------------------------------------------------ #
    # 3. Encode as base64 PNG
    # ------------------------------------------------------------------ #
    try:
        buf = io.BytesIO()
        img.save(buf, format="PNG", optimize=True)
        b64_data = base64.b64encode(buf.getvalue()).decode("utf-8")
    except Exception as exc:
        print(f"[TRACE] tools.visual_inspect.visual_inspect: except {str(exc)[:80]}", file=sys.stderr, flush=True)
        return f"ERROR: base64 encoding failed: {exc}"

    # ------------------------------------------------------------------ #
    # 4. Augment question with coordinate instruction
    # ------------------------------------------------------------------ #
    full_question = (
        f"{question}\n\n"
        f"The screenshot was resized to {resize_width}x{new_h} pixels. "
        f"For any UI elements you describe, include their approximate (x, y) pixel "
        f"coordinates in the resized image so a click automation script can use them."
    )

    # ------------------------------------------------------------------ #
    # 5a. Primary: NVIDIA kimi-k2.6 Vision
    # ------------------------------------------------------------------ #
    nvidia_key = os.environ.get("NVIDIA_API_KEY", "").strip()
    if nvidia_key:
        result = _call_nvidia_vision(b64_data, full_question, nvidia_key)
        if not result.startswith("ERROR:"):
            return result
        logger.warning("[VisualInspect] NVIDIA call failed: %s. Trying Anthropic.", result)

    # ------------------------------------------------------------------ #
    # 5b. Fallback 1: Anthropic Claude Vision
    # ------------------------------------------------------------------ #
    anthropic_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if anthropic_key:
        result = _call_anthropic_vision(b64_data, full_question, anthropic_key)
        if not result.startswith("ERROR:"):
            return result
        logger.warning("[VisualInspect] Anthropic call failed: %s. Trying Gemini.", result)

    # ------------------------------------------------------------------ #
    # 5c. Fallback 2: Gemini Vision
    # ------------------------------------------------------------------ #
    gemini_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if gemini_key:
        result = _call_gemini_vision(b64_data, full_question, gemini_key)
        return result

    return "ERROR: No vision API key available. Set NVIDIA_API_KEY, ANTHROPIC_API_KEY, or GEMINI_API_KEY in .env"


# ---------------------------------------------------------------------------
# Vision API helpers
# ---------------------------------------------------------------------------

def _call_nvidia_vision(b64_data: str, question: str, api_key: str, max_tokens: int = 1024) -> str:
    """Call moonshotai/kimi-k2.6 on NVIDIA NIM with a base64 PNG screenshot.

    Uses the OpenAI-compatible /v1/chat/completions endpoint at
    https://integrate.api.nvidia.com with multimodal image_url content.
    """
    print(f"[TRACE] tools.visual_inspect._call_nvidia_vision: enter", file=sys.stderr, flush=True)
    try:
        import httpx
    except ImportError:
        print(f"[TRACE] tools.visual_inspect._call_nvidia_vision: except ImportError", file=sys.stderr, flush=True)
        return "ERROR: httpx not installed — run: pip install httpx"

    payload = {
        "model": "moonshotai/kimi-k2.6",
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/png;base64,{b64_data}",
                        },
                    },
                    {
                        "type": "text",
                        "text": question,
                    },
                ],
            }
        ],
        "max_tokens": max_tokens,
        "temperature": 0.20,
        "top_p": 1.00,
        "stream": False,
    }

    try:
        resp = httpx.post(
            "https://integrate.api.nvidia.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=45.0,
        )
    except httpx.TimeoutException:
        print(f"[TRACE] tools.visual_inspect._call_nvidia_vision: except TimeoutException", file=sys.stderr, flush=True)
        return "ERROR: NVIDIA API timeout (45s)"
    except Exception as exc:
        print(f"[TRACE] tools.visual_inspect._call_nvidia_vision: except {str(exc)[:80]}", file=sys.stderr, flush=True)
        return f"ERROR: NVIDIA API request failed: {exc}"

    if resp.status_code != 200:
        return f"ERROR: NVIDIA API {resp.status_code}: {resp.text[:300]}"

    try:
        choices = resp.json()["choices"]
        return choices[0]["message"]["content"].strip()
    except Exception as exc:
        print(f"[TRACE] tools.visual_inspect._call_nvidia_vision: except {str(exc)[:80]}", file=sys.stderr, flush=True)
        return f"ERROR: NVIDIA response parse failed: {exc}"


def _call_anthropic_vision(b64_data: str, question: str, api_key: str, max_tokens: int = 1024) -> str:
    """Call Claude claude-sonnet-4-6 with a base64 PNG screenshot."""
    print(f"[TRACE] tools.visual_inspect._call_anthropic_vision: enter", file=sys.stderr, flush=True)
    try:
        import httpx
    except ImportError:
        print(f"[TRACE] tools.visual_inspect._call_anthropic_vision: except ImportError", file=sys.stderr, flush=True)
        return "ERROR: httpx not installed — run: pip install httpx"

    payload = {
        "model": "claude-sonnet-4-6",
        "max_tokens": max_tokens,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/png",
                            "data": b64_data,
                        },
                    },
                    {
                        "type": "text",
                        "text": question,
                    },
                ],
            }
        ],
    }

    try:
        resp = httpx.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json=payload,
            timeout=30.0,
        )
    except httpx.TimeoutException:
        print(f"[TRACE] tools.visual_inspect._call_anthropic_vision: except TimeoutException", file=sys.stderr, flush=True)
        return "ERROR: Anthropic API timeout (30s)"
    except Exception as exc:
        print(f"[TRACE] tools.visual_inspect._call_anthropic_vision: except {str(exc)[:80]}", file=sys.stderr, flush=True)
        return f"ERROR: Anthropic API request failed: {exc}"

    if resp.status_code != 200:
        return f"ERROR: Anthropic API {resp.status_code}: {resp.text[:300]}"

    try:
        content = resp.json()["content"]
        text_blocks = [b["text"] for b in content if b.get("type") == "text"]
        return "\n".join(text_blocks).strip()
    except Exception as exc:
        print(f"[TRACE] tools.visual_inspect._call_anthropic_vision: except {str(exc)[:80]}", file=sys.stderr, flush=True)
        return f"ERROR: Anthropic response parse failed: {exc}"


def _call_gemini_vision(b64_data: str, question: str, api_key: str, max_tokens: int = 1024) -> str:
    """Call Gemini 2.0 Flash with a base64 PNG screenshot."""
    print(f"[TRACE] tools.visual_inspect._call_gemini_vision: enter", file=sys.stderr, flush=True)
    try:
        import httpx
    except ImportError:
        print(f"[TRACE] tools.visual_inspect._call_gemini_vision: except ImportError", file=sys.stderr, flush=True)
        return "ERROR: httpx not installed — run: pip install httpx"

    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"gemini-2.0-flash:generateContent?key={api_key}"
    )
    payload = {
        "contents": [
            {
                "parts": [
                    {
                        "inline_data": {
                            "mime_type": "image/png",
                            "data": b64_data,
                        }
                    },
                    {"text": question},
                ]
            }
        ],
        "generationConfig": {"maxOutputTokens": max_tokens},
    }

    try:
        resp = httpx.post(url, json=payload, timeout=30.0)
    except httpx.TimeoutException:
        print(f"[TRACE] tools.visual_inspect._call_gemini_vision: except TimeoutException", file=sys.stderr, flush=True)
        return "ERROR: Gemini API timeout (30s)"
    except Exception as exc:
        print(f"[TRACE] tools.visual_inspect._call_gemini_vision: except {str(exc)[:80]}", file=sys.stderr, flush=True)
        return f"ERROR: Gemini API request failed: {exc}"

    if resp.status_code != 200:
        return f"ERROR: Gemini API {resp.status_code}: {resp.text[:300]}"

    try:
        candidates = resp.json()["candidates"]
        parts = candidates[0]["content"]["parts"]
        text_parts = [p["text"] for p in parts if "text" in p]
        return "\n".join(text_parts).strip()
    except Exception as exc:
        print(f"[TRACE] tools.visual_inspect._call_gemini_vision: except {str(exc)[:80]}", file=sys.stderr, flush=True)
        return f"ERROR: Gemini response parse failed: {exc}"

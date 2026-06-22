"""
Clipboard Reader — read on-screen text via the clipboard (Phase 28b).

Ctrl+A / Ctrl+C is ~20x faster than screenshot+OCR for text content and works on
dark themes where OCR struggles. But Ctrl+A has side effects in non-text apps
(File Explorer selects all files), so this is GATED to a strict allow-list of text
apps detected via the focused window's process. Unknown apps return a marker telling
the caller to fall back to screen_ocr / desktop_get_ui_tree.

The prior clipboard contents are always restored. Never raises.
"""
import sys

import time
import logging

logger = logging.getLogger(__name__)

# Process names (lowercased, no .exe) where Ctrl+A/Ctrl+C is safe.
SAFE_TEXT_PROCESSES = {
    "chrome", "msedge", "firefox", "brave", "opera", "vivaldi",
    "code", "code-insiders", "notepad", "notepad++", "sublime_text",
    "windowsterminal", "wt", "powershell", "pwsh", "cmd", "conhost",
    "devenv", "idea64", "pycharm64", "webstorm64", "obsidian", "acrobat",
    "winword", "soffice", "gvim", "atom",
}


def _focused_process_name() -> str:
    """Return the lowercased process name (no .exe) of the foreground window."""
    try:
        import ctypes
        import psutil
        user32 = ctypes.windll.user32
        hwnd = user32.GetForegroundWindow()
        pid = ctypes.c_ulong()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        proc = psutil.Process(pid.value)
        name = proc.name().lower()
        if name.endswith(".exe"):
            name = name[:-4]
        return name
    except Exception as e:
        print(f"[TRACE] tools.clipboard_reader._focused_process_name: except {str(e)[:80]}", file=sys.stderr, flush=True)
        logger.warning(f"[clipboard] could not resolve focused process: {e}")
        return ""


def _read_clipboard_text() -> str:
    try:
        import win32clipboard
        import win32con
        win32clipboard.OpenClipboard()
        try:
            if win32clipboard.IsClipboardFormatAvailable(win32con.CF_UNICODETEXT):
                return win32clipboard.GetClipboardData(win32con.CF_UNICODETEXT) or ""
            return ""
        finally:
            win32clipboard.CloseClipboard()
    except Exception:
        print(f"[TRACE] tools.clipboard_reader._read_clipboard_text: except Exception", file=sys.stderr, flush=True)
        return ""


def _set_clipboard_text(text: str) -> None:
    try:
        import win32clipboard
        import win32con
        win32clipboard.OpenClipboard()
        try:
            win32clipboard.EmptyClipboard()
            if text:
                win32clipboard.SetClipboardData(win32con.CF_UNICODETEXT, text)
        finally:
            win32clipboard.CloseClipboard()
    except Exception as e:
        print(f"[TRACE] tools.clipboard_reader._set_clipboard_text: except {str(e)[:80]}", file=sys.stderr, flush=True)
        logger.warning(f"[clipboard] restore failed: {e}")


def read_screen_text(mode: str = "all") -> str:
    """Read on-screen text via the clipboard. mode: 'all' (Ctrl+A+C) | 'selection' (Ctrl+C).

    Returns the text, or a "[clipboard] ..." marker if the focused app isn't a known
    text app or win32 is unavailable — so the caller can fall back to screen_ocr.
    """
    print(f"[TRACE] tools.clipboard_reader.read_screen_text: enter", file=sys.stderr, flush=True)
    proc = _focused_process_name()
    if not proc:
        return "[clipboard] could not detect focused app — use screen_ocr or desktop_get_ui_tree instead"
    if proc not in SAFE_TEXT_PROCESSES:
        return (f"[clipboard] unsafe app '{proc}' (Ctrl+A may have side effects) — "
                f"use screen_ocr or desktop_get_ui_tree instead")

    try:
        from tools.desktop_automation import desktop_press_keys
    except Exception as e:
        print(f"[TRACE] tools.clipboard_reader.read_screen_text: except {str(e)[:80]}", file=sys.stderr, flush=True)
        return f"[clipboard] key sender unavailable: {e} — use screen_ocr"

    original = _read_clipboard_text()
    try:
        if mode == "all":
            desktop_press_keys(["ctrl", "a"])
            time.sleep(0.05)
        desktop_press_keys(["ctrl", "c"])
        time.sleep(0.1)
        text = _read_clipboard_text()
        if not text:
            return "[clipboard] no text captured — use screen_ocr or desktop_get_ui_tree"
        return text
    except Exception as e:
        print(f"[TRACE] tools.clipboard_reader.read_screen_text: except {str(e)[:80]}", file=sys.stderr, flush=True)
        logger.warning(f"[clipboard] read failed: {e}")
        return f"[clipboard] read error: {e} — use screen_ocr"
    finally:
        # Always restore the user's prior clipboard.
        _set_clipboard_text(original)

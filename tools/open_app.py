"""
open_app — adaptive app opener (Phase 27).

Encodes the fallback decision tree the user described:
    1. Already open?        -> focus the existing window
    2. Native app installed? -> launch it, poll until the window appears, focus it
    3. Otherwise            -> open the web app in the user's REAL desktop browser

Returns a trace string describing which path was taken so the model learns which
apps need which path. Never raises — every failure returns a descriptive string
so the orchestrator can try another approach.
"""

import os
import sys
import time
import shutil
import logging
import subprocess

logger = logging.getLogger(__name__)

# Native launch commands (Windows). Value is an argv list passed to Popen.
# "start" entries go through the shell so Windows resolves the app the way the
# Start menu would. Plain entries are resolved against PATH via shutil.which.
_NATIVE_LAUNCH = {
    "chrome":      ["cmd", "/c", "start", "", "chrome"],
    "google chrome": ["cmd", "/c", "start", "", "chrome"],
    "edge":        ["cmd", "/c", "start", "", "msedge"],
    "firefox":     ["cmd", "/c", "start", "", "firefox"],
    "vs code":     ["code"],
    "vscode":      ["code"],
    "code":        ["code"],
    "notepad":     ["notepad"],
    "notepad++":   ["cmd", "/c", "start", "", "notepad++"],
    "word":        ["cmd", "/c", "start", "", "winword"],
    "excel":       ["cmd", "/c", "start", "", "excel"],
    "powerpoint":  ["cmd", "/c", "start", "", "powerpnt"],
    "terminal":    ["wt"],
    "powershell":  ["powershell"],
    "explorer":    ["explorer"],
    "file explorer": ["explorer"],
    "calculator":  ["cmd", "/c", "start", "", "calc"],
    "spotify":     ["cmd", "/c", "start", "", "spotify:"],
    "slack":       ["cmd", "/c", "start", "", "slack:"],
    "discord":     ["cmd", "/c", "start", "", "discord:"],
    "figma":       ["cmd", "/c", "start", "", "figma:"],
    "notion":      ["cmd", "/c", "start", "", "notion:"],
}

# Web-app fallback URLs, opened in the user's real default browser.
_WEB_APP_URLS = {
    "figma":    "https://www.figma.com",
    "notion":   "https://www.notion.so",
    "spotify":  "https://open.spotify.com",
    "slack":    "https://app.slack.com",
    "discord":  "https://discord.com/app",
    "chatgpt":  "https://chatgpt.com",
    "codex":    "https://chatgpt.com/codex",
    "gmail":    "https://mail.google.com",
    "gemini":   "https://gemini.google.com",
    "claude":   "https://claude.ai",
    "youtube":  "https://www.youtube.com",
    "maps":     "https://maps.google.com",
    "google maps": "https://maps.google.com",
    "docs":     "https://docs.google.com",
    "sheets":   "https://sheets.google.com",
    "linear":   "https://linear.app",
    "github":   "https://github.com",
}


def _norm(name: str) -> str:
    return (name or "").strip().lower()


def _window_open(app_name: str) -> bool:
    """True if any visible window title contains the app name."""
    try:
        from tools.windows import get_window_stack
        needle = _norm(app_name)
        for w in get_window_stack():
            if needle in (w.get("title", "") or "").lower():
                return True
    except Exception as e:
        logger.warning(f"[open_app] window scan failed: {e}")
    return False


def _launch_native(app_name: str) -> tuple[bool, str]:
    """Attempt to launch the native app. Returns (attempted, detail)."""
    key = _norm(app_name)
    argv = _NATIVE_LAUNCH.get(key)

    if argv is None:
        # Not in the map — try the bare name on PATH (e.g. "code", "obs").
        if shutil.which(key):
            argv = [key]
        else:
            return False, f"no native launcher known for '{app_name}'"

    # For plain (non-shell) launchers, confirm the binary exists first.
    if argv[0] not in ("cmd", "powershell") and not shutil.which(argv[0]):
        return False, f"'{argv[0]}' not found on PATH"

    try:
        subprocess.Popen(argv, shell=False,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True, f"launched via {' '.join(argv)}"
    except Exception as e:
        return False, f"launch failed: {e}"


def _open_in_browser(app_name: str) -> str:
    """Open the web app (or a search for it) in the user's real default browser."""
    key = _norm(app_name)
    url = _WEB_APP_URLS.get(key)
    fallback_search = False
    if not url:
        url = f"https://duckduckgo.com/?q={key.replace(' ', '+')}+web+app"
        fallback_search = True

    try:
        if sys.platform == "win32":
            os.startfile(url)  # system default browser, visible
        else:
            import webbrowser
            webbrowser.open(url)
    except Exception as e:
        return f"[open_app] browser fallback failed for '{app_name}': {e}"

    if fallback_search:
        return (f"[open_app] no native app or known web app for '{app_name}'. "
                f"Opened a web search in your browser: {url}")
    return f"[open_app] opened web app for '{app_name}' in your browser: {url}"


def open_app(app_name: str, prefer: str = "auto") -> str:
    """
    Adaptive app opener.

    prefer:
      "auto"   (default) — full decision tree: existing window -> native -> web
      "native" — only check window then native launch (no web fallback)
      "web"    — go straight to the browser web app
    """
    app_name = (app_name or "").strip()
    if not app_name:
        return "[open_app] no app_name provided."

    prefer = _norm(prefer) or "auto"
    trace = []

    if prefer == "web":
        return _open_in_browser(app_name)

    # Step 1 — already open?
    if _window_open(app_name):
        try:
            from tools.desktop_automation import desktop_focus_window
            res = desktop_focus_window(app_name)
            return f"[open_app] '{app_name}' was already open — focused existing window. ({res})"
        except Exception as e:
            return f"[open_app] '{app_name}' already open but focus failed: {e}"
    trace.append("not currently open")

    # Step 2 — native launch + confirm the window appears
    attempted, detail = _launch_native(app_name)
    trace.append(f"native: {detail}")
    if attempted:
        deadline = time.time() + 5.0
        while time.time() < deadline:
            if _window_open(app_name):
                try:
                    from tools.desktop_automation import desktop_focus_window
                    desktop_focus_window(app_name)
                except Exception:
                    pass
                return f"[open_app] launched native '{app_name}' and confirmed its window. ({' | '.join(trace)})"
            time.sleep(0.4)
        # Launched but window not confirmed yet — let the model verify visually.
        return (f"[open_app] launched native '{app_name}', but its window was not confirmed "
                f"within 5s — verify with visual_inspect. ({' | '.join(trace)})")

    if prefer == "native":
        return f"[open_app] could not open '{app_name}' natively and web fallback disabled. ({' | '.join(trace)})"

    # Step 3 — web fallback
    web_result = _open_in_browser(app_name)
    return f"{web_result} ({' | '.join(trace)})"

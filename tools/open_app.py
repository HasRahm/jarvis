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
from core.trace import trace as _jtrace
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
    return _find_open_window(app_name) is not None


def _find_open_window(app_name: str) -> dict | None:
    """Return the first visible window dict whose title contains the app name, else None."""
    _jtrace(f"[TRACE] tools.open_app._find_open_window: enter")
    try:
        from tools.windows import get_window_stack
        needle = _norm(app_name)
        for w in get_window_stack():
            if needle in (w.get("title", "") or "").lower():
                return w
    except Exception as e:
        _jtrace(f"[TRACE] tools.open_app._find_open_window: except {str(e)[:80]}")
        logger.warning(f"[open_app] window scan failed: {e}")
    return None


def _has_unsaved_marker(title: str) -> bool:
    """Windows convention: a leading '*' (or '●'/'•') in the title means UNSAVED changes.

    Typing into such a window risks destroying the user's unsaved work, so open_app must not
    silently reuse it. (e.g. Notepad shows '*Untitled - Notepad'.)
    """
    _jtrace(f"[TRACE] tools.open_app._has_unsaved_marker: enter")
    t = (title or "").strip()
    return t.startswith("*") or t.startswith("●") or t.startswith("•")


# Cache the Start-panel app list for this process run (Get-StartApps ~300ms).
_start_apps_cache = None


def _get_start_apps() -> list[dict]:
    """Enumerate every Start-panel entry (Win32 + UWP) via PowerShell Get-StartApps.

    Returns a list of {"name", "appid"}. Cached per process. [] on failure.
    """
    _jtrace(f"[TRACE] tools.open_app._get_start_apps: enter")
    global _start_apps_cache
    if _start_apps_cache is not None:
        return _start_apps_cache
    _start_apps_cache = []
    if sys.platform != "win32":
        return _start_apps_cache
    try:
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "Get-StartApps | ConvertTo-Json -Compress"],
            capture_output=True, text=True, timeout=15,
        )
        if proc.returncode == 0 and proc.stdout.strip():
            import json as _json
            data = _json.loads(proc.stdout)
            if isinstance(data, dict):
                data = [data]
            _start_apps_cache = [
                {"name": (d.get("Name") or "").strip(), "appid": (d.get("AppID") or "").strip()}
                for d in data if d.get("Name") and d.get("AppID")
            ]
    except Exception as e:
        _jtrace(f"[TRACE] tools.open_app._get_start_apps: except {str(e)[:80]}")
        logger.warning(f"[open_app] Get-StartApps failed: {e}")
    return _start_apps_cache


def _find_in_start_panel(app_name: str) -> str | None:
    """Return an AppsFolder launch AppID for the best Start-panel name match, or None."""
    _jtrace(f"[TRACE] tools.open_app._find_in_start_panel: enter")
    key = _norm(app_name)
    apps = _get_start_apps()
    # Exact, then startswith, then substring.
    for pred in (lambda n: n == key,
                 lambda n: n.startswith(key),
                 lambda n: key in n):
        for app in apps:
            if pred(app["name"].lower()):
                return app["appid"]
    return None


def _find_shortcut(app_name: str) -> str | None:
    """Search taskbar-pinned and Start-Menu .lnk shortcuts for a name match."""
    _jtrace(f"[TRACE] tools.open_app._find_shortcut: enter")
    key = _norm(app_name)
    if sys.platform != "win32":
        return None
    appdata = os.environ.get("APPDATA", "")
    programdata = os.environ.get("ProgramData", r"C:\ProgramData")
    search_dirs = [
        os.path.join(appdata, r"Microsoft\Internet Explorer\Quick Launch\User Pinned\TaskBar"),
        os.path.join(appdata, r"Microsoft\Windows\Start Menu\Programs"),
        os.path.join(programdata, r"Microsoft\Windows\Start Menu\Programs"),
    ]
    import glob
    for base in search_dirs:
        if not base or not os.path.isdir(base):
            continue
        for lnk in glob.glob(os.path.join(base, "**", "*.lnk"), recursive=True):
            if key in os.path.splitext(os.path.basename(lnk))[0].lower():
                return lnk
    return None


def find_app_launch(app_name: str) -> dict | None:
    """Discover how to launch an app (no side effects — pure discovery).

    Order: PATH/known map -> Start panel (Get-StartApps) -> taskbar/Start-Menu .lnk.
    Returns {"method", "argv"|"appid"|"lnk"} or None if nothing found.
    """
    _jtrace(f"[TRACE] tools.open_app.find_app_launch: enter")
    key = _norm(app_name)

    # 1. Known map / PATH
    argv = _NATIVE_LAUNCH.get(key)
    if argv is None and shutil.which(key):
        argv = [key]
    if argv is not None:
        if argv[0] in ("cmd", "powershell") or shutil.which(argv[0]):
            return {"method": "path", "argv": argv}

    # 2. Start panel (covers Win32 + UWP store apps)
    appid = _find_in_start_panel(app_name)
    if appid:
        return {"method": "start_panel", "appid": appid}

    # 3. Taskbar-pinned / Start-Menu shortcuts
    lnk = _find_shortcut(app_name)
    if lnk:
        return {"method": "shortcut", "lnk": lnk}

    return None


def _launch_native(app_name: str) -> tuple[bool, str]:
    """Attempt to launch the app via the full discovery chain. Returns (attempted, detail)."""
    _jtrace(f"[TRACE] tools.open_app._launch_native: enter")
    found = find_app_launch(app_name)
    if not found:
        return False, f"'{app_name}' not found on PATH, Start panel, taskbar, or Start Menu"

    try:
        method = found["method"]
        if method == "path":
            subprocess.Popen(found["argv"], shell=False,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True, f"launched via {' '.join(found['argv'])}"
        if method == "start_panel":
            # Launch by AppsFolder AppID — works for Win32 and UWP.
            subprocess.Popen(["explorer.exe", f"shell:AppsFolder\\{found['appid']}"],
                             shell=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True, f"launched from Start panel (AppID={found['appid']})"
        if method == "shortcut":
            os.startfile(found["lnk"])
            return True, f"launched via shortcut {os.path.basename(found['lnk'])}"
    except Exception as e:
        _jtrace(f"[TRACE] tools.open_app._launch_native: except {str(e)[:80]}")
        return False, f"launch failed: {e}"
    return False, f"no launch method for '{app_name}'"


def _open_in_browser(app_name: str) -> str:
    """Open the web app (or a search for it) in the user's real default browser."""
    _jtrace(f"[TRACE] tools.open_app._open_in_browser: enter")
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
        _jtrace(f"[TRACE] tools.open_app._open_in_browser: except {str(e)[:80]}")
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
    _jtrace(f"[TRACE] tools.open_app.open_app: enter")
    app_name = (app_name or "").strip()
    if not app_name:
        return "[open_app] no app_name provided."

    prefer = _norm(prefer) or "auto"
    trace = []

    if prefer == "web":
        return _open_in_browser(app_name)

    # Step 1 — already open?
    unsaved_avoided = False
    existing = _find_open_window(app_name)
    if existing:
        title = existing.get("title", "") or ""
        if _has_unsaved_marker(title):
            # Data-loss guard (Phase 46): the matching window has UNSAVED changes. Do NOT focus it
            # (the next type/click could overwrite the user's work). Fall through to launch a FRESH
            # instance, and warn loudly so the model verifies it's on the new (untitled) window.
            unsaved_avoided = True
            trace.append(f"existing window '{title[:48]}' has UNSAVED changes — refusing to reuse it")
        else:
            try:
                from tools.desktop_automation import desktop_focus_window
                res = desktop_focus_window(app_name)
                return f"[open_app] '{app_name}' was already open — focused existing window. ({res})"
            except Exception as e:
                _jtrace(f"[TRACE] tools.open_app.open_app: except {str(e)[:80]}")
                return f"[open_app] '{app_name}' already open but focus failed: {e}"
    else:
        trace.append("not currently open")

    # Step 2 — native launch + confirm the window appears
    attempted, detail = _launch_native(app_name)
    trace.append(f"native: {detail}")
    if attempted:
        deadline = time.time() + 5.0
        _warn = (" ⚠ An UNSAVED window of this app was left untouched — before typing, VERIFY you are "
                 "on the NEW (untitled, no '*') window, not the user's unsaved document."
                 if unsaved_avoided else "")
        while time.time() < deadline:
            if _window_open(app_name):
                try:
                    from tools.desktop_automation import desktop_focus_window
                    desktop_focus_window(app_name)
                except Exception:
                    _jtrace(f"[TRACE] tools.open_app.open_app: except Exception")
                    pass
                return f"[open_app] launched native '{app_name}' and confirmed its window.{_warn} ({' | '.join(trace)})"
            time.sleep(0.4)
        # Launched but window not confirmed yet — let the model verify visually.
        return (f"[open_app] launched native '{app_name}', but its window was not confirmed "
                f"within 5s — verify with visual_inspect. ({' | '.join(trace)})")

    if prefer == "native":
        return f"[open_app] could not open '{app_name}' natively and web fallback disabled. ({' | '.join(trace)})"

    # Step 2b — resolve a smarter fallback (alternative app / API / specific web URL)
    try:
        from core.system.app_resolver import resolve
        res = resolve(app_name, action="open")
        method = res.get("method")
        if method == "alternative_app":
            alt = res.get("app")
            attempted2, detail2 = _launch_native(alt)
            trace.append(f"alternative '{alt}': {detail2}")
            if attempted2:
                return f"[open_app] {res.get('note')} ({' | '.join(trace)})"
        elif method == "api":
            trace.append(f"api: {res.get('client')}")
            return f"[open_app] {res.get('note')} — use the API client/MCP rather than a window. ({' | '.join(trace)})"
        elif method == "browser" and res.get("url"):
            try:
                if sys.platform == "win32":
                    os.startfile(res["url"])
                else:
                    import webbrowser
                    webbrowser.open(res["url"])
                trace.append(f"browser: {res['url']}")
                return f"[open_app] {res.get('note')} ({' | '.join(trace)})"
            except Exception as e:
                _jtrace(f"[TRACE] tools.open_app.open_app: except {str(e)[:80]}")
                trace.append(f"browser open failed: {e}")
    except Exception as e:
        _jtrace(f"[TRACE] tools.open_app.open_app: except {str(e)[:80]}")
        trace.append(f"resolver skipped: {e}")

    # Step 3 — generic web fallback (known web app URL or DuckDuckGo search)
    web_result = _open_in_browser(app_name)
    return f"{web_result} ({' | '.join(trace)})"

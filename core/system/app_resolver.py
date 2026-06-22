"""
App Resolver — check if an app is available and route to the best alternative (Phase 28b).

Before Jarvis tries to open an app, resolve() determines the best way to accomplish
the task: the native app if installed, else an alternative app, else an API client
(when credentials exist), else the browser version, else a web search.

Wired into tools/open_app.py so opening an app never dead-ends on missing software.
Never raises.
"""
import sys
from core.trace import trace as _jtrace

import os
import shutil
import logging

logger = logging.getLogger(__name__)

# app -> ordered fallbacks. type ∈ {app, api, browser}
APP_ALTERNATIVES = {
    "excel": [
        {"type": "app", "name": "libreoffice", "exe": "soffice"},
        {"type": "browser", "url": "https://sheets.google.com"},
    ],
    "word": [
        {"type": "app", "name": "libreoffice", "exe": "soffice"},
        {"type": "browser", "url": "https://docs.google.com"},
    ],
    "powerpoint": [
        {"type": "app", "name": "libreoffice", "exe": "soffice"},
        {"type": "browser", "url": "https://slides.google.com"},
    ],
    "photoshop": [
        {"type": "app", "name": "gimp", "exe": "gimp"},
        {"type": "app", "name": "paint.net", "exe": "paintdotnet"},
        {"type": "browser", "url": "https://www.photopea.com"},
    ],
    "figma": [
        {"type": "api", "client": "FigmaAPIClient", "key": "FIGMA_MCP_TOKEN"},
        {"type": "browser", "url": "https://www.figma.com"},
    ],
    "slack": [
        {"type": "api", "client": "SlackAPIClient", "key": "SLACK_TOKEN"},
        {"type": "browser", "url": "https://app.slack.com"},
    ],
    "outlook": [
        {"type": "browser", "url": "https://outlook.live.com"},
        {"type": "app", "name": "thunderbird", "exe": "thunderbird"},
    ],
    "chrome": [
        {"type": "app", "name": "edge", "exe": "msedge"},
        {"type": "app", "name": "firefox", "exe": "firefox"},
    ],
    "github": [
        {"type": "api", "client": "GitHubAPIClient", "key": "GITHUB_TOKEN"},
        {"type": "browser", "url": "https://github.com"},
    ],
}

# name variants used for PATH lookup
_EXE_VARIANTS = {
    "chrome": ["chrome", "google-chrome", "chromium"],
    "edge": ["msedge"],
    "firefox": ["firefox"],
    "excel": ["excel"],
    "word": ["winword"],
    "powerpoint": ["powerpnt"],
    "code": ["code", "code-insiders"],
    "libreoffice": ["soffice"],
}


def _api_key_present(env_var: str) -> bool:
    return bool(env_var and os.environ.get(env_var))


def is_installed(app_name: str) -> bool:
    """True if the app can be found via PATH, registry, running process, or install dirs."""
    _jtrace(f"[TRACE] core.system.app_resolver.is_installed: enter")
    key = (app_name or "").strip().lower()
    if not key:
        return False

    # 1. PATH (with known name variants)
    for exe in _EXE_VARIANTS.get(key, [key]):
        if shutil.which(exe):
            return True

    # 2. Windows registry App Paths
    try:
        import winreg
        for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
            try:
                with winreg.OpenKey(
                    hive,
                    r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\\" + f"{key}.exe"
                ):
                    return True
            except OSError:
                _jtrace(f"[TRACE] core.system.app_resolver.is_installed: except OSError")
                continue
    except Exception:
        _jtrace(f"[TRACE] core.system.app_resolver.is_installed: except Exception")
        pass

    # 3. Running process
    try:
        import psutil
        for p in psutil.process_iter(["name"]):
            n = (p.info.get("name") or "").lower()
            if n.startswith(key):
                return True
    except Exception:
        _jtrace(f"[TRACE] core.system.app_resolver.is_installed: except Exception")
        pass

    # 4. Common install dirs
    for base in (os.environ.get("ProgramFiles", r"C:\Program Files"),
                 os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),
                 os.path.join(os.path.expanduser("~"), "AppData", "Local")):
        try:
            if base and os.path.isdir(os.path.join(base, app_name)):
                return True
        except Exception:
            _jtrace(f"[TRACE] core.system.app_resolver.is_installed: except Exception")
            continue

    # 5. Start panel (Get-StartApps) — matches what open_app can actually launch.
    try:
        from tools.open_app import _find_in_start_panel
        if _find_in_start_panel(app_name):
            return True
    except Exception:
        _jtrace(f"[TRACE] core.system.app_resolver.is_installed: except Exception")
        pass

    return False


def resolve(app_name: str, action: str = "open") -> dict:
    """Return the best method to accomplish *action* on *app_name*.

    {"method": native_app|alternative_app|api|browser|web_search, "app"/"url"/"client",
     "note": substitution message or None, "confidence": float}
    """
    _jtrace(f"[TRACE] core.system.app_resolver.resolve: enter")
    app_name = (app_name or "").strip()
    if not app_name:
        return {"method": "web_search", "query": "", "note": None, "confidence": 0.0}

    if is_installed(app_name):
        return {"method": "native_app", "app": app_name, "note": None, "confidence": 1.0}

    for alt in APP_ALTERNATIVES.get(app_name.lower(), []):
        if alt["type"] == "app" and is_installed(alt["name"]):
            return {"method": "alternative_app", "app": alt["name"], "exe": alt.get("exe"),
                    "note": f"{app_name} not found — using {alt['name']} instead",
                    "confidence": 0.85}
        if alt["type"] == "api" and _api_key_present(alt.get("key", "")):
            return {"method": "api", "client": alt["client"],
                    "note": f"Using {alt['client']} API instead of {app_name} desktop",
                    "confidence": 0.95}
        if alt["type"] == "browser":
            return {"method": "browser", "url": alt["url"],
                    "note": f"{app_name} not installed — opening browser version at {alt['url']}",
                    "confidence": 0.75}

    return {"method": "web_search",
            "query": f"{app_name} {action} online",
            "note": f"No alternative found for {app_name} — searching the web.",
            "confidence": 0.4}

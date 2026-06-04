"""tools/disk_cleanup.py — Intelligent 4-stage disk cleanup for Windows.

Stages:
  1. scan()          — Read-only survey of disk usage by category.
  2. safe_clean()    — Auto-delete always-safe files (temp, cache, old log backups).
  3. judgment_scan() — Return candidates needing human/AI approval (large, old, stale).
  4. never_touch     — Guarded via never_touch_check(); never reported or deleted.

All deletions are gated: never_touch_check() is called before any removal.
safe_clean(dry_run=True) is the default — no actual deletions without opt-in.
"""

import os
import glob
import shutil
import logging
import fnmatch
from datetime import datetime, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)

# ── Never-touch paths ───────────────────────────────────────────────────────
# Resolved at import time dynamically so they work on any machine.
_DEFAULT_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_PROJECT_ROOT = os.environ.get(
    "JARVIS_WIN_PROJECT_ROOT",
    _DEFAULT_PROJECT_ROOT
).replace("/", "\\")

_USER_PROFILE = os.environ.get("USERPROFILE", os.path.expanduser("~"))
_APPDATA_ROAMING = os.path.join(_USER_PROFILE, "AppData", "Roaming")
_APPDATA_LOCAL = os.path.join(_USER_PROFILE, "AppData", "Local")

_NEVER_TOUCH_PREFIXES = [
    r"C:\Windows",
    r"C:\Program Files",
    r"C:\Program Files (x86)",
    r"C:\ProgramData\Microsoft",
    os.path.join(_APPDATA_ROAMING, "Microsoft"),
    os.path.join(_APPDATA_LOCAL, "Microsoft", "WindowsApps"),
    _PROJECT_ROOT,   # Jarvis project root — never auto-clean
]

# Normalize to lowercase for comparison (Windows paths are case-insensitive)
_NEVER_TOUCH_NORM = [p.lower() for p in _NEVER_TOUCH_PREFIXES]


def never_touch_check(path: str) -> bool:
    """Return True if path is under any never-touch prefix or a clean exclusion.

    Always call this before deleting anything.
    """
    # Normalize slashes to match current OS
    normalized_path = path.replace("\\", "/").replace("/", os.sep)
    norm = os.path.abspath(normalized_path).lower()
    
    # Normalize prefixes to match current OS slashes and get their abspath
    normalized_prefixes = [
        os.path.abspath(p.replace("\\", "/").replace("/", os.sep)).lower()
        for p in _NEVER_TOUCH_PREFIXES
    ]
    
    if any(norm == p or norm.startswith(p + os.sep) for p in normalized_prefixes):
        return True
        
    # Also protect tool-specific subdirs inside otherwise-cleanable dirs
    excl_norm = [
        os.path.abspath(e.replace("\\", "/").replace("/", os.sep)).lower()
        for e in _CLEAN_EXCLUSIONS
    ]
    return any(norm == e or norm.startswith(e + os.sep) for e in excl_norm)


# ── Stage 1: Scan ───────────────────────────────────────────────────────────

def _dir_size_bytes(path: str) -> int:
    """Return total size of a directory tree in bytes (0 if inaccessible)."""
    total = 0
    try:
        for dirpath, _dirs, files in os.walk(path):
            for f in files:
                try:
                    total += os.path.getsize(os.path.join(dirpath, f))
                except OSError:
                    pass
    except (PermissionError, OSError):
        pass
    return total


def _dir_size_mb(path: str) -> float:
    """Return total size of a directory tree in MB (0 if inaccessible)."""
    return round(_dir_size_bytes(path) / (1024 * 1024), 2)


def _file_size_mb(path: str) -> float:
    try:
        return round(os.path.getsize(path) / (1024 * 1024), 2)
    except OSError:
        return 0.0


def scan() -> dict:
    """Stage 1 — read-only disk usage survey.

    Returns a dict with keys in both bytes and MB for complete frontend compatibility.
    """
    temp_bytes = (
        _dir_size_bytes(r"C:\Windows\Temp") +
        _dir_size_bytes(os.path.expandvars(r"%LOCALAPPDATA%\Temp"))
    )

    cache_bytes = _dir_size_bytes(
        os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\Windows\INetCache")
    )

    win_update_bytes = _dir_size_bytes(r"C:\Windows\SoftwareDistribution\Download")

    # Jarvis rotated log backups: logs/*.log.1, logs/*.log.2 etc.
    logs_dir = os.path.join(_PROJECT_ROOT, "logs")
    jarvis_logs_bytes = 0
    if os.path.isdir(logs_dir):
        for fname in os.listdir(logs_dir):
            if fname.endswith(tuple(f".{i}" for i in range(1, 10))):
                try:
                    jarvis_logs_bytes += os.path.getsize(os.path.join(logs_dir, fname))
                except OSError:
                    pass

    user_downloads_bytes = _dir_size_bytes(os.path.expandvars(r"%USERPROFILE%\Downloads"))

    total_safe_bytes = temp_bytes + cache_bytes + win_update_bytes + jarvis_logs_bytes
    total_bytes = total_safe_bytes + user_downloads_bytes

    return {
        # Bytes (expected by phone/mc-hud.jsx)
        "temp_bytes": temp_bytes,
        "cache_bytes": cache_bytes,
        "win_update_bytes": win_update_bytes,
        "jarvis_logs_bytes": jarvis_logs_bytes,
        "user_downloads_bytes": user_downloads_bytes,
        "total_safe_bytes": total_safe_bytes,
        "total_bytes": total_bytes,
        # Megabytes (backward compatibility)
        "temp_mb": round(temp_bytes / (1024 * 1024), 2),
        "cache_mb": round(cache_bytes / (1024 * 1024), 2),
        "win_update_mb": round(win_update_bytes / (1024 * 1024), 2),
        "jarvis_logs_mb": round(jarvis_logs_bytes / (1024 * 1024), 2),
        "user_downloads_mb": round(user_downloads_bytes / (1024 * 1024), 2),
        "total_safe_mb": round(total_safe_bytes / (1024 * 1024), 2),
        "total_mb": round(total_bytes / (1024 * 1024), 2),
    }


# ── Stage 2: Safe auto-clean ────────────────────────────────────────────────

def _safe_remove(path: str, dry_run: bool) -> int:
    """Delete a file or directory tree if not under a never-touch prefix.

    Returns bytes freed (0 on dry_run or failure).
    """
    if never_touch_check(path):
        logger.warning(f"[cleanup] Blocked never-touch path: {path}")
        return 0
    try:
        size = 0
        if os.path.isfile(path):
            size = os.path.getsize(path)
            if not dry_run:
                os.remove(path)
        elif os.path.isdir(path):
            size = sum(
                os.path.getsize(os.path.join(dp, f))
                for dp, _, files in os.walk(path)
                for f in files
                if not never_touch_check(os.path.join(dp, f))
            )
            if not dry_run:
                shutil.rmtree(path, ignore_errors=True)
        return size
    except (PermissionError, OSError) as e:
        logger.debug(f"[cleanup] Could not remove {path}: {e}")
        return 0


# ── Module-level safe-clean directory list (injectable for tests) ────────────
# Tests can monkeypatch this list to avoid needing admin-level system dirs.
_SAFE_CLEAN_DIRS: list[str] = []  # populated lazily in safe_clean()

# Subdirectories inside safe-clean targets that must never be touched.
# Claude Code (and other tools) write output files to %LOCALAPPDATA%\Temp\claude\
_CLEAN_EXCLUSIONS: list[str] = [
    os.path.join(os.path.expandvars("%LOCALAPPDATA%"), "Temp", "claude"),
    os.path.join(os.path.expandvars("%LOCALAPPDATA%"), "Temp", "claude-code"),
]


def _clean_dir_contents(directory: str, dry_run: bool) -> tuple[int, int]:
    """Delete contents of a directory (not the dir itself).

    Returns (files_deleted, bytes_freed). Silently skips on PermissionError.
    """
    files_deleted = 0
    bytes_freed = 0
    if not os.path.isdir(directory):
        return 0, 0
    try:
        entries = list(os.scandir(directory))
    except (PermissionError, OSError) as e:
        logger.debug(f"[cleanup] Cannot scan {directory}: {e}")
        return 0, 0
    for entry in entries:
        freed = _safe_remove(entry.path, dry_run)
        if freed > 0 or (not dry_run and not os.path.exists(entry.path)):
            files_deleted += 1
            bytes_freed += freed
    return files_deleted, bytes_freed


def safe_clean(dry_run: bool = True) -> dict:
    """Stage 2 — delete always-safe categories.

    dry_run=True (default): reports what *would* be deleted, touches nothing.
    dry_run=False: actually deletes. Call only after user confirmation.

    Returns:
        files_deleted  — count of files/dirs removed
        bytes_freed    — total bytes reclaimed
        mb_freed       — bytes_freed / 1024^2
        dry_run        — echoes the flag
        targets        — list of cleaned paths (for logging)
    """
    total_files = 0
    total_bytes = 0
    targets = []

    def _clean(path):
        nonlocal total_files, total_bytes
        if not os.path.exists(path):
            return
        f, b = _clean_dir_contents(path, dry_run)
        if f or b:
            total_files += f
            total_bytes += b
            targets.append({"path": path, "files": f, "mb": round(b / (1024 * 1024), 2)})

    # Use injectable list if set (for tests), else default Windows system dirs
    import tools.disk_cleanup as _self_mod
    dirs_override = _self_mod._SAFE_CLEAN_DIRS
    if dirs_override:
        for d in dirs_override:
            _clean(d)
    else:
        # Windows Temp
        _clean(r"C:\Windows\Temp")
        _clean(os.path.expandvars(r"%LOCALAPPDATA%\Temp"))

        # INet / browser cache
        _clean(os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\Windows\INetCache"))

        # Windows Update download cache
        _clean(r"C:\Windows\SoftwareDistribution\Download")

        # Jarvis rotated log backups only (leave the active .log files)
        logs_dir = os.path.join(_PROJECT_ROOT, "logs")
        if os.path.isdir(logs_dir):
            for fname in os.listdir(logs_dir):
                if fname.endswith(tuple(f".{i}" for i in range(1, 10))):
                    fpath = os.path.join(logs_dir, fname)
                    freed = _safe_remove(fpath, dry_run)
                    if freed > 0 or (not dry_run and not os.path.exists(fpath)):
                        total_files += 1
                        total_bytes += freed
                        targets.append({"path": fpath, "files": 1, "mb": round(freed / (1024 * 1024), 2)})

    return {
        "files_deleted": total_files,
        "bytes_freed": total_bytes,
        "freed_bytes": total_bytes,      # Expected by phone/mc-hud.jsx
        "deleted_files": total_files,    # Expected by phone/mc-hud.jsx
        "mb_freed": round(total_bytes / (1024 * 1024), 2),
        "dry_run": dry_run,
        "targets": targets,
    }


# ── Stage 3: Judgment-needed ────────────────────────────────────────────────

_STALE_ENV_MARKERS = ("node_modules", ".venv", "venv", "__pycache__", ".tox")
_JUDGMENT_LARGE_MB = 500    # files over this threshold get flagged
_JUDGMENT_DOWNLOAD_DAYS = 90
_JUDGMENT_ENV_DAYS = 60     # stale env if parent project untouched this many days


def _days_since(path: str) -> int:
    """Days since the file/dir was last modified."""
    try:
        mtime = os.path.getmtime(path)
        return (datetime.now() - datetime.fromtimestamp(mtime)).days
    except OSError:
        return 0


def _has_recent_git_activity(directory: str, days: int = 30) -> bool:
    """True if the git repo in `directory` has commits or changes in last `days` days."""
    try:
        import subprocess
        result = subprocess.run(
            ["git", "-C", directory, "log", f"--since={days} days ago", "--oneline", "--max-count=1"],
            capture_output=True, text=True, timeout=5
        )
        return bool(result.stdout.strip())
    except Exception:
        return False  # if we can't check, assume active


def _ollama_suggest(description: str) -> str:
    """Ask Gemma4 for a one-sentence keep/delete suggestion. Falls back gracefully."""
    if os.environ.get("JARVIS_CI") == "true":
        return "CI mode: no AI suggestion."
    try:
        import requests
        ollama_host = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
        prompt = (
            f"{description}\n"
            "Should I delete this to free disk space, or keep it? "
            "Reply in one sentence."
        )
        resp = requests.post(
            f"{ollama_host}/api/generate",
            json={"model": "gemma3:4b", "prompt": prompt, "stream": False},
            timeout=15,
        )
        if resp.ok:
            return resp.json().get("response", "").strip()
    except Exception as e:
        logger.debug(f"[cleanup] Ollama suggestion failed: {e}")
    return "Could not get AI suggestion."


def judgment_scan() -> list[dict]:
    """Stage 3 — return items that need human/AI judgment before deletion.

    Each item dict:
        path        — absolute path
        type        — 'large_file' | 'old_download' | 'stale_env'
        size_mb     — size in MB
        age_days    — days since last modification
        reason      — human-readable reason for flagging
        ai_suggestion — one-sentence AI keep/delete suggestion
        safe_to_skip — True if never_touch_check() blocks this path
    """
    candidates = []

    # ── A. Large files (>500 MB) in user home, excluding never-touch ─────────
    user_home = os.path.expandvars(r"%USERPROFILE%")
    _walk_dirs = [
        os.path.join(user_home, "Documents"),
        os.path.join(user_home, "Downloads"),
        os.path.join(user_home, "Desktop"),
        os.path.join(user_home, "Videos"),
        os.path.join(user_home, "Music"),
    ]
    seen_paths = set()
    for root_dir in _walk_dirs:
        if not os.path.isdir(root_dir):
            continue
        for dirpath, dirs, files in os.walk(root_dir):
            if never_touch_check(dirpath):
                dirs.clear()
                continue
            for fname in files:
                fpath = os.path.join(dirpath, fname)
                if fpath in seen_paths:
                    continue
                seen_paths.add(fpath)
                try:
                    size_bytes = os.path.getsize(fpath)
                except OSError:
                    continue
                size_mb = size_bytes / (1024 * 1024)
                if size_mb >= _JUDGMENT_LARGE_MB:
                    age = _days_since(fpath)
                    desc = f"Large file: {fname} ({size_mb:.0f} MB, {age} days old) at {fpath}"
                    candidates.append({
                        "path": fpath,
                        "type": "large_file",
                        "size_mb": round(size_mb, 1),
                        "age_days": age,
                        "reason": f"File is {size_mb:.0f} MB and has not changed in {age} days.",
                        "ai_suggestion": _ollama_suggest(desc),
                        "safe_to_skip": False,
                    })

    # ── B. Old Downloads (>90 days) ───────────────────────────────────────────
    downloads_dir = os.path.join(user_home, "Downloads")
    if os.path.isdir(downloads_dir):
        for entry in os.scandir(downloads_dir):
            if never_touch_check(entry.path):
                continue
            age = _days_since(entry.path)
            if age >= _JUDGMENT_DOWNLOAD_DAYS:
                try:
                    size_mb = (
                        _dir_size_mb(entry.path) if entry.is_dir()
                        else round(entry.stat().st_size / (1024 * 1024), 1)
                    )
                except OSError:
                    size_mb = 0.0
                if size_mb < 1 and age < 180:
                    continue  # skip tiny old files unless really old
                desc = f"Old download: {entry.name} ({size_mb:.0f} MB, {age} days old)"
                candidates.append({
                    "path": entry.path,
                    "type": "old_download",
                    "size_mb": size_mb,
                    "age_days": age,
                    "reason": f"In Downloads, {age} days old, {size_mb:.0f} MB.",
                    "ai_suggestion": _ollama_suggest(desc),
                    "safe_to_skip": False,
                })

    # ── C. Stale dev environments (node_modules / .venv in old projects) ─────
    dev_roots = [
        os.path.join(user_home, "Documents"),
        os.path.join(user_home, "Desktop"),
        os.path.join(user_home, "dev"),
        os.path.join(user_home, "projects"),
        os.path.join(user_home, "repos"),
        r"C:\dev",
        r"C:\projects",
    ]
    for dev_root in dev_roots:
        if not os.path.isdir(dev_root):
            continue
        for entry in os.scandir(dev_root):
            if not entry.is_dir() or never_touch_check(entry.path):
                continue
            # Look one level down for stale env markers
            for marker in _STALE_ENV_MARKERS:
                marker_path = os.path.join(entry.path, marker)
                if not os.path.isdir(marker_path):
                    continue
                if never_touch_check(marker_path):
                    continue
                parent_age = _days_since(entry.path)
                if parent_age < _JUDGMENT_ENV_DAYS:
                    continue
                # Skip if git repo has recent activity
                if _has_recent_git_activity(entry.path, days=_JUDGMENT_ENV_DAYS):
                    continue
                size_mb = _dir_size_mb(marker_path)
                if size_mb < 10:
                    continue  # not worth flagging tiny envs
                desc = (
                    f"Stale {marker} at {marker_path} ({size_mb:.0f} MB, "
                    f"parent project last touched {parent_age} days ago, no recent git activity)"
                )
                candidates.append({
                    "path": marker_path,
                    "type": "stale_env",
                    "size_mb": round(size_mb, 1),
                    "age_days": parent_age,
                    "reason": (
                        f"{marker} folder ({size_mb:.0f} MB) in project "
                        f"untouched for {parent_age} days with no recent git commits."
                    ),
                    "ai_suggestion": _ollama_suggest(desc),
                    "safe_to_skip": False,
                })

    # Sort by size descending (biggest savings first)
    candidates.sort(key=lambda x: x["size_mb"], reverse=True)
    return candidates


# ── Deletion helper for approved judgment items ──────────────────────────────

def delete_judgment_item(path: str) -> dict:
    """Delete a single item approved by the user from judgment_scan().

    Returns {deleted: bool, mb_freed: float, error: str|None}.
    Never deletes never-touch paths.
    """
    if never_touch_check(path):
        return {"deleted": False, "mb_freed": 0.0, "error": "Path is in never-touch list."}
    try:
        if os.path.isfile(path):
            size = os.path.getsize(path)
            os.remove(path)
        elif os.path.isdir(path):
            size = sum(
                os.path.getsize(os.path.join(dp, f))
                for dp, _, files in os.walk(path)
                for f in files
            )
            shutil.rmtree(path, ignore_errors=False)
        else:
            return {"deleted": False, "mb_freed": 0.0, "error": "Path not found."}
        logger.info(f"[cleanup] Deleted: {path} ({size / (1024*1024):.1f} MB)")
        return {"deleted": True, "mb_freed": round(size / (1024 * 1024), 2), "error": None}
    except Exception as e:
        logger.error(f"[cleanup] Failed to delete {path}: {e}")
        return {"deleted": False, "mb_freed": 0.0, "error": str(e)}

"""
Session persistence — save and restore REPL conversation history.

Two layers:
  • Named/timestamped sessions   → ~/.jarvis/sessions/<name>_<ts>.jsonl  (manual /save, /load)
  • Per-directory rolling memory  → ~/.jarvis/sessions/by_dir/<cwd-hash>.jsonl
    Auto-saved on exit and auto-loaded on startup so "the same directory remembers" — like a
    project notebook. The cwd is hashed (not embedded) to stay filesystem-safe and private.

Each line is one message dict: {"role": ..., "content": ...}.
System messages are stripped on save (they are rebuilt at startup).
"""
import json
import os
import hashlib
from datetime import datetime
from pathlib import Path

_SESSIONS_DIR = Path.home() / ".jarvis" / "sessions"
_BY_DIR = _SESSIONS_DIR / "by_dir"


def _ensure_dir() -> Path:
    _SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    return _SESSIONS_DIR


# ── per-directory rolling memory ───────────────────────────────────────────────

def _cwd_key(cwd: str | None = None) -> str:
    """Stable, filesystem-safe key for a working directory."""
    p = os.path.abspath(cwd or os.getcwd())
    # Normalise case on Windows so C:\X and c:\x map to the same memory.
    if os.name == "nt":
        p = p.lower()
    return hashlib.sha1(p.encode("utf-8")).hexdigest()[:16]


def _cwd_path(cwd: str | None = None) -> Path:
    _BY_DIR.mkdir(parents=True, exist_ok=True)
    return _BY_DIR / f"{_cwd_key(cwd)}.jsonl"


def save_cwd(messages: list[dict], cwd: str | None = None, max_turns: int = 200) -> str:
    """Persist conversation for the current directory (rolling, capped)."""
    path = _cwd_path(cwd)
    # Keep the tail so the file never grows without bound.
    kept = [m for m in messages if m.get("role") != "system"][-max_turns * 4:]
    # Record which directory this belongs to (first line metadata), for /sessions display.
    with open(path, "w", encoding="utf-8") as f:
        f.write(json.dumps({"_meta": True, "cwd": os.path.abspath(cwd or os.getcwd()),
                            "saved": datetime.now().isoformat(timespec="seconds")}) + "\n")
        for m in kept:
            f.write(json.dumps(m, ensure_ascii=False) + "\n")
    return str(path)


def load_cwd(cwd: str | None = None) -> list[dict]:
    """Return saved messages for the current directory (excluding the _meta line)."""
    path = _cwd_path(cwd)
    if not path.exists():
        return []
    return [m for m in _read(path) if not m.get("_meta")]


def clear_cwd(cwd: str | None = None) -> bool:
    """Forget the current directory's rolling memory. Returns True if something was removed."""
    path = _cwd_path(cwd)
    if path.exists():
        try:
            path.unlink()
            return True
        except Exception:
            return False
    return False


def save(messages: list[dict], name: str = "") -> str:
    """Persist conversation messages to disk.  Returns the file path."""
    d = _ensure_dir()
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    fname = f"{name}_{ts}.jsonl" if name else f"session_{ts}.jsonl"
    path = d / fname
    with open(path, "w", encoding="utf-8") as f:
        for m in messages:
            if m.get("role") == "system":
                continue
            f.write(json.dumps(m, ensure_ascii=False) + "\n")
    return str(path)


def load_last() -> list[dict] | None:
    """Return messages from the most-recent session file, or None."""
    d = _ensure_dir()
    files = sorted(d.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not files:
        return None
    return _read(files[0])


def load_file(path: str) -> list[dict]:
    return _read(Path(path))


def list_sessions(limit: int = 10) -> list[tuple[str, str, int]]:
    """Return (filename, mtime-string, turn-count) for recent sessions."""
    d = _ensure_dir()
    files = sorted(d.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)[:limit]
    out = []
    for p in files:
        msgs = _read(p)
        turns = sum(1 for m in msgs if m.get("role") == "user")
        mtime = datetime.fromtimestamp(p.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
        out.append((p.name, mtime, turns))
    return out


def _read(path: Path) -> list[dict]:
    msgs = []
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    msgs.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return msgs

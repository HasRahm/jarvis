"""Central debug-trace sink.

All `[TRACE]` instrumentation across the codebase routes through `trace()` instead of
raw `print(..., file=sys.stderr)`. This keeps the interactive REPL/console clean by
default — tracing is OFF unless explicitly enabled, and even when enabled it writes to a
log file rather than flooding the terminal.

Control via environment:
  JARVIS_TRACE=1          -> enable tracing (writes to logs/jarvis_trace.log)
  JARVIS_TRACE_CONSOLE=1  -> also echo each trace line to the real stderr
                             (use when you redirect stderr to a file on launch)

Default (neither set): trace() is a cheap no-op. stdlib-only, import-safe everywhere.
"""

import os
import sys
import threading

_ENABLED = os.environ.get("JARVIS_TRACE") == "1"
_CONSOLE = os.environ.get("JARVIS_TRACE_CONSOLE") == "1"
_LOCK = threading.Lock()
_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs", "jarvis_trace.log")
_fh = None


def is_enabled() -> bool:
    return _ENABLED


def _ensure_fh():
    global _fh
    if _fh is None:
        os.makedirs(os.path.dirname(_PATH), exist_ok=True)
        _fh = open(_PATH, "a", encoding="utf-8")
    return _fh


def trace(msg: str) -> None:
    """Write one already-formatted trace line (e.g. '[TRACE] mod.func: enter').

    No-op unless JARVIS_TRACE=1. Never raises — instrumentation must not break callers."""
    if not _ENABLED:
        return
    try:
        with _LOCK:
            fh = _ensure_fh()
            fh.write(msg + "\n")
            fh.flush()
            if _CONSOLE and sys.__stderr__ is not None:
                sys.__stderr__.write(msg + "\n")
                sys.__stderr__.flush()
    except Exception:
        pass

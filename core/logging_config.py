"""
core/logging_config.py — Unified logging setup for all Jarvis services.

Call configure_logging(service_name) once at the top of each entry-point module.
Writes rotating log files to logs/<service>.log (10 MB per file, 5 backups).
Console output uses the same format. Set JARVIS_DEBUG=true for DEBUG level.
"""
import sys

import logging
import os
from logging.handlers import RotatingFileHandler

# Resolve project root (two levels up from this file: core/ -> jarvis/)
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_LOG_DIR = os.path.join(_PROJECT_ROOT, "logs")

_LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

_configured = set()  # guard against double-configuration in the same process


def configure_logging(service_name: str = "jarvis") -> None:
    """
    Configure the root logger with:
    - A StreamHandler (console) at INFO or DEBUG level
    - A RotatingFileHandler writing to logs/<service_name>.log
      (10 MB max, 5 backup files, UTF-8 encoded)

    Safe to call multiple times — subsequent calls for the same service_name
    are no-ops. Uses JARVIS_DEBUG env var to switch between INFO and DEBUG.
    """
    print(f"[TRACE] core.logging_config.configure_logging: enter", file=sys.stderr, flush=True)
    if service_name in _configured:
        return
    _configured.add(service_name)

    os.makedirs(_LOG_DIR, exist_ok=True)

    level = logging.DEBUG if os.getenv("JARVIS_DEBUG", "").lower() in ("1", "true", "yes") else logging.INFO
    formatter = logging.Formatter(_LOG_FORMAT, datefmt=_DATE_FORMAT)

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    console_handler.setLevel(level)

    # Rotating file handler — 10 MB per file, keep 5 backups
    log_path = os.path.join(_LOG_DIR, f"{service_name}.log")
    file_handler = RotatingFileHandler(
        log_path,
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(level)

    root = logging.getLogger()
    # Clear any existing handlers (e.g. from a prior basicConfig call)
    root.handlers.clear()
    root.setLevel(level)
    root.addHandler(console_handler)
    root.addHandler(file_handler)

    logging.getLogger(__name__).info(
        f"Logging configured: service={service_name} level={logging.getLevelName(level)} file={log_path}"
    )

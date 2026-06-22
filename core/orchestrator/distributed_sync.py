"""
Distributed Sync — Concurrency and access synchronization wrapper.

Provides a cross-platform file lock to prevent overlapping writes to the shared AGENTS.md.
"""
import sys
from core.trace import trace as _jtrace

import os
import time
import logging
from contextlib import contextmanager

logger = logging.getLogger(__name__)



@contextmanager
def agents_md_lock(lock_file_path: str = None):
    """
    A cross-platform file-based lock to prevent concurrent writes to AGENTS.md.
    Uses fcntl on Unix/Linux and msvcrt on Windows.
    """
    _jtrace(f"[TRACE] core.orchestrator.distributed_sync.agents_md_lock: enter")
    if lock_file_path is None:
        # Resolve to root-level AGENTS.md.lock
        lock_file_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
            "AGENTS.md.lock"
        )

    lock_file = None
    acquired = False
    try:
        lock_file = open(lock_file_path, "w")
        start_time = time.time()

        while not acquired:
            try:
                if os.name == 'nt':
                    import msvcrt
                    lock_file.seek(0)
                    msvcrt.locking(lock_file.fileno(), msvcrt.LK_NBLCK, 1)
                    acquired = True
                else:
                    import fcntl
                    fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    acquired = True
            except (IOError, OSError):
                _jtrace(f"[TRACE] core.orchestrator.distributed_sync.agents_md_lock: except ?")
                if time.time() - start_time > 10.0:
                    logger.warning("Still waiting to acquire file lock for AGENTS.md...")
                    start_time = time.time()
                time.sleep(0.1)

        yield

    finally:
        if lock_file:
            try:
                if acquired:
                    if os.name == 'nt':
                        import msvcrt
                        lock_file.seek(0)
                        msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)
                    else:
                        import fcntl
                        fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
            except Exception as e:
                _jtrace(f"[TRACE] core.orchestrator.distributed_sync.agents_md_lock: except {str(e)[:80]}")
                logger.warning(f"Error releasing file lock: {e}")
            lock_file.close()
            try:
                os.remove(lock_file_path)
            except Exception:
                _jtrace(f"[TRACE] core.orchestrator.distributed_sync.agents_md_lock: except Exception")
                pass

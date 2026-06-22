"""
core/cli/run_events.py — a tiny, thread-safe pub/sub bus for run telemetry.

Why a bus: the live execution graph must not care *how* an agent ran — as a
direct ``run_backend_agent`` tool call, or buried inside ``delegate_task``'s
DAG. Producers (agents, the orchestrator, the tool loop) ``emit`` events;
consumers (the CLI's GraphSession) ``subscribe``. Nothing is coupled, and a
headless run with no subscriber simply drops events on the floor.

Events are plain (name, payload) pairs. Conventional names — keep these stable:

    emit("plan_ready",    subtasks=[{"desc","agent"}, …])
    emit("agent_started", agent="backend", detail="writing app/auth.py")
    emit("agent_finished",agent="backend", detail="3 files  +191")
    emit("agent_failed",  agent="qa",      detail="2 tests failed")
    emit("tokens",        agent="backend", tokens=12400)   # delta or absolute
    emit("shipped",       summary=["✓ Shipped — …", "◆ Indexed …"])

Delivery is synchronous on the caller's thread; handlers are wrapped so one
bad subscriber can never break a producer (or another subscriber).
"""

from __future__ import annotations
import sys
from core.trace import trace as _jtrace

import os
import threading
from typing import Callable

# A handler takes (event_name, payload_dict).
Handler = Callable[[str, dict], None]

_subscribers: "list[Handler]" = []
_lock = threading.RLock()
_DEBUG = os.environ.get("JARVIS_EVENTS_DEBUG") == "1"


def subscribe(handler: Handler) -> Callable[[], None]:
    """Register a handler. Returns a zero-arg unsubscribe function."""
    _jtrace(f"[TRACE] core.cli.run_events.subscribe: enter")
    with _lock:
        _subscribers.append(handler)

    def _unsub() -> None:
        unsubscribe(handler)

    return _unsub


def unsubscribe(handler: Handler) -> None:
    with _lock:
        try:
            _subscribers.remove(handler)
        except ValueError:
            _jtrace(f"[TRACE] core.cli.run_events.unsubscribe: except ValueError")
            pass


def emit(event: str, **payload) -> None:
    """Publish an event to every subscriber. Never raises."""
    _jtrace(f"[TRACE] core.cli.run_events.emit: enter")
    with _lock:
        targets = list(_subscribers)
    if _DEBUG:
        try:
            print(f"[events] {event} {payload}")
        except Exception:
            _jtrace(f"[TRACE] core.cli.run_events.emit: except Exception")
            pass
    for handler in targets:
        try:
            handler(event, payload)
        except Exception:
            # A subscriber's failure must never propagate into the producer.
            _jtrace(f"[TRACE] core.cli.run_events.emit: except Exception")
            if _DEBUG:
                import traceback
                traceback.print_exc()


def clear() -> None:
    """Drop all subscribers (use in tests)."""
    with _lock:
        _subscribers.clear()

"""
core/cli/demo_graph.py — standalone smoke test for the live execution graph.

Run it WITHOUT the orchestrator to see exactly what a real build will look
like, and to verify rendering / animation / encoding on your terminal:

    python -m core.cli.demo_graph

It drives the renderer through a realistic timeline by emitting the same
run-events the real agents will emit, so it exercises the full GraphSession
path (bus → controller → renderer → Live), not a private shortcut.
"""

from __future__ import annotations
import sys
from core.trace import trace as _jtrace

import time
from rich.console import Console

from core.cli import run_events as ev
from core.cli.live_graph import GraphSession

TASK = "Build a SaaS REST API with JWT auth and user management"

SUBTASKS = [
    {"desc": "Design users schema + JWT auth endpoints", "agent": "backend"},
    {"desc": "Build login & dashboard UI on the API",     "agent": "frontend"},
    {"desc": "Containerise + prepare deploy config",       "agent": "iac"},
    {"desc": "Verify contracts + integration tests",       "agent": "qa"},
]


def main() -> None:
    _jtrace(f"[TRACE] core.cli.demo_graph.main: enter")
    console = Console()
    with GraphSession(console, TASK):
        time.sleep(1.0)
        ev.emit("plan_ready", subtasks=SUBTASKS)
        ev.emit("tokens", agent="planner", tokens=5210)
        time.sleep(1.2)

        ev.emit("agent_started", agent="backend", detail="writing app/auth.py")
        time.sleep(2.0)
        ev.emit("agent_finished", agent="backend", detail="3 files  +191")
        ev.emit("tokens", agent="backend", tokens=7200)

        ev.emit("agent_started", agent="frontend", detail="writing web/dashboard.html")
        ev.emit("agent_started", agent="iac", detail="writing Dockerfile")
        time.sleep(1.8)
        ev.emit("agent_finished", agent="frontend", detail="3 files  +310")
        ev.emit("tokens", agent="frontend", tokens=6500)
        time.sleep(1.0)
        ev.emit("agent_finished", agent="iac", detail="2 files  +46")
        ev.emit("tokens", agent="iac", tokens=2400)

        ev.emit("agent_started", agent="qa", detail="running 12 integration tests")
        time.sleep(2.0)
        ev.emit("agent_finished", agent="qa", detail="12 passed · contracts honoured")
        ev.emit("tokens", agent="qa", tokens=4500)

        time.sleep(0.6)
        ev.emit("shipped", summary=[
            "✓ Shipped — 9 files · 4 agents · 25,800 tokens",
            "◆ Indexed 6 API contracts → memory.gbrain",
        ])
        time.sleep(1.5)


if __name__ == "__main__":
    main()

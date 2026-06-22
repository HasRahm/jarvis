"""
core/cli/graph_renderer.py — Jarvis live execution-graph renderer.

A production rewrite of the original ExecutionGraphRenderer. It draws the
warm "Claude-style" execution tree the design mocks up:

    🔴 🟡 🟢   jarvis — ~/projects/foo — zsh           • hermes · online
    $ jarvis run "Build a SaaS REST API …"

    ◆ JARVIS  v2.0
    multi-agent orchestrator · planner → agents → qa

    ✓ Plan ready — 4 subtasks across 4 agents
       01  Design users schema + JWT auth endpoints   backend
       …
    execution graph
      you                  ✓  ready
       ↳▶ planner          ✓  4 subtasks mapped
          ├─▶ backend      ✓  3 files  +191
          ├─▶ frontend     ⠹  writing web/dashboard.html
          ├─▶ iac          ·  queued
          └─▶ qa           ·  queued
              └─▶ shipped  ·
    ⠹ orchestrating · 12,400 tokens · $0.0021          4.5s · esc interrupt

Design goals:
  * Animates on its own. Implements ``__rich__`` so a ``rich.live.Live`` re-renders
    it every refresh — spinners spin and the clock ticks with no external driver.
  * Thread-safe. State mutations and renders are guarded by a lock, so agent
    worker threads can update it while Live reads it.
  * Encoding-safe. Falls back to ASCII glyphs on a non-UTF-8 console (legacy
    Windows cp1252) instead of raising UnicodeEncodeError.
  * Pure view. Holds no orchestration logic — it is fed state via simple methods
    (see live_graph.GraphSession / run_events for the wiring).

Backwards-compatible: the original method names ``update_plan``,
``set_agent_status`` and ``set_metrics`` are retained as thin aliases.
"""

from __future__ import annotations

import os
import sys
from core.trace import trace as _jtrace
import time
import threading
from dataclasses import dataclass, field
from enum import Enum
from typing import Iterable

from rich.console import Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text


# ── palette (warm ivory / clay, matches the design system) ───────────────────
class Palette:
    CLAY = "#E08A5F"   # accent — running / command / brand
    NODE = "#E9E1D4"   # active node label
    DIM = "#9A9081"    # secondary text
    FAINT = "#615A50"  # pending / chrome
    OK = "#9DBE92"     # done
    FAIL = "#C77E68"   # failed
    AMBER = "#D8AB5E"  # plan tags


# ── glyphs, with an ASCII fallback for non-unicode consoles ──────────────────
def _supports_unicode() -> bool:
    _jtrace(f"[TRACE] core.cli.graph_renderer._supports_unicode: enter")
    enc = (getattr(sys.stdout, "encoding", "") or "").lower()
    return "utf" in enc or os.environ.get("JARVIS_FORCE_UNICODE") == "1"


_UNICODE = _supports_unicode()

if _UNICODE:
    SPINNER = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
    G_DONE, G_FAIL, G_PEND = "✓", "✗", "·"
    DOTS = "🔴 🟡 🟢"
    DIAMOND, BRAND_ARROW = "◆", "→"
    BR_MID, BR_LAST, BR_PLAN = "├─▶ ", "└─▶ ", "↳▶ "
else:                                   # legacy cp1252 / ascii terminals
    SPINNER = "|/-\\"
    G_DONE, G_FAIL, G_PEND = "v", "x", "."
    DOTS = "( ) ( ) ( )"
    DIAMOND, BRAND_ARROW = "*", "->"
    BR_MID, BR_LAST, BR_PLAN = "|-> ", "`-> ", "|> "


class NodeState(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


@dataclass
class _Node:
    label: str
    state: NodeState = NodeState.PENDING
    detail: str = "queued"


@dataclass
class ExecutionGraphRenderer:
    """Live view of one Jarvis build. Mutate via the methods; render via Rich."""

    command: str
    project: str | None = None
    subtasks: list[dict] = field(default_factory=list)

    def __post_init__(self) -> None:
        self._lock = threading.RLock()
        self.start_time = time.time()
        self.tokens = 0
        self.cost = 0.0
        self.status_label = "orchestrating"
        self.finished = False
        self.plan_ready = False
        self.planner = _Node("planner", NodeState.RUNNING, "thinking…")
        # ordered agent nodes — insertion order is render order
        self.agents: "dict[str, _Node]" = {}
        self.summary: list[str] = []
        if self.project is None:
            try:
                self.project = f"~/{os.path.basename(os.getcwd())}"
            except Exception:
                _jtrace(f"[TRACE] core.cli.graph_renderer.ExecutionGraphRenderer.__post_init__: except Exception")
                self.project = "~"

    # ── state transitions ────────────────────────────────────────────────────
    def planner_running(self, detail: str = "thinking…") -> None:
        with self._lock:
            self.planner.state = NodeState.RUNNING
            self.planner.detail = detail

    def plan(self, subtasks: Iterable[dict]) -> None:
        """Seed the plan. ``subtasks`` = [{"desc": str, "agent": str}, …]."""
        with self._lock:
            self.subtasks = list(subtasks)
            self.plan_ready = True
            self.planner.state = NodeState.DONE
            self.planner.detail = f"{len(self.subtasks)} subtasks mapped"
            for t in self.subtasks:
                agent = (t.get("agent") or "agent").strip()
                self.agents.setdefault(agent, _Node(agent))

    def agent_running(self, agent: str, detail: str = "working…") -> None:
        with self._lock:
            node = self.agents.setdefault(agent, _Node(agent))
            node.state = NodeState.RUNNING
            node.detail = detail

    def agent_done(self, agent: str, detail: str = "done") -> None:
        with self._lock:
            node = self.agents.setdefault(agent, _Node(agent))
            node.state = NodeState.DONE
            node.detail = detail

    def agent_failed(self, agent: str, detail: str = "failed") -> None:
        with self._lock:
            node = self.agents.setdefault(agent, _Node(agent))
            node.state = NodeState.FAILED
            node.detail = detail

    def metrics(self, tokens: int, cost: float) -> None:
        with self._lock:
            self.tokens = int(tokens)
            self.cost = float(cost)

    def finish(self, summary: list[str] | None = None,
               status_label: str = "idle") -> None:
        with self._lock:
            self.finished = True
            self.status_label = status_label
            if summary:
                self.summary = list(summary)

    # ── backwards-compatible aliases (original API) ───────────────────────────
    def update_plan(self, subtasks):                 # noqa: D401  (legacy name)
        self.plan(subtasks)

    def set_agent_status(self, agent: str, status: str):
        """Legacy: status string doubled as state+detail. Map it sensibly."""
        _jtrace(f"[TRACE] core.cli.graph_renderer.ExecutionGraphRenderer.set_agent_status: enter")
        s = (status or "").lower()
        if s in ("queued", "pending"):
            with self._lock:
                self.agents.setdefault(agent, _Node(agent))
        elif s in ("done", "shipped", "passed", "complete"):
            self.agent_done(agent, status)
        elif s in ("failed", "error", "suspended"):
            self.agent_failed(agent, status)
        else:
            self.agent_running(agent, status)

    def set_metrics(self, tokens: int, cost: float):
        self.metrics(tokens, cost)

    # ── helpers ───────────────────────────────────────────────────────────────
    def _spin(self) -> str:
        _jtrace(f"[TRACE] core.cli.graph_renderer.ExecutionGraphRenderer._spin: enter")
        idx = int((time.time() - self.start_time) * 12) % len(SPINNER)
        return SPINNER[idx]

    def _icon(self, state: NodeState):
        _jtrace(f"[TRACE] core.cli.graph_renderer.ExecutionGraphRenderer._icon: enter")
        if state is NodeState.DONE:
            return Text(G_DONE, style=Palette.OK)
        if state is NodeState.FAILED:
            return Text(G_FAIL, style=Palette.FAIL)
        if state is NodeState.RUNNING:
            return Text(self._spin(), style=Palette.CLAY)
        return Text(G_PEND, style=Palette.FAINT)

    def _node_styles(self, state: NodeState):
        _jtrace(f"[TRACE] core.cli.graph_renderer.ExecutionGraphRenderer._node_styles: enter")
        if state is NodeState.PENDING:
            return Palette.FAINT, Palette.FAINT
        if state is NodeState.RUNNING:
            return Palette.NODE, Palette.CLAY
        if state is NodeState.FAILED:
            return Palette.NODE, Palette.FAIL
        return Palette.NODE, Palette.DIM

    # ── render ────────────────────────────────────────────────────────────────
    def render(self) -> Panel:
        with self._lock:
            return self._render_locked()

    def __rich__(self):
        # Lets `Live(graph)` re-render every refresh → spinners + clock animate.
        return self.render()

    def _render_locked(self) -> Panel:
        _jtrace(f"[TRACE] core.cli.graph_renderer.ExecutionGraphRenderer._render_locked: enter")
        elements: list = []

        # 1. window chrome
        elements.append(Text(
            f"{DOTS}    jarvis  —  {self.project}  —  zsh        • hermes · online",
            style=Palette.FAINT,
        ))

        # 2. command echo
        cmd = Text("\n$ ", style=Palette.CLAY)
        cmd.append("jarvis run ", style=Palette.DIM)
        cmd.append(f'"{self.command}"\n', style=Palette.NODE)
        elements.append(cmd)

        # 3. banner
        banner = Text()
        banner.append(f"{DIAMOND} JARVIS", style=f"bold {Palette.CLAY}")
        banner.append("  v2.0\n", style=Palette.FAINT)
        banner.append(
            f"multi-agent orchestrator · planner {BRAND_ARROW} agents {BRAND_ARROW} qa",
            style=Palette.DIM,
        )
        elements.append(banner)

        # 4. plan
        if self.plan_ready and self.subtasks:
            n_agents = len({t.get("agent", "") for t in self.subtasks})
            elements.append(Text(
                f"\n{G_DONE} Plan ready — {len(self.subtasks)} subtasks across {n_agents} agents",
                style=f"bold {Palette.NODE}",
            ))
            plan_tbl = Table(show_header=False, box=None, padding=(0, 2))
            plan_tbl.add_column(width=4)
            plan_tbl.add_column()
            plan_tbl.add_column()
            for i, t in enumerate(self.subtasks):
                plan_tbl.add_row(
                    Text(f"  {i + 1:02d}", style=Palette.FAINT),
                    Text(t.get("desc", ""), style=Palette.DIM),
                    Text(t.get("agent", ""), style=Palette.AMBER),
                )
            elements.append(plan_tbl)

        # 5. execution tree
        elements.append(Text("\nexecution graph", style=Palette.FAINT))
        tree = Table(show_header=False, box=None, padding=(0, 2))
        tree.add_column(width=26)
        tree.add_column(width=2)
        tree.add_column()

        def row(prefix: str, label: str, state: NodeState, detail: str):
            _jtrace(f"[TRACE] core.cli.graph_renderer.ExecutionGraphRenderer._render_locked.row: enter")
            name_style, det_style = self._node_styles(state)
            line = Text(prefix, style=Palette.FAINT)
            line.append(label, style=f"bold {name_style}")
            tree.add_row(line, self._icon(state), Text(detail, style=det_style))

        row("", "you", NodeState.DONE, "ready")
        row(f"  {BR_PLAN}", "planner", self.planner.state, self.planner.detail)

        agents = list(self.agents.values())
        for i, node in enumerate(agents):
            last = i == len(agents) - 1
            row(f"     {BR_LAST if last else BR_MID}", node.label, node.state, node.detail)

        # shipped node — done only when every agent finished cleanly
        all_done = bool(agents) and all(n.state is NodeState.DONE for n in agents)
        any_fail = any(n.state is NodeState.FAILED for n in agents)
        ship_state = (NodeState.FAILED if any_fail else
                      NodeState.DONE if (all_done and self.finished) else NodeState.PENDING)
        row(f"         {BR_LAST}", "shipped", ship_state, "" if ship_state is NodeState.PENDING else
            ("blocked" if any_fail else "verified"))

        elements.append(tree)

        # 6. summary (after a finished build) — sits between tree and footer
        if self.finished and self.summary:
            for ln in self.summary:
                elements.append(Text(ln, style=Palette.OK if ln.startswith(G_DONE) else Palette.CLAY))

        # 7. footer
        elapsed = time.time() - self.start_time
        spin = self._spin() if not self.finished else G_DONE
        spin_style = Palette.CLAY if not self.finished else Palette.OK
        left = Text(f"\n{spin} ", style=spin_style)
        left.append(self.status_label, style=Palette.DIM)
        left.append(f" · {self.tokens:,} tokens · ", style=Palette.FAINT)
        left.append(f"${self.cost:.4f}", style=Palette.CLAY)

        right_txt = (f"{elapsed:.1f}s · esc interrupt" if not self.finished
                     else "↵ run · /help · ↑ recall")
        footer = Table.grid(expand=True)
        footer.add_column(justify="left")
        footer.add_column(justify="right")
        footer.add_row(left, Text(right_txt + " ", style=Palette.FAINT))

        elements.append(footer)

        return Panel(Group(*elements), border_style=Palette.FAINT, padding=(1, 2))

"""
core/cli/live_graph.py — the controller that turns run-events into a live,
animated execution graph in the terminal.

Usage (decoupled / recommended) — agents emit events on the bus, this just
listens and renders:

    from core.cli.live_graph import GraphSession

    with GraphSession(self.console, task) as g:
        run_the_agent_loop(...)        # agents call run_events.emit(...)
    # graph finalises + prints the summary on exit

Usage (direct / zero-instrumentation fallback) — drive it from the tool loop:

    with GraphSession(self.console, task) as g:
        g.graph.planner_running()
        g.graph.plan(subtasks)
        g.graph.agent_running("backend", "writing app/auth.py")
        ...
        g.add_tokens("backend", 12400)

Both styles can be mixed. The session is safe on a non-TTY (CI, piped output):
it degrades to terse line prints instead of a live region.
"""

from __future__ import annotations
import sys

import os
from rich.console import Console
from rich.live import Live

from core.cli import run_events
from core.cli.graph_renderer import ExecutionGraphRenderer, G_DONE, DIAMOND


# Blended $/1M-token estimates (input+output averaged) for cost display.
# Source of truth is config/agent_models.json + the OpenRouter catalog; this is
# a safe fallback so the footer always shows *something* sane.
_PRICE_PER_MTOK = {
    "claude-opus": 30.0, "claude-sonnet": 6.0, "claude": 6.0,
    "gpt-5": 5.0, "gpt-oss": 0.3, "gpt": 5.0,
    "gemini-3": 3.5, "gemini-2.5-pro": 3.5, "gemini": 1.5,
    "kimi": 0.6, "minimax": 0.5, "nemotron": 0.4,
    "gemma": 0.0,            # local / cloud-free default
}
_DEFAULT_PRICE = 1.0


def estimate_cost(tokens: int, model: str | None = None) -> float:
    """Rough USD cost for a token count under the active model."""
    print(f"[TRACE] core.cli.live_graph.estimate_cost: enter", file=sys.stderr, flush=True)
    m = (model or os.environ.get("JARVIS_PRIMARY_MODEL", "gemma")).lower()
    price = next((p for key, p in _PRICE_PER_MTOK.items() if key in m), _DEFAULT_PRICE)
    return tokens / 1_000_000 * price


class GraphSession:
    """Owns an ExecutionGraphRenderer, a Live region, and a bus subscription."""

    def __init__(self, console: Console, task: str, project: str | None = None,
                 model: str | None = None, enabled: bool | None = None):
        self.console = console
        self.graph = ExecutionGraphRenderer(task, project)
        self.model = model or os.environ.get("JARVIS_PRIMARY_MODEL")
        # Live only makes sense on a real terminal; otherwise print plainly.
        self.enabled = console.is_terminal if enabled is None else enabled
        self._live: Live | None = None
        self._unsub = None
        self._tokens_by_agent: dict[str, int] = {}

    # ── lifecycle ─────────────────────────────────────────────────────────────
    def __enter__(self) -> "GraphSession":
        self._unsub = run_events.subscribe(self._on_event)
        if self.enabled:
            self._live = Live(self.graph, console=self.console,
                              refresh_per_second=12, transient=False,
                              vertical_overflow="visible")
            self._live.__enter__()
        else:
            self.console.print(f'[dim]$ jarvis run "{self.graph.command}"[/]')
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        if not self.graph.finished:
            self.graph.finish()
        if self._live is not None:
            self._live.update(self.graph.render())   # final frame
            self._live.__exit__(exc_type, exc, tb)
            self._live = None
        elif self.graph.summary:
            for ln in self.graph.summary:
                self.console.print(ln)
        if self._unsub:
            self._unsub()
            self._unsub = None
        return False   # never swallow exceptions

    # ── token / cost accounting ───────────────────────────────────────────────
    def add_tokens(self, agent: str, tokens: int, absolute: bool = False) -> None:
        """Record tokens for an agent (delta by default) and refresh cost."""
        print(f"[TRACE] core.cli.live_graph.GraphSession.add_tokens: enter", file=sys.stderr, flush=True)
        if absolute:
            self._tokens_by_agent[agent] = int(tokens)
        else:
            self._tokens_by_agent[agent] = self._tokens_by_agent.get(agent, 0) + int(tokens)
        total = sum(self._tokens_by_agent.values())
        self.graph.metrics(total, estimate_cost(total, self.model))

    # ── bus handler ────────────────────────────────────────────────────────────
    def _on_event(self, event: str, p: dict) -> None:
        try:
            if event == "plan_ready":
                self.graph.plan(p.get("subtasks", []))
            elif event == "planner_running":
                self.graph.planner_running(p.get("detail", "thinking…"))
            elif event == "agent_started":
                self.graph.agent_running(p["agent"], p.get("detail", "working…"))
            elif event == "agent_finished":
                self.graph.agent_done(p["agent"], p.get("detail", "done"))
            elif event == "agent_failed":
                self.graph.agent_failed(p["agent"], p.get("detail", "failed"))
            elif event == "tokens":
                self.add_tokens(p.get("agent", "_"), p.get("tokens", 0),
                                absolute=p.get("absolute", False))
            elif event == "shipped":
                self.finish(p.get("summary"))
        except Exception:
            # Rendering must never crash a run.
            print(f"[TRACE] core.cli.live_graph.GraphSession._on_event: except Exception", file=sys.stderr, flush=True)
            pass

    # ── convenience finish ─────────────────────────────────────────────────────
    def finish(self, summary: list[str] | None = None) -> None:
        print(f"[TRACE] core.cli.live_graph.GraphSession.finish: enter", file=sys.stderr, flush=True)
        if summary is None:
            total = sum(self._tokens_by_agent.values())
            n_files = "?"  # callers can pass a richer summary
            summary = [
                f"{G_DONE} Shipped — {len(self.graph.agents)} agents · "
                f"{total:,} tokens · ${estimate_cost(total, self.model):.4f}",
                f"{DIAMOND} Indexed contracts → memory.gbrain",
            ]
        self.graph.finish(summary)

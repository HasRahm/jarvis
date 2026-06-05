import os
import sys
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.live import Live

console = Console()

def render_tool_call(name: str, args: dict):
    """Render a tool call block in a yellow panel."""
    # Convert args to clean string
    args_str = ", ".join(f"{k}={repr(v)}" for k, v in args.items()) if isinstance(args, dict) else str(args)
    text = Text.from_markup(f"[bold yellow]Executing:[/] [bold]{name}[/]({args_str})")
    console.print(
        Panel(
            text,
            title="[bold yellow]▶ TOOL CALL[/]",
            border_style="yellow",
            padding=(0, 1)
        )
    )

def render_tool_result(name: str, result: str):
    """Render a tool execution result in a green panel."""
    res_str = str(result)
    summary = res_str[:300] + ("..." if len(res_str) > 300 else "")
    text = Text.from_markup(f"[bold green]Result of:[/] {name}\n[dim]{summary}[/]")
    console.print(
        Panel(
            text,
            title="[bold green]◀ TOOL RESULT[/]",
            border_style="green",
            padding=(0, 1)
        )
    )

def render_agent_dispatch(agent: str, model: str, task: str):
    """Render an agent task dispatch block in dynamic colors."""
    color = {
        "frontend": "blue",
        "backend": "orange1",
        "qa": "green",
        "iac": "magenta"
    }.get(agent.lower(), "white")
    
    text = Text.from_markup(f"[bold {color}]{agent.upper()}[/] [dim]({model})[/] dispatched with task:\n[italic]{task}[/]")
    console.print(
        Panel(
            text,
            title=f"[bold {color}]🤖 AGENT DISPATCH[/]",
            border_style=color,
            padding=(0, 1)
        )
    )

def render_agents_md_update(agent: str, status: str, step: str):
    """Log an AGENTS.md state update."""
    color = {
        "idle": "dim white",
        "working": "yellow",
        "done": "green",
        "passed": "bold green",
        "suspended": "red"
    }.get(status.lower(), "white")
    
    text = Text.from_markup(
        f"[dim]AGENTS.md[/] · [bold cyan]{agent}[/] status → [{color}]{status.upper()}[/] · {step}"
    )
    console.print(text)

def render_system_banner():
    """Print the welcome header banner."""
    table = Table(show_header=False, border_style="cyan")
    table.add_row(
        Text.from_markup(
            "[bold cyan]JARVIS // OPERATOR CONSOLE[/]\n"
            "[dim]Autonomous Agent System · Multi-Model DAG Routing · Local-First[/]"
        )
    )
    console.print(table)

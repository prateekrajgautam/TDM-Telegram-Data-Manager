"""
ui.py
-----
Rich-based progress dashboard (section 16). Kept intentionally simple
for Phase 2: a single progress bar plus a status line. Expand later
with a Live layout (current file / speed / ETA / recent log panel)
once the underlying download engine reports richer progress events.
"""

from __future__ import annotations

from rich.console import Console
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
)

console = Console()


def make_progress() -> Progress:
    return Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        TimeElapsedColumn(),
        console=console,
    )


def print_stats(stats: dict) -> None:
    console.print("\n[bold]Run summary[/bold]")
    for state, count in stats.get("by_state", {}).items():
        console.print(f"  {state}: {count}")
    total_mb = stats.get("total_downloaded_bytes", 0) / (1024 * 1024)
    console.print(f"  total downloaded: {total_mb:.1f} MB")

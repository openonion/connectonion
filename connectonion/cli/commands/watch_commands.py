"""Read-only CLI view of the Host watch declarations and delivery state."""

import json

import typer
from rich.console import Console

from ...network.host.watch import retry_event, watch_status
from ...project import project_co_dir

console = Console(soft_wrap=True)


def handle_list(as_json: bool) -> None:
    """Show what is watched and whether the latest event was handled."""
    try:
        rows = watch_status(project_co_dir())
    except (OSError, ValueError) as exc:
        console.print(f"[red]✗[/red] {exc}")
        raise typer.Exit(1) from exc
    if as_json:
        print(json.dumps({"watchers": rows}, indent=2))
        return
    if not rows:
        console.print("No watchers configured. Add watch: to .co/host.yaml.")
        return
    for row in rows:
        event = row["last_event"] or {}
        target = row["path"] or (f"every {row['every_seconds']}s" if row["every_seconds"] else "push")
        counts = f"  · {row['pending']} pending, {row['failed']} failed" if row["pending"] or row["failed"] else ""
        console.print(f"[bold]{row['name']}[/bold]  {row['source']} {target}  · "
                      f"{event.get('status', 'not yet fired')}{counts}")
        if event:
            console.print(f"  last: {event['observed_at']}  session: {event.get('session_id') or '-'}")
            if event.get("error"):
                console.print(f"  error: {event['error']}")
        for failed in row["failed_events"]:
            if failed["id"] != event.get("id"):
                console.print(f"  failed: {failed['id']}  {failed['error']}")


def handle_retry(event_id: str) -> None:
    """Put one failed event back on the durable queue."""
    if not retry_event(project_co_dir(), event_id):
        console.print(f"[red]✗[/red] No failed event with ID {event_id!r}. Run: co watch list --json")
        raise typer.Exit(1)
    console.print(f"[green]✓[/green] Event {event_id} is pending. The Host will retry it on its next poll.")

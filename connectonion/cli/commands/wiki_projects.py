"""`co wiki projects`: project pages from the user's own coding-session messages (#1943).

Kept out of wiki_commands.py on purpose: the group is added there in one
line, and everything it does lives here and in wiki/project_material.py and
wiki/project_pages.py.
"""

import typer

from .wiki_help import verbatim


def _day(stamp: str) -> str:
    return stamp[:10] if stamp else "unknown"


def _cost_line(estimate: dict, meter: dict) -> str:
    week = (f"; the Codex week is at {meter['used_percent']}%" if "used_percent" in meter
            else f"; {meter['unknown']}" if meter.get("unknown") else "")
    return (f"Cost: {estimate['model_calls']} model call(s) carrying about {estimate['chars']:,} characters "
            f"(~{estimate['tokens_estimated_in']:,} tokens) of skills, pages and messages; the runner re-reads "
            f"them each turn, so billed input is several times that{week}.")


def _mode(row: dict) -> str:
    return "update" if row["mode"] == "update" else "first write"


def _order_lines(rows: list[dict]) -> list[str]:
    return [f"  {row['record']}  (last active {_day(row['last_activity'])}, {row['new_messages']} "
            f"{'new ' if row['mode'] == 'update' else ''}messages, {_mode(row)}"
            + (f", {row['left_out']} older not sent" if row["left_out"] else "") + ")"
            for row in rows]


def _refresh(root, full: bool) -> dict:
    """Step 1, no model: file the user's new messages under their project pages."""
    from ...wiki.project_material import extract
    from ...wiki.service import subscriptions
    typer.echo("Wiki projects: reading your own messages in Codex and Claude Code sessions", err=True)
    report = extract(root, subscriptions(root), full=full)
    excluded = sum(report["excluded"].values())
    typer.echo(f"Wiki projects: {report['messages']} new messages from {report['files_read']} session files"
               + (f"; {excluded} typed in folders that are never projects" if excluded else "")
               + (f"; {len(report['unmapped'])} folders with messages have no project page"
                  if report["unmapped"] else ""), err=True)
    return report


NOTHING = "Every project page is written from all of your messages. Nothing to write."
NO_PAGES = "No project pages yet: the map makes them from your session folders."


def add_projects_app(wiki, factory, handle, logged) -> None:
    projects = factory(help="co wiki projects", no_args_is_help=False)
    projects.info.cls = verbatim("co wiki projects", projects.info.cls)
    wiki.add_typer(projects, name="projects")

    @projects.callback(invoke_without_command=True)
    def overview(ctx: typer.Context,
                 recent_days: int = typer.Option(14, "--recent-days", min=1),
                 full: bool = typer.Option(False, "--full")):
        if ctx.invoked_subcommand:
            return
        from ...wiki import quota
        from ...wiki.config import read_config
        from ...wiki.files import Notebook
        from ...wiki.project_pages import estimate, queue

        def operation(root):
            if not Notebook(root).list("projects"):
                return NO_PAGES, ["init"]
            report = _refresh(root, full)
            rows = queue(root, recent_days=recent_days)
            if not rows:
                return NOTHING, ["list", "projects"]
            cost = estimate(rows)
            if ctx.obj["json"]:
                return {"order": rows, "estimate": cost, "unmapped": report["unmapped"]}, ["projects", "write"]
            text = "\n".join([f"{cost['pages']} project pages to write; {cost['recent']} active in the last "
                              f"{recent_days} days come first:", *_order_lines(rows), "",
                              _cost_line(cost, quota.read(read_config(root))), "Nothing was spent."])
            return text, ["projects", "write"]
        handle(ctx, operation, ["projects"])

    @projects.command("write", cls=verbatim("co wiki projects write"))
    def write(ctx: typer.Context,
              limit: int = typer.Option(5, "--limit", min=0),
              recent_days: int = typer.Option(14, "--recent-days", min=1),
              full: bool = typer.Option(False, "--full")):
        from ...wiki import quota
        from ...wiki.config import read_config
        from ...wiki.files import Notebook
        from ...wiki.project_pages import estimate, queue, write_page, write_pages
        from ...wiki.service import run_logs

        def operation(root):
            if not Notebook(root).list("projects"):
                return NO_PAGES, ["init"]
            _refresh(root, full)
            rows = queue(root, recent_days=recent_days)
            chosen = rows if limit == 0 else rows[:limit]
            if not chosen:
                return NOTHING, ["list", "projects"]
            config = read_config(root)
            typer.echo(f"Writing {len(chosen)} of {len(rows)} project pages. "
                       + _cost_line(estimate(chosen), quota.read(config)), err=True)

            def gate():
                reading = quota.read(config)
                return quota.blocks(reading, quota.points_spent(run_logs(root), reading), config["limits"])

            def on_page(number, total, row):
                typer.echo(f"[{number}/{total}] {row['record']} ({_mode(row)}, "
                           f"last active {_day(row['last_activity'])})", err=True)

            def one(record):
                return logged(root, record, "projects write",
                              lambda update: write_page(root, record, config=config, progress=update))

            result = write_pages(root, limit=limit, recent_days=recent_days, write=one, gate=gate, on_page=on_page)
            if result.get("stopped"):
                typer.echo(f"Stopped: {result['stopped']}", err=True)
            accepted = [row["page"] for row in result["pages"] if row["outcome"] == "accepted"]
            return (result, ["show", accepted[0]] if accepted else ["logs"],
                    any(row["outcome"] != "accepted" for row in result["pages"]))
        handle(ctx, operation, ["projects"])

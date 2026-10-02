"""`co rem projects`: project pages from the user's own coding-session messages (#1943).

Kept out of rem_commands.py on purpose: the group is added there in one
line, and everything it does lives here and in rem/project_material.py and
rem/project_pages.py.
"""

import typer

from . import rem_look
from .rem_help import verbatim


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
    return [f"  {row['record']}  (last active {_day(row['last_activity'])}, "
            + _count(row['new_messages'], ('new ' if row['mode'] == 'update' else '') + 'message')
            + f", {_mode(row)}"
            + (f", {row['left_out']} older not sent" if row["left_out"] else "") + ")"
            for row in rows]


def _refresh(root, full: bool, recent_days: int) -> dict:
    """Step 1, no model: file the user's new messages under their project pages."""
    from ...rem.project_material import extract
    from ...rem.service import subscriptions
    rem_look.line("co rem projects: reading your own messages in Codex and Claude Code sessions", err=True)
    report = extract(root, subscriptions(root), full=full, recent_days=recent_days)
    excluded = sum(report["excluded"].values())
    workspace = report["workspace"]
    rem_look.line(f"co rem projects: "
               + f"{_count(report['messages'], 'new message')} from {_count(report['files_read'], 'session file')}"
               + (f"; {excluded} typed in folders that are never projects" if excluded else ""), err=True)
    if workspace["attributed"] or workspace["stayed_out"]:
        rem_look.line(f"co rem projects: {workspace['attributed']} typed in a workspace were filed under the "
                   f"repository they worked in ({workspace['folders']} folders); {workspace['stayed_out']} "
                   "stayed out, their sessions touched no repository", err=True)
    if report["created"]:
        rem_look.line(f"co rem projects: made {_count(len(report['created']), 'project page')} for folders active "
                   f"in the last {recent_days} days: " + ", ".join(report["created"]), err=True)
    return report


def _count(number: int, noun: str) -> str:
    return f"{number} {noun}{'' if number == 1 else 's'}"


def _left_line(report: dict, recent_days: int) -> list[str]:
    """Folders with messages and no page that were not given one: all older than the window."""
    left = len(report["unmapped"])
    return [f"{left} more {'folder' if left == 1 else 'folders'} with messages and no page; not created "
            f"(older than {recent_days} days)"] if left else []


NOTHING = "No new retained user input to write. Pages without usable evidence remain uninvestigated."
NO_PAGES = "No project pages yet: the map makes them from your session folders."


def add_projects_app(rem, factory, handle, logged) -> None:
    projects = factory(help="co rem projects", no_args_is_help=False)
    projects.info.cls = verbatim("co rem projects", projects.info.cls)
    rem.add_typer(projects, name="projects")

    @projects.callback(invoke_without_command=True)
    def overview(ctx: typer.Context,
                 recent_days: int = typer.Option(14, "--recent-days", min=1),
                 full: bool = typer.Option(False, "--full")):
        if ctx.invoked_subcommand:
            return
        from ...rem import quota
        from ...rem.config import read_config
        from ...rem.files import Notebook
        from ...rem.project_pages import estimate, queue

        def operation(root):
            if not Notebook(root).list("projects"):
                return NO_PAGES, ["init"]
            report = _refresh(root, full, recent_days)
            rows = queue(root, recent_days=recent_days)
            if ctx.obj["json"]:
                return ({"order": rows, "estimate": estimate(rows), "workspace": report["workspace"],
                         "created": report["created"], "unmapped": report["unmapped"]},
                        ["projects", "write"] if rows else ["list", "projects"])
            if not rows:
                return "\n".join([NOTHING, *_left_line(report, recent_days)]), ["list", "projects"]
            cost = estimate(rows)
            text = "\n".join([f"{cost['pages']} project pages to write; {cost['recent']} active in the last "
                              f"{recent_days} days come first:", *_order_lines(rows), "",
                              *_left_line(report, recent_days),
                              _cost_line(cost, quota.read(read_config(root))), "Nothing was spent."])
            return text, ["projects", "write"]
        handle(ctx, operation, ["projects"])

    @projects.command("write", cls=verbatim("co rem projects write"))
    def write(ctx: typer.Context,
              limit: int = typer.Option(5, "--limit", min=0),
              recent_days: int = typer.Option(14, "--recent-days", min=1),
              full: bool = typer.Option(False, "--full")):
        from ...rem import quota
        from ...rem.config import read_config
        from ...rem.files import Notebook
        from ...rem.project_pages import estimate, queue, write_page, write_pages
        from ...rem.service import run_logs

        def operation(root):
            if not Notebook(root).list("projects"):
                return NO_PAGES, ["init"]
            _refresh(root, full, recent_days)
            rows = queue(root, recent_days=recent_days)
            chosen = rows if limit == 0 else rows[:limit]
            if not chosen:
                return NOTHING, ["list", "projects"]
            config = read_config(root)
            from ...rem import first_run
            from ...rem.runner import PLAN
            total = first_run.plan(run_logs(root), owner=False, people=0, projects=len(chosen))
            rem_look.line(f"Writing {len(chosen)} of {_count(len(rows), 'project page')}. "
                          + first_run.announce(total, PLAN.get(config["runner"], "on the configured runner"))
                          + " " + _cost_line(estimate(chosen), quota.read(config)), err=True)

            def gate():
                reading = quota.read(config)
                return quota.blocks(reading, quota.points_spent(run_logs(root), reading), config["limits"])

            def on_page(number, total, row):
                rem_look.line(f"[{number}/{total}] {row['record']} ({_mode(row)}, "
                           f"last active {_day(row['last_activity'])})", err=True)

            def one(record):
                return logged(root, record, "projects write",
                              lambda update: write_page(root, record, config=config, progress=update))

            result = write_pages(root, limit=limit, recent_days=recent_days, write=one, gate=gate, on_page=on_page)
            accepted = [row["page"] for row in result["pages"] if row["outcome"] == "accepted"]
            return ((result if ctx.obj["json"] else written_summary(result)),
                    ["show", accepted[0]] if accepted else ["logs"],
                    any(row["outcome"] != "accepted" for row in result["pages"]))
        handle(ctx, operation, ["projects"], resume=["projects", "write"])


def written_summary(result: dict) -> str:
    """`projects write`'s last word: a line per page and what is left (#2008).

    1.9.0a5 ended with the result dict dumped as YAML (pages:, mode:, outcome:).
    """
    lines = [f"  {row['page']}: " + ("written" if row["outcome"] == "accepted" else
                                     f"{row['outcome']} ({str(row.get('why', ''))[:160]})")
             for row in result["pages"]]
    accepted = sum(row["outcome"] == "accepted" for row in result["pages"])
    head = f"Wrote {_count(accepted, 'project page')} of {len(result['pages'])}."
    tail = [f"Stopped before the rest: {result['stopped']}."] if result.get("stopped") else []
    left = [f"{_count(result['left'], 'project page')} left to write."] if result.get("left") else []
    return "\n".join([head, *lines, *tail, *left])

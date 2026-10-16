"""`co rem import`: notebook imports and optional model summaries."""

import typer

from .rem_help import show, verbatim


def add_import_app(rem, factory, handle) -> None:
    imports = factory(help="co rem import", no_args_is_help=False)
    imports.info.cls = verbatim("co rem import", imports.info.cls)
    rem.add_typer(imports, name="import")

    @imports.callback(invoke_without_command=True)
    def overview(ctx: typer.Context):
        if ctx.invoked_subcommand is None:
            show("co rem import")

    @imports.command("sessions", cls=verbatim("co rem import sessions"))
    def sessions(ctx: typer.Context,
                 days: int = typer.Option(180, "--days", min=1),
                 summarise: bool = typer.Option(False, "--summarise"),
                 limit: int = typer.Option(40, "--limit", min=1),
                 json_out: bool = typer.Option(False, "--json")):
        from ...rem.sessions import import_sessions, summarise_line, summarise_sessions, summary
        ctx.obj["json"] = ctx.obj["json"] or json_out

        def operation(root):
            report = import_sessions(root, days=days)
            reasons = ", ".join(f"{reason}: {count}" for reason, count in sorted(report["skipped"].items()))
            text = summary(report)
            if summarise:
                report["summary"] = summarise_sessions(root, limit=limit)
                text += "\n" + summarise_line(report["summary"])
            text += "\nSkipped: " + reasons if reasons else ""
            return (report if ctx.obj["json"] else text), ["list", "sessions"]
        handle(ctx, operation, ["import", "sessions"])

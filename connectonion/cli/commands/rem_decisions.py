"""The decisions status and write commands, and their compatibility alias."""

from typing import Optional

import typer

from .rem_help import verbatim


def _round_lines(number, row):
    lines = [f"Round {number}: {row['read']} decisions read · {len(row['changed'])} pages written · {len(row['refused'])} refused"]
    lines += [f"  refused {refusal['record']}: " + "; ".join(refusal["errors"]) for refusal in row["refused"]]
    return "\n".join(lines)


def _summary(value):
    ending = f"{value['left']} decisions left"
    if value["reason"]:
        stop = (f"round {len(value['rounds'])} " + ("failed" if value['rounds'][-1]['changed'] else "wrote no page")
                if value["rounds"] else "before round 1")
        ending = f"stopped: {stop} · {ending}"
    return f"Done: {len(value['rounds'])} rounds · {value['written']} pages written · {value['refused']} refused · {ending}"


def write_decisions(ctx, rounds, handle, written):
    from ...rem.decisions import write
    report = {}

    def progress(number, row):
        written.extend(row["changed"])
        if not ctx.obj["json"]:
            typer.echo(_round_lines(number, row))

    def operation(root):
        report.update(write(root, rounds=rounds, progress=progress))
        return report, ["list", "decisions"], report["failed"]

    try:
        handle(ctx, operation, ["decisions", "write"], draw=_summary, resume=["decisions", "write"])
    finally:
        if report.get("reason") and not ctx.obj["json"]:
            typer.echo("Reason: " + report["reason"])


def add_decisions_app(rem, factory, handle, written):
    decisions = factory(help="co rem decisions", no_args_is_help=False)
    decisions.info.cls = verbatim("co rem decisions", decisions.info.cls)
    rem.add_typer(decisions, name="decisions")

    @decisions.callback(invoke_without_command=True)
    def overview(ctx: typer.Context):
        if ctx.invoked_subcommand:
            return
        from ...rem.decisions import status

        def operation(root):
            value = status(root)
            text = (f"Decision pages: {value['decisions']} · Principle pages: {value['principles']} · "
                    f"Decisions waiting: {value['waiting']}")
            return (value if ctx.obj["json"] else text), ["decisions", "write"]
        handle(ctx, operation, ["init"])

    @decisions.command("write", cls=verbatim("co rem decisions write"))
    def write_pages(ctx: typer.Context, rounds: Optional[int] = typer.Option(None, "--rounds", min=1)):
        write_decisions(ctx, rounds, handle, written)

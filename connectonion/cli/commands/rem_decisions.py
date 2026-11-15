"""Read-only decisions status and the abstract command's progress output."""

import typer

from .rem_help import verbatim


def _round_lines(number, row):
    lines = [f"Round {number}: {row['read']} captured lines read · {len(row['changed'])} pages written · {len(row['refused'])} pages refused"
             + _line_counts(row) + f" · Skipped: {row['lines'].get('not_decision', 0)} not a decision"]
    lines += [f"  refused {refusal['record']}: " + "; ".join(refusal["errors"]) for refusal in row["refused"]]
    return "\n".join(lines)


def _summary(value):
    ending = f"{value['left']} captured lines left"
    if value["reason"]:
        ending = f"stopped: {value['reason']} · {ending}"
    noun = "slice" if value['set_aside'] == 1 else "slices"
    deferred = f"{value['set_aside']} {noun} set aside for a later retry · "
    return (f"Done: {len(value['rounds'])} rounds · {value['written']} pages written · {value['refused']} pages refused · {deferred}{ending}"
            + _line_counts(value) + _skipped(value)
            + f" · Pages: {value['pages']['decisions']} decisions · {value['pages']['knowledge']} knowledge"
              f" · {value['pages']['principles']} principles")


def _line_counts(value):
    counts = value['lines']
    text = (f" · Lines: {counts.get('written', 0)} written · {counts.get('merged', 0)} merged"
            f" · {counts.get('refused', 0)} refused · {counts.get('no_answer', 0)} no answer")
    if value.get('given_up'):
        text += f" · {value['given_up']} given up"
    return text


def _skipped(value):
    counts = value['skipped']
    if not any(counts.values()):
        return ""
    return (f" · Skipped: {counts['no_quote']} no quote captured · {counts['no_source']} no bound source"
            f" · {counts['not_owner']} owner quote contradicted · {counts['not_decision']} not a decision")


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
        handle(ctx, operation, ["abstract"], draw=_summary, resume=["abstract"])
    finally:
        if report.get("reason") and not ctx.obj["json"]:
            typer.echo("Reason: " + report["reason"])


def add_decisions_app(rem, factory, handle):
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
                    f"Captured lines waiting: {value['waiting']} · {value['to_retry']} to retry"
                    + _line_counts(value) + _skipped(value))
            return (value if ctx.obj["json"] else text), ["abstract"]
        handle(ctx, operation, ["init"])

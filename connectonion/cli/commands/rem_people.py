"""`co rem investigate people`: recent correspondents first, in portions, cost first (#1943 stage 3).

Kept out of rem_commands.py on purpose, like rem_projects.py: the investigate
command hands the `people` category here in one line. Each person is still
investigated by `investigate.investigate` (#1942's evidence files); what this
adds is who comes next, over which window, and saying what it costs and what
is left.
"""

import typer


def _day(stamp: str) -> str:
    return stamp[:10] if stamp else "unknown"


def cost_line(estimate: dict, meter: dict) -> str:
    week = (f" The Codex week is at {meter['used_percent']}%." if "used_percent" in meter
            else f" Quota: {meter['unknown']}." if meter.get("unknown") else "")
    measured = estimate["measured"]
    known = (f" On this machine one {measured['mails']}-mail person took {measured['input_tokens'] / 1e6:.2f}M "
             f"input tokens and {measured['minutes']} minutes." if measured.get("input_tokens") else "")
    return (f"Cost: {estimate['model_calls']} model call(s), one per person; {estimate['mails_mapped']:,} mails "
            f"mapped for the full investigations, and {estimate['updates']} update(s) that read only mail since "
            f"their last investigation.{known}{week}")


def order_lines(rows: list[dict]) -> list[str]:
    return [f"  {row['record']}  (last mail {_day(row['last_activity'])}, "
            + (f"update: mail since {row['last_investigated']}, {row['days']} days" if row["mode"] == "update"
               else f"{row['mails']} mails mapped, {row['days']} days") + ")"
            for row in rows]


def run_people(ctx, root, *, limit: int, recent_days: int, days, list_only: bool, gate, clients_for,
               subscriptions, logged):
    """The people category: order, cost, then one person after another. Returns (result, next, failed)."""
    from ...rem import quota
    from ...rem.config import read_config
    from ...rem.people_pages import estimate, investigate_person, queue, write_pages
    rows = queue(root, recent_days=recent_days)
    if days:
        rows = [{**row, "days": days} if row["mode"] == "full" else row for row in rows]
    chosen = rows if limit == 0 else rows[:limit]
    config = read_config(root)
    if list_only:
        if ctx.obj["json"]:
            return {"category": "people", "order": rows, "estimate": estimate(chosen)}, ["investigate", "people"], False
        text = "\n".join([f"{len(rows)} people to investigate; {sum(r['recent'] for r in rows)} written to in the "
                          f"last {recent_days} days come first:", *order_lines(rows), "",
                          f"The next {len(chosen)}: " + cost_line(estimate(chosen), quota.read(config)),
                          "Nothing was read or spent."])
        return text, ["investigate", "people"], False
    if not chosen:
        return "No people to investigate: every page is investigated and nothing new has arrived.", \
            ["list", "people"], False
    typer.echo(f"Investigating {len(chosen)} of {len(rows)} people. "
               + cost_line(estimate(chosen), quota.read(config)), err=True)
    clients, sources = clients_for(root), subscriptions(root)

    def on_page(number, total, row):
        typer.echo(f"[{number}/{total}] {row['record']} (last mail {_day(row['last_activity'])}, "
                   f"{'update, ' if row['mode'] == 'update' else ''}{row['days']} days)", err=True)

    def one(row):
        return logged(root, row["record"], "investigate", lambda update: investigate_person(
            root, row, clients=clients, subscriptions=sources, stage_progress=update))

    result = write_pages(chosen, write=one, gate=gate, on_page=on_page)
    result["left"] = len(rows) - sum(1 for row in result["pages"] if row["outcome"] == "accepted")
    if result.get("stopped"):
        typer.echo(f"Stopped: {result['stopped']}", err=True)
    typer.echo(f"{result['left']} people left to investigate.", err=True)
    accepted = [row["page"] for row in result["pages"] if row["outcome"] == "accepted"]
    return ({"category": "people", **result}, ["show", accepted[0]] if accepted else ["logs"],
            any(row["outcome"] != "accepted" for row in result["pages"]))

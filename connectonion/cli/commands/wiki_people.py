"""`co wiki investigate people`: an agent searching each person's prepared evidence (#1943, #1850).

Kept out of wiki_commands.py on purpose, like wiki_projects.py: the investigate
command hands the `people` category here in one line, and everything it does
lives here and in wiki/people_evidence.py and wiki/people_pages.py.
"""

import typer


def _day(stamp: str) -> str:
    return stamp[:10] if stamp else "unknown"


def cost_line(estimate: dict, meter: dict) -> str:
    week = (f"; the Codex week is at {meter['used_percent']}%" if "used_percent" in meter
            else f"; {meter['unknown']}" if meter.get("unknown") else "")
    folders = (f"; their evidence folders hold {estimate['evidence_items']:,} items "
               f"({estimate['evidence_bytes'] / 1024:,.0f} KB) the agent searches and reads from"
               if estimate.get("evidence_items") else "")
    return (f"Cost: {estimate['model_calls']} model call(s), one per person, carrying about "
            f"{estimate['chars']:,} characters (~{estimate['tokens_estimated_in']:,} tokens) of skills, pages "
            f"and evidence indexes{folders}; the runner re-reads its context each turn, so billed input is "
            f"several times that{week}.")


def order_lines(rows: list[dict]) -> list[str]:
    return [f"  {row['record']}  (last mail {_day(row['last_activity'])}, "
            + (f"{row['new_items']} new items, update" if row["mode"] == "update"
               else f"{row['mails']} mails mapped, first write") + ")"
            for row in rows]


def run_people(ctx, root, *, limit: int, recent_days: int, days: int, list_only: bool, gate, clients_for,
               subscriptions, logged):
    """The people category: order, cost, then one model call per person. Returns (result, next, failed)."""
    from ...wiki import quota
    from ...wiki.config import read_config
    from ...wiki.people_pages import estimate, prepare_portion, queue, write_page, write_pages
    rows = queue(root, recent_days=recent_days)
    chosen = rows if limit == 0 else rows[:limit]
    config = read_config(root)
    if list_only:
        if ctx.obj["json"]:
            return {"category": "people", "order": rows, "estimate": estimate(chosen)}, ["investigate", "people"], False
        text = "\n".join([f"{len(rows)} people to investigate; {sum(r['recent'] for r in rows)} written to in the "
                          f"last {recent_days} days come first:", *order_lines(rows), "",
                          cost_line(estimate(chosen), quota.read(config)),
                          "Nothing was read or spent."])
        return text, ["investigate", "people"], False
    if not chosen:
        return ("Every people page is written from all of its evidence. Nothing to investigate.",
                ["list", "people"], False)
    clients, sources = clients_for(root), subscriptions(root)

    def on_person(number, total, row):
        typer.echo(f"Preparing evidence [{number}/{total}] {row['record']} (no model)", err=True)

    prepared = prepare_portion(root, chosen, clients=clients, subscriptions=sources, days=days,
                               on_person=on_person)
    typer.echo(f"Investigating {len(chosen)} of {len(rows)} people. "
               + cost_line(estimate(chosen, prepared), quota.read(config)), err=True)

    def on_page(number, total, row):
        typer.echo(f"[{number}/{total}] {row['record']} (last mail {_day(row['last_activity'])}, "
                   f"{prepared[row['record']].get('pending', 0)} items)", err=True)

    def one(record):
        return logged(root, record, "investigate", lambda update: write_page(
            root, record, config=config, clients=clients, subscriptions=sources, days=days,
            progress=update, prepared=prepared[record]))

    result = write_pages(root, limit=0, write=one, gate=gate, on_page=on_page, rows=chosen)
    result["left"] = len(rows) - sum(1 for row in result["pages"] if row["outcome"] in ("accepted", "skipped"))
    if result.get("stopped"):
        typer.echo(f"Stopped: {result['stopped']}", err=True)
    typer.echo(f"{result['left']} people left to investigate.", err=True)
    accepted = [row["page"] for row in result["pages"] if row["outcome"] == "accepted"]
    return ({"category": "people", **result}, ["show", accepted[0]] if accepted else ["logs"],
            any(row["outcome"] not in ("accepted", "skipped") for row in result["pages"]))

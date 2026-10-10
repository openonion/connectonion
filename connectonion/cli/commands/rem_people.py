"""`co rem investigate people`: recent correspondents first, in portions, cost first (#1943 stage 3).

Kept out of rem_commands.py on purpose, like rem_projects.py: the investigate
command hands the `people` category here in one line. Each person is still
investigated by `investigate.investigate` (#1942's evidence files); what this
adds is who comes next, over which window, and saying what it costs and what
is left.
"""

from . import rem_look


def _day(stamp: str) -> str:
    return stamp[:10] if stamp else "unknown"


def counted(number: int, word: str, plural: str = "") -> str:
    """"1 mail", "2 mails": 1.9.0a2 said "1 mails"."""
    return f"{number:,} {word if number == 1 else plural or word + 's'}"


def cost_line(estimate: dict, meter: dict) -> str:
    """The cost before anything is read. The mail counts are the map's, and a floor.

    The map lists one window (90 days by default) with a metadata listing; an
    investigation reads `window_days` and searches the server for every
    address, which found 617 mails for a person the map counted once (#1974).
    """
    week = (f" The Codex week is at {meter['used_percent']}%." if "used_percent" in meter
            else f" Quota: {meter['unknown']}." if meter.get("unknown") else "")
    measured = estimate["measured"]
    known = (f" Historical sample ({measured['date']}, {measured['window_days']}-day read): "
             f"one {measured['mails']}-mail person took {measured['input_tokens'] / 1e6:.2f}M "
             f"input tokens and {measured['minutes']} minutes. A longer read may cost more."
             if measured.get("input_tokens") else "")
    return (f"Cost: {counted(estimate['model_calls'], 'model call')}, one per person; at least "
            f"{counted(estimate['mails_mapped'], 'mail')} for the full investigations (the map's count: they read "
            f"{estimate.get('window_days', 150)} days and search the server, which finds more), and "
            f"{counted(estimate['updates'], 'update')} that read only mail since their last "
            f"investigation.{known}{week}")


def order_lines(rows: list[dict]) -> list[str]:
    return [f"  {row['record']}  (last mail {_day(row['last_activity'])}, "
            + (f"update: mail since {row['last_investigated']}, {row['days']} days" if row["mode"] == "update"
               else f"at least {counted(row['mails'], 'mail')} in the map, reads {row['days']} days") + ")"
            for row in rows]


def owner_first(ctx, root) -> list[str]:
    """Your own page, and addresses that may be yours, before anyone else (#1943, #1974).

    Empty when your page has been investigated and nothing is left to confirm.
    """
    from ...rem.files import Notebook, read_json, state_path
    from ...rem.queue import last_investigated
    from .rem_commands import _next
    state = read_json(state_path(root, "map.json"), {})
    record = (state.get("owner") or {}).get("record")
    lines = []
    notebook = Notebook(root)
    if record and notebook.path(record).is_file():
        status = next((line for line in notebook.read(record).splitlines() if line.startswith("Investigation:")), "")
        if last_investigated(status) is None:
            lines.append(f"First, your own page ({record}), not investigated yet: "
                         + _next(ctx, ["investigate", "me"]))
    possible = [row for row in state.get("possible_own_addresses") or [] if row.get("address")][:6]
    if possible:
        # Spelled here, never read from the map: a 1.8 map stored `co wiki init --mine`.
        lines.append("Possibly yours (you wrote, they never replied): "
                     + ", ".join(f"{row['address']} ({row.get('sent', 0)} sent)" for row in possible)
                     + ". Confirm the ones that are yours: "
                     + _next(ctx, ["init", "--mine", ",".join(row["address"] for row in possible)]))
    return lines


def run_people(ctx, root, *, limit: int, recent_days: int, days, list_only: bool, gate, clients_for,
               subscriptions, logged, budget=None, announce=True, workers: int = 1):
    """The people category: order, cost, then bounded parallel work. Returns (result, next, failed).

    `announce=False` is init's first run, which has already said one total
    for every page it will write (#2008).
    """
    from ...rem import quota
    from ...rem.config import read_config
    from ...rem.people_pages import estimate, investigate_person, queue, write_pages
    rows = queue(root, recent_days=recent_days)
    if days:
        rows = [{**row, "days": days} if row["mode"] == "full" else row for row in rows]
    chosen = rows if limit == 0 else rows[:limit]
    config = read_config(root)
    budget_note = (f" Budget: {budget} points is advisory; up to {workers} already-started pages can finish "
                   "after it is reached." if budget else "")
    if list_only:
        next_step = ["investigate", "people", "--limit", str(limit)]
        if budget:
            next_step += ["--budget", str(budget)]
        if days:
            next_step += ["--days", str(days)]
        if recent_days != 14:
            next_step += ["--recent-days", str(recent_days)]
        if ctx.obj["json"]:
            return ({"category": "people", "order": rows, "estimate": estimate(chosen),
                     "first": owner_first(ctx, root)}, next_step, False)
        text = "\n".join([*owner_first(ctx, root),
                          f"{counted(len(rows), 'person', 'people')} to investigate: people you wrote to first, "
                          f"then people who wrote more than once, then one-mail contacts; the last {recent_days} "
                          "days first in each:", *order_lines(rows), "",
                          f"The next {len(chosen)}: " + cost_line(estimate(chosen), quota.read(config))
                          + budget_note,
                          "Nothing was read or spent."])
        return text, next_step, False
    if not chosen:
        return "No people to investigate: every page is investigated and nothing new has arrived.", \
            ["list", "people"], False
    meter = quota.read(config)
    if announce:
        rem_look.line(f"Investigating {len(chosen)} of {len(rows)} people. "
                      + cost_line(estimate(chosen), meter) + budget_note, err=True)
    sources = subscriptions(root)

    def on_page(number, total, row, outcome):
        rem_look.line(f"[{number}/{total}] {row['record']}: {outcome['outcome']} "
                      f"(last mail {_day(row['last_activity'])}, "
                      f"{'update, ' if row['mode'] == 'update' else ''}{row['days']} days)", err=True)

    def one(row):
        return logged(root, row["record"], "investigate", lambda update: investigate_person(
            root, row, clients=clients_for(root), subscriptions=sources, stage_progress=update))

    result = write_pages(chosen, write=one, gate=gate, on_page=on_page, workers=workers)
    result["left"] = len(rows) - sum(1 for row in result["pages"] if row["outcome"] == "accepted")
    if result.get("stopped"):
        rem_look.line(f"Stopped: {result['stopped']}", err=True)
    rem_look.line(f"{counted(result['left'], 'person', 'people')} left to investigate.", err=True)
    accepted = [row["page"] for row in result["pages"] if row["outcome"] == "accepted"]
    return ({"category": "people", **result}, ["show", accepted[0]] if accepted else ["logs"],
            any(row["outcome"] != "accepted" for row in result["pages"]))

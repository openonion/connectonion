"""Which pages to investigate next, in what order (#1656).

A category run spends minutes, sometimes forty, per page, so the order is the
product: pages still marked Unknown, the ones with the most mail or sessions
first, because those are the relationships and projects the owner lives in.
The map already counted them; nothing here reads a source.

Left out on purpose:
- the owner's own page -- it has its own reading (`investigate me`), and the
  person path excludes the owner's addresses, so it would read no mail at all;
- addresses the map thinks may be the owner's -- investigated as a person, the
  owner's second Gmail (106 sent, 0 received) would top the list and pull the
  owner's own mail into a page about nobody;
- automated candidates, which are not people, and senders a people queue
  leaves out as vendors (`excluded_people`);
- addresses held for review (#1844): no name, and the owner never wrote to them;
- a page investigated in the last week, so a daily category run does not
  spend the budget re-reading what it just read -- unless that investigation
  read nothing about its subject (`hollow_investigations`, #1974).
"""

import re
from datetime import date, datetime, timezone

from .files import Notebook, read_json, state_path
from .map import needs_review

CATEGORIES = {"people": "people/", "projects": "projects/", "orgs": "orgs/", "skills": "skills/catalog/"}
RECENT_DAYS = 7


def last_investigated(status_line: str) -> date | None:
    # `written <date>` is a pass that read the page's sources too (#1983):
    # counted only as "investigated", a project page sync had just written
    # topped the queue as "not investigated" (#2046).
    days = [d for d in re.findall(r"(?<!not )(?:investigated|written) (\d{4}-\d{2}-\d{2})", status_line)]
    return max(date.fromisoformat(d) for d in days) if days else None


def weights(state: dict, excluded: frozenset | set = frozenset()) -> dict:
    """How much of the owner's work each page stands for, from the last map:
    mail for a person, sessions for a project, people for an org. The one
    order the queue and `list` share; `list` sorted by file name put agent
    addresses like 0x3c3ae74550@mail.openonion.ai above the owner's
    colleagues (#1670).

    An org counts only the people a queue would investigate: github.com led
    the 1.9.0a7 orgs queue with "6 people", all of them unsubscribe addresses
    (#2046)."""
    weight = {row.get("record"): row.get("mails") or 0 for row in state.get("people", [])}
    weight.update({row.get("record"): row.get("sessions") or 0 for row in state.get("projects", [])})
    weight.update({row.get("record"): len([p for p in row.get("people") or [] if p not in excluded])
                   for row in state.get("orgs", [])})
    return weight


def by_weight(root, records: list[str]) -> list[str]:
    weight = weights(read_json(state_path(root, "map.json"), {}))
    return sorted(records, key=lambda record: (-weight.get(record, 0), record))


def excluded_people(state: dict) -> set:
    """People pages no queue investigates: the owner, what may be the owner's, and senders that are not people.

    One definition for every people queue; `investigate --list` and
    `investigate people --list` once disagreed by four pages (#1974). A sender
    is left out when every address looks automated (no-reply, notifications,
    billing ...), or when the owner never wrote to them and their domain also
    sends the notices the map set aside -- `express@airbnb.com` beside
    `automated@airbnb.com` -- the vendors that topped 1.9.0a2's queue.
    """
    from .map import service_page
    from .scan import AUTOMATED_HINT
    excluded = {(state.get("owner") or {}).get("record")}
    excluded |= {row.get("record") for row in state.get("possible_own_addresses", [])}
    notice_domains = {row.get("address", "").rpartition("@")[2].casefold()
                      for row in state.get("automated_correspondents", []) if "@" in row.get("address", "")}
    for row in state.get("people", []):
        addresses = row.get("addresses") or ([row["address"]] if row.get("address") else [])
        vendor = not row.get("sent") and addresses and all(
            address.rpartition("@")[2].casefold() in notice_domains for address in addresses)
        # An older map's row the map's own rule now calls a service (#2031): an
        # investor-update sender cost the 1.9.0a6 daily round 100,080 tokens.
        if (row.get("classification") == "automated candidate" or vendor
                or (addresses and all(AUTOMATED_HINT.search(address) for address in addresses))
                or (addresses and service_page(row.get("name") or "", addresses, row, set()))):
            excluded.add(row.get("record"))
    return excluded


def _material_read(coverage: list[str]) -> int:
    """How many bodies, attachments and messages an investigation's coverage says it read."""
    text = "\n".join(coverage)
    counts = re.findall(r"(\d+) bodies read|(\d+) attachments read|, (\d+) read\b", text)
    return sum(int(number) for row in counts for number in row if number)


def hollow_investigations(root) -> set:
    """People and organisation pages whose latest recorded investigation read nothing about them (#1974).

    1.9.0a2 stamped such pages "investigated": 8 bodies matched and "summarised
    in 0 chunk(s)", or 33 mails listed and none read. The run record keeps the
    coverage, so the queue can take them back without anyone editing a page.
    Project pages are read from their files too, which coverage does not count,
    so they are not judged here.

    The daily round records its pages without their coverage, so the page is
    asked too: stamped investigated, with no Sources entry naming a message,
    session, URL or file -- only the coverage note, the page, or the map. That
    is the founders@ page on the owner's notebook.
    """
    notebook = Notebook(root)
    hollow = {record for category in ("people", "orgs") for record in notebook.list(category)
              if _stamped_from_nothing(notebook.read(record))}
    from .merge import resolve
    latest = {}
    for path in state_path(root, "runs").glob("run_*.json"):
        run = read_json(path, {})
        if not isinstance(run, dict) or run.get("phase") not in ("investigate", "investigate me"):
            continue
        # A record merged since (#1976) is judged as the page it now lives in.
        record = resolve(root, run.get("record") or "")
        if record.startswith(("people/", "orgs/")) and run.get("outcome") == "completed" \
                and run.get("started_at", "") > latest.get(record, {}).get("started_at", ""):
            latest[record] = run
    return hollow | {record for record, run in latest.items() if notebook.path(record).is_file()
                     and (_material_read(run.get("coverage") or []) == 0
                     or any(re.search(r"summarised in 0 chunk", line) for line in run.get("coverage") or []))}


def _stamped_from_nothing(page: str) -> bool:
    from .page_review import SOURCE_ID
    status = next((line for line in page.splitlines() if line.startswith("Investigation:")), "")
    if last_investigated(status) is None:
        return False
    sources = page.partition("\n## Sources\n")[2].split("\nInvestigation:")[0]
    return not any(SOURCE_ID.search(line) or re.search(r"https?://|`/[^`]+`", line)
                   for line in sources.splitlines())


def order(root, category: str, today: date | None = None) -> list[dict]:
    if category not in CATEGORIES:
        raise ValueError(category)
    today = today or datetime.now(timezone.utc).date()
    prefix = CATEGORIES[category]
    state = read_json(state_path(root, "map.json"), {})
    from .merge import resolve
    # The map may name a record a later merge aliased (#1976): exclude the page it lives in.
    excluded = {resolve(root, record) for record in excluded_people(state) if record} | needs_review(root)
    weight = weights(state, excluded)
    # An org whose every mapped person is left out is a sender, not an
    # organisation the owner deals with: nothing about it is worth a turn (#2046).
    excluded |= {row.get("record") for row in state.get("orgs", [])
                 if row.get("people") and not weight.get(row.get("record"))}
    hollow = hollow_investigations(root) if category in ("people", "orgs") else set()
    notebook = Notebook(root)
    entries = notebook.unfinished(prefix.split("/")[0])
    listed = {entry["path"] for entry in entries}
    # A hollow page may have had its Unknowns written over with nothing; it is
    # unfinished all the same.
    entries += [{"path": path, "unknown": 0, "status": ""} for path in sorted(hollow - listed)
                if path.startswith(prefix) and notebook.path(path).is_file()]
    rows = []
    for entry in entries:
        path = entry["path"]
        if not path.startswith(prefix) or path in excluded or path.endswith("/index.md"):
            continue
        if category == "projects":
            from .project_pages import private
            if private(path, notebook.read(path)):
                continue   # the owner's journal is investigated only when they name it (#2079)
        last = None if path in hollow else last_investigated(entry["status"])
        rows.append({"path": path, "weight": weight.get(path, 0), "unknown": entry["unknown"],
                     "last_investigated": last.isoformat() if last else None,
                     "recent": bool(last and (today - last).days < RECENT_DAYS),
                     **({"hollow": True} if path in hollow else {})})
    rows.sort(key=lambda row: (row["recent"], -row["weight"], -row["unknown"], row["path"]))
    return rows


ALL = ("people", "projects", "orgs", "skills")


def order_all(root) -> list[dict]:
    """People, projects and organisations in one queue, by weight (#1842).

    The first pass after init and the scheduled round both take the busiest
    page next, whatever its kind; one order keeps them from disagreeing.
    """
    rows = [row for category in ALL for row in order(root, category)]
    rows.sort(key=lambda row: (row["recent"], -row["weight"], -row.get("unknown", 0), row["path"]))
    return rows

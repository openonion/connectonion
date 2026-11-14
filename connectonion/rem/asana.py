"""Asana as a co rem source: the newest collected version of each selected task.

Two halves, kept apart. `collect_now` is the only part that talks to Asana: it
runs asana_export's sync_tasks for the subscription's project gids, once per
sync, before the notebook is locked, and saves changed tasks under inbox/asana.
Everything else reads that folder only: `pending_asana` counts what is waiting
for a dry run from the index alone, and `collect_asana` turns the newest
committed snapshot of each waiting task into one item, the way chat.py turns
saved messages into items. No model, no CLI, no network in either.

Progress is per task: progress["consumed"][task_gid] is the change_id of the
snapshot REM last read. A task is pending when its newest snapshot has another
change_id, so an older version that was replaced before it was read is never
read at all -- REM is given each task's latest version, not its history.
"""

import json
from datetime import datetime
from pathlib import Path

from .files import RemError
from .source import MAX_MESSAGE_CHARS, TRUNCATION_NOTE, Batch

ASANA = "asana"
# One task's material: header, description and comments. A task with years of
# comments keeps its newest ones; what was left out is said, not hidden.
MAX_TASK_CHARS = 12000


# -- the network half -----------------------------------------------------------

def collect_now(subscription: dict, client=None) -> dict:
    """Fetch the selected projects' changes into the source folder; returns sync_tasks' summary.

    Raises AsanaError / AsanaStoreError / ValueError as sync_tasks does; the
    caller decides that a failed collection still lets saved snapshots be read.
    """
    from ..useful_tools.asana_export import sync_tasks
    gids = list(subscription.get("project_gids") or [])
    if not gids:
        raise RemError("Asana has no selected project; add one with co rem sources add asana --project <gid>")
    if client is None:
        from ..useful_tools.asana import Asana
        client = Asana()
    return sync_tasks(client, Path(subscription["root"]), gids)


# -- the local half ---------------------------------------------------------------

def _source(subscription: dict) -> Path:
    return Path(subscription["root"])


def _status(subscription: dict) -> dict:
    from ..useful_tools.asana_export import export_status
    return export_status(_source(subscription))


def _pending(subscription: dict, progress: dict, status: dict) -> list[dict]:
    """The newest committed snapshot of every selected task REM has not read in that version."""
    from ..useful_tools.asana_export import latest_snapshots
    if not status["initialized"]:
        return []
    consumed = progress.get("consumed") if isinstance(progress.get("consumed"), dict) else {}
    snapshots = latest_snapshots(_source(subscription), account_gid=status["account_gid"],
                                 project_gids=list(subscription.get("project_gids") or []))
    return [snapshot for snapshot in snapshots if consumed.get(snapshot["task_gid"]) != snapshot["change_id"]]


def pending_asana(subscription: dict, progress: dict) -> dict:
    """What a dry run says: counts from the index only -- no request, no task body read."""
    status = _status(subscription)
    base = {"body_reads": False, "projects": list(subscription.get("project_gids") or []),
            "source_available": subscription.get("adapter") == "available",
            "last_success_at": status["last_success_at"], "last_failure": status["last_failure"]}
    if not status["initialized"]:
        # Never collected is not "nothing pending": the count is unknown until a sync collects.
        return {**base, "initialized": False, "pending_tasks": None,
                "note": "not collected yet; the next co rem sync collects first"}
    return {**base, "initialized": True, "pending_tasks": len(_pending(subscription, progress, status))}


def collect_asana(subscription: dict, progress: dict, max_items: int, max_chars: int) -> Batch:
    """Up to max_items waiting tasks, oldest collection first, one item each, within max_chars."""
    from ..useful_tools.asana_export import load_snapshots
    if not subscription.get("enabled") or not subscription.get("consented"):
        raise RemError("Source is disabled or not yet authorized; run start to confirm access")
    status = _status(subscription)
    consumed = dict(progress.get("consumed") or {}) if isinstance(progress.get("consumed"), dict) else {}
    updated = {**progress, "consumed": consumed}
    items, used = [], 0
    for snapshot in _pending(subscription, progress, status):
        if len(items) >= max_items:
            break
        [record] = load_snapshots(_source(subscription), [snapshot])
        item = task_item(record)
        size = len(json.dumps(item, ensure_ascii=False))
        if items and used + size > max_chars:
            break   # the next task waits whole for the next batch
        items.append(item)
        used += size
        consumed[snapshot["task_gid"]] = snapshot["change_id"]
    return Batch(items, updated)


# -- investigation ---------------------------------------------------------

NOT_CONNECTED = f"{ASANA}: not connected; not searched"

def gather_asana(subscription: dict, handles: list[str], *, start: datetime, record: str,
                 owner: bool = False) -> tuple[list[dict], list[str]]:
    """Tasks about one page's subject from the saved Asana material, and the coverage lines saying what was read.

    Local only: it never asks Asana and never touches sync progress; what
    `co rem sync` collected is what there is. Each task is read in its newest
    saved version.

    Identity is an Asana gid, never a name alone. A handle that is a gid seen
    in the material (`--handle <gid>`) decides by itself. Otherwise the page's
    names are looked up among the people (assignees and real comment authors;
    Asana's own activity names no one we can trust) or the projects, and used
    only when they lead to exactly one gid: two "Bob Lee"s, or two projects
    called Atlas, are not merged -- nothing is read and the line names the gids
    to choose from. `owner` (the owner's own page) is the token's account.

    A task counts when it changed inside the window or got a real comment
    inside it (for a person, a comment of theirs).
    """
    from ..useful_tools.asana_export import AsanaStoreError, latest_snapshots, load_snapshots
    if record.startswith("orgs/"):
        return [], [f"{ASANA}: not read for organisation pages; not searched"]
    if not subscription.get("enabled") or not subscription.get("project_gids"):
        # No project chosen is said as "not connected", not left out.
        return [], [NOT_CONNECTED]
    if not subscription.get("consented"):
        return [], [f"{ASANA}: not approved yet (co rem start); not searched"]
    try:
        status = _status(subscription)
        if not status["initialized"]:
            return [], [f"{ASANA}: nothing collected yet (co rem sync --source asana collects it); not searched"]
        snapshots = latest_snapshots(_source(subscription), account_gid=status["account_gid"],
                                     project_gids=list(subscription["project_gids"]))
        records = load_snapshots(_source(subscription), snapshots)
    except (AsanaStoreError, OSError, ValueError) as error:
        return [], [f"{ASANA}: unreadable ({error}); not searched"]
    account = status["account_gid"]
    project_page = record.startswith("projects/")
    kind = "project" if project_page else "person"
    if owner and not project_page:
        ids, how = {account}, "the account owner's own tasks and comments"
    else:
        wanted = {h.strip().casefold() for h in handles if h and h.strip()}
        ids, how, ambiguous = _identify(records, wanted, project_page)
        if ambiguous:
            choices = "; ".join(f"{name!r} is {', '.join(sorted(gids))}" for name, gids in ambiguous.items())
            return [], [f"{ASANA}: the page's name matches more than one Asana {kind} ({choices}); "
                        f"not merged and not searched; name one with co rem investigate {record} --handle <gid>"]
    picked = [r for r in records if _about(r, ids, start, project_page)]
    found = []
    for r in picked:
        item = task_item(r)
        # How many comments on this task are the user's own words: the evidence
        # a project page may draw Insight from, where an assignment is not.
        item["user_comments"] = sum(1 for s in r.get("stories") or []
                                    if _is_comment(s) and isinstance(s.get("created_by"), dict)
                                    and s["created_by"].get("gid") == account and str(s.get("text") or "").strip())
        found.append(item)
    who = f"gid {', '.join(sorted(ids))}" if ids else "no match"
    line = (f"{ASANA}: {len(records)} task(s) saved from the selected projects, {len(found)} about the subject "
            f"in the window, read ({how}; {who}); collected by sync, last at {status['last_success_at']}")
    return found, [line]


def _identify(records: list[dict], wanted: set, project_page: bool) -> tuple[set, str, dict]:
    """The subject's Asana gids: (gids, how, ambiguous names -> their gids)."""
    names = {}   # gid -> every name it was seen under
    for r in records:
        task = r["task"]
        things = (task.get("projects") or []) if project_page else \
            [task.get("assignee")] + [s.get("created_by") for s in r.get("stories") or [] if _is_comment(s)]
        for thing in things:
            if isinstance(thing, dict) and thing.get("gid"):
                names.setdefault(str(thing["gid"]), set()).add(str(thing.get("name") or "").strip().casefold())
    given = {gid for gid in names if gid.casefold() in wanted}
    if given:
        return given, "gid given", {}
    by_name = {}
    for gid, seen in names.items():
        for name in seen & wanted:
            by_name.setdefault(name, set()).add(gid)
    matched = set().union(*by_name.values()) if by_name else set()
    if len(matched) > 1:
        return set(), "", by_name
    return matched, ("project name" if project_page else "assignee or comment author name") + ", one gid", {}


def _about(record: dict, ids: set, start: datetime, project_page: bool) -> bool:
    """Whether one task snapshot is about the subject inside the window."""
    if not ids:
        return False
    task = record["task"]
    changed = _after(task.get("modified_at"), start)
    comments = [s for s in record.get("stories") or [] if _is_comment(s) and _after(s.get("created_at"), start)]
    if project_page:
        return any(isinstance(p, dict) and str(p.get("gid")) in ids for p in task.get("projects") or []) \
            and (changed or bool(comments))
    def mine(person):
        return isinstance(person, dict) and str(person.get("gid")) in ids
    return (changed and mine(task.get("assignee"))) or any(mine(s.get("created_by")) for s in comments)


def _after(stamp, start: datetime) -> bool:
    """Asana's ISO time at or after start; an unreadable time is not in the window."""
    try:
        when = datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))
    except ValueError:
        return False
    if when.tzinfo is None:
        return False
    return when >= start


# -- a cited version, for the claim audit and the reader ------------

CITED_SCOPE = ("One saved Asana task version, as co rem sync collected it: name, projects, assignee, due date, "
               "status, description and comments by named authors. Asana's own activity such as assignment "
               "or completion is counted, not quoted, so who assigned a task is not shown.")


def cited_snapshot(root: Path, source: str) -> dict | None:
    """The local excerpt of one cited Asana change_id, read in the version cited; None when it cannot be shown.

    Offline: it reads the notebook's saved subscription and the inbox/asana
    folder it names, never Asana. A citation is shown only while Asana is on
    and approved for this notebook and the snapshot belongs to one of the
    selected projects: a change from another account, a position that was
    never committed, or a task outside the chosen projects stays unresolved,
    so the audit keeps refusing it.
    """
    if not source.startswith(ASANA + ":"):
        return None
    from ..useful_tools.asana_export import AsanaStoreError, load_change
    from .files import read_json, state_path
    from .reader_model import PRIVATE
    saved = read_json(state_path(root, "subscriptions.json"), {})
    subscription = saved.get(ASANA) if isinstance(saved, dict) else None
    if not (isinstance(subscription, dict) and subscription.get("kind") == ASANA and subscription.get("root")
            and subscription.get("enabled") and subscription.get("consented") and subscription.get("project_gids")):
        return None
    try:
        record = load_change(Path(subscription["root"]), source)
    except (AsanaStoreError, OSError, ValueError):
        return None
    if record is None or not set(map(str, record["project_gids"])) & set(map(str, subscription["project_gids"])):
        return None
    item = task_item(record)
    if PRIVATE.search(item["text"]):
        return None
    # task_item already keeps one task within MAX_TASK_CHARS and says what it left out.
    clipped = "[truncated by co rem:" in item["text"] or "omitted by co rem:" in item["text"]
    return {"excerpt": item["text"], "truncated": clipped, "time": item["timestamp"], "sender": "",
            "thread": "", "source": ASANA, "subject": item["subject"], "captured_at": record.get("collected_at") or "",
            "input_scope": CITED_SCOPE}


# -- one task as material ---------------------------------------------------------------

def task_item(record: dict) -> dict:
    """One REM item for one task snapshot: who it is assigned to, where it lives, what was said.

    Deterministic: the same snapshot always gives the same text. Comments are
    attributed to their authors by name and gid; the token owner's own comments
    are marked "(you)", since only they can carry the user's commitments.
    System activity (assigned, completed, moved) is counted, not quoted.
    """
    task, stories = record["task"], record.get("stories") or []
    owner = record["change_id"].split(":")[1]
    name = task.get("name") or "(untitled)"
    projects = [p.get("name") or p.get("gid") for p in task.get("projects") or [] if isinstance(p, dict)]
    assignee = task.get("assignee") if isinstance(task.get("assignee"), dict) else None
    lines = [f"Asana task: {name}",
             f"Projects: {', '.join(projects) if projects else '(none)'}",
             f"Assignee: {_person(assignee, owner) if assignee else 'unassigned'}",
             f"Due: {task.get('due_at') or task.get('due_on') or 'no due date'}",
             "Status: " + (f"completed {task.get('completed_at') or ''}".strip() if task.get("completed") else "open"),
             f"Link: {task.get('permalink_url') or 'asana task ' + str(task.get('gid'))}"]
    notes = _clip(str(task.get("notes") or "").strip())
    if notes:
        lines += ["", "Description:", notes]
    comments = sorted((s for s in stories if _is_comment(s) and str(s.get("text") or "").strip()),
                      key=lambda s: (str(s.get("created_at")), str(s.get("gid"))))
    activity = sum(1 for s in stories if not _is_comment(s))
    if comments:
        lines += ["", "Comments (oldest first):"]
        lines += [f"- {s.get('created_at')} {_person(s.get('created_by'), owner)}: {_clip(str(s['text']).strip())}"
                  for s in comments]
    if activity:
        lines += ["", f"({activity} activity record(s) by Asana, such as assignment or completion, not quoted)"]
    text = "\n".join(lines)
    if len(text) > MAX_TASK_CHARS:
        # Keep the header and the newest comments: drop from the start of the comment list.
        header = "\n".join(lines[:6])
        tail = text[-(MAX_TASK_CHARS - len(header) - 200):]
        text = (header + "\n\n[earlier description and comments omitted by co rem: "
                f"{len(text) - len(header) - len(tail)} characters]\n" + tail)
    return {"role": "other", "speaker": _person(assignee, owner) if assignee else "",
            "correspondent": "", "text": text,
            "timestamp": str(task.get("modified_at") or record.get("collected_at")),
            "source": record["change_id"],
            "reference": task.get("permalink_url") or f"asana:task/{task.get('gid')}",
            "project": projects[0] if projects else "", "subject": name}


def _is_comment(story: dict) -> bool:
    return isinstance(story, dict) and (story.get("type") == "comment"
                                        or story.get("resource_subtype") == "comment_added")


def _person(person, owner: str) -> str:
    if not isinstance(person, dict):
        return "(Asana)"
    label = f"{person.get('name') or '(no name)'} [{person.get('gid')}]"
    return label + " (you)" if person.get("gid") == owner else label


def _clip(text: str) -> str:
    if len(text) <= MAX_MESSAGE_CHARS:
        return text
    return text[:MAX_MESSAGE_CHARS] + TRUNCATION_NOTE.format(dropped=len(text) - MAX_MESSAGE_CHARS)

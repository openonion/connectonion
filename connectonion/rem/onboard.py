"""
Purpose: map one source into the notebook: the source says which kinds of page it yields, the map reads each row's kind (#3331)
LLM-Note:
  Dependencies: imports from [chat.wechat_people, map (_people_groups, worth_a_page, _notice, _service, _record, _mail_rows, project_groups, file_project), org_map, scan.scan_projects, files] | imported by [cli/commands/rem_commands.py `co rem map`, native_round onboarding]
  Data flow: rows(root, name, sub) -> [{kind: person|org|project|knowledge, ...}] | plan(root, rows, kinds, write) -> {kind: {create, merge, known, skip}}
  State/Effects: write=False touches nothing (the dry run); write=True only adds pages and handles, never removes or rewrites prose
  Integration: a new source declares its kinds in YIELDS and a producer in PRODUCERS; the appliers never branch on the source
  Errors: RemError when a kind is asked of a source that doesn't yield it, or the source isn't known
"""

from pathlib import Path

from .files import Notebook, RemError, read_json, state_path

KIND_WORDS = ("people", "orgs", "projects", "knowledge")
ROW_KIND = {"person": "people", "org": "orgs", "project": "projects", "knowledge": "knowledge"}
# What each source kind yields. A new source adds one line here and one producer below; the map code is unchanged.
YIELDS = {
    "gmail": ("people", "orgs"),
    "outlook": ("people", "orgs"),
    "wechat": ("people",),
    "codex": ("projects",),
    "claude-code": ("projects",),
}


def yields(sub: dict) -> tuple:
    return YIELDS.get(sub.get("kind", ""), ())


def check_kinds(name: str, sub: dict, wanted: tuple) -> tuple:
    """The kinds to build: every kind the source yields, or the asked ones if it yields them all."""
    have = yields(sub)
    if not have:
        raise RemError(f"{name} can't be mapped yet; mappable sources: {', '.join(sorted(YIELDS))}")
    missing = [kind for kind in wanted if kind not in have]
    if missing:
        refused = RemError(f"{name} yields: {', '.join(have)}")
        refused.exit_code = 2   # wrong usage, not a failure of the source
        raise refused
    return wanted or have


def _mail_rows(name, sub, days):
    from .map import _mail_rows as scan
    from .service import mail_client
    people, _own = scan({sub["kind"]: mail_client(sub["kind"])}, days, (), [])
    return [{**row, "kind": "person"} for row in people] + \
           [{"kind": "org", "address": row["address"], "one_way": row.get("one_way")} for row in people]


def _wechat_rows(name, sub, days):
    from .chat import wechat_people
    return [{**row, "kind": "person"} for row in wechat_people()]


def _coding_rows(name, sub, days, root=None):
    from .scan import scan_projects
    return [{**row, "kind": "project"} for row in scan_projects({name: sub}, days, root)]


PRODUCERS = {"gmail": _mail_rows, "outlook": _mail_rows, "wechat": _wechat_rows,
             "codex": _coding_rows, "claude-code": _coding_rows}


def rows(root: Path, name: str, sub: dict, days: int) -> list[dict]:
    produce = PRODUCERS[sub["kind"]]
    return produce(name, sub, days, root) if produce is _coding_rows else produce(name, sub, days)


def _roster(notebook):
    people = notebook.people()
    by_handle = {h.casefold(): p["path"] for p in people for h in (*p["aliases"], *p["emails"])}
    by_name = {}
    for person in people:
        key = " ".join(person["title"].split()).casefold()
        if len(key.split()) >= 2:
            by_name.setdefault(key, person["path"])
    return by_handle, by_name


def _add_handles(notebook, record, handles):
    """Give an existing page the handles it is reachable on in the new source; prose is untouched."""
    lines = notebook.read(record).split("\n")
    from .files import EMAIL
    for label, wanted in (("Also known as", [h for h in handles if not EMAIL.fullmatch(h)]),
                          ("Email", [h for h in handles if EMAIL.fullmatch(h)])):
        index = next((i for i, line in enumerate(lines) if line.startswith(f"- {label}:")), None)
        if not wanted or index is None:
            continue
        value = lines[index].split(":", 1)[1].strip()
        have = [] if value in ("", "Unknown") else [v.strip() for v in value.split(",")]
        lines[index] = f"- {label}: " + ", ".join(dict.fromkeys([*have, *wanted]))
    notebook.write(record, "\n".join(lines))


def _rank(group) -> int:
    """Which new pages are worth reading first (#3347): chats on this machine, then friends the owner named, then
    the rest of the address book."""
    if sum(r.get("sent", 0) + r.get("received", 0) for r in group):
        return 0
    return 1 if any(r.get("remark") for r in group) else 2


def _people(notebook, people_rows, write):
    from . import map as rem_map
    from .threads import person_marks
    by_handle, by_name = _roster(notebook)
    # The owner's 不是人 on a handle sticks: such a contact is never stubbed or merged into a page, by
    # `co rem map` or by the night's re-map (#3339). A page already made for it is set aside by the census.
    marks = person_marks(notebook.root)
    out = {"create": [], "merge": [], "known": 0, "skip": 0, "not_person": 0, "retitled": []}
    for group in rem_map._people_groups(people_rows):
        handles = [row["address"] for row in group]
        name = " ".join(str(next((r["name"] for r in group if r.get("name")), "")).split())
        sent, received = (sum(r.get(k, 0) for r in group) for k in ("sent", "received"))
        said = {marks.get(h.casefold()) for h in handles} - {None}
        if "not-person" in said and "person" not in said:
            out["not_person"] += 1
            continue
        if any(h.casefold() in by_handle for h in handles):
            out["known"] += 1
            record = next(by_handle[h.casefold()] for h in handles if h.casefold() in by_handle)
            if _retitle(notebook, record, name, write):
                out["retitled"].append(record)
            continue
        # A friend in the owner's address book is worth a page with no messages: he added them (#3347).
        friend = all(r.get("friend") for r in group)
        if (not name or all(rem_map._notice(r) for r in group) or rem_map._service(group)
                or not (friend or rem_map.worth_a_page(sent, received))):
            out["skip"] += 1
            continue
        record = by_name.get(name.casefold()) if len(name.split()) >= 2 else None
        rank = _rank(group)
        if record:
            # An existing page already has material from elsewhere (mail); the new handle adds to it.
            out["merge"].append({"name": name, "record": record, "handles": handles, "rank": rank, "material": True})
            if write:
                _add_handles(notebook, record, handles)
        else:
            record = rem_map._record("people", name, handles[0])
            out["create"].append({"name": name, "record": record, "handles": handles, "rank": rank,
                                  "material": sent + received > 0})
            emails = ", ".join(h for h in handles if "@" in h)
            if write:
                notebook.stub_person(record, name, handles, **({"email": emails} if emails else {}))
            by_name[name.casefold()] = record
        by_handle.update({h.casefold(): record for h in handles})
    return out


def _retitle(notebook, record, name, write) -> bool:
    """A page titled by a nickname with no letter, digit or CJK in it (".", "^ ^", a filler blank) takes the
    source's better title, which is the remark or a plain placeholder (#3368). Handles and prose are untouched."""
    from .chat import usable_name
    lines = notebook.read(record).split("\n")
    title = lines[0][2:].strip() if lines and lines[0].startswith("# ") else ""
    if not name or usable_name(title) or name == title:
        return False
    if write:
        notebook.write(record, "\n".join([f"# {name}", *lines[1:]]))
    return True


def _orgs(notebook, org_rows, write):
    """Organisations from the domains of people who now have pages (the map's own rule, additive)."""
    from .map import _record
    from .org_map import _domain, map_orgs, organisation
    by_handle, _ = _roster(notebook)
    linked = [{"address": r["address"], "record": by_handle.get(r["address"].casefold()), "one_way": r.get("one_way")}
              for r in org_rows]
    if not write:
        existing = {d for record in notebook.list("orgs") for d in _domains(notebook.read(record))}
        talking = {organisation(_domain(r["address"])) for r in linked if r["record"] and not r["one_way"]
                   and _domain(r["address"])}
        return {"create": sorted(talking - existing), "merge": [], "known": len(talking & existing), "skip": 0}
    owner = (read_json(state_path(notebook.root, "map.json"), {}) or {}).get("owner")
    from .service import now
    orgs, created = map_orgs(notebook, linked, now().isoformat(), 0, _record, owner)
    return {"create": created, "merge": [], "known": len(orgs) - len(created), "skip": 0}


def _domains(page):
    import re
    section = page.partition("## Domains\n")[2].split("\n## ", 1)[0]
    return {d.casefold().rstrip(".") for d in re.findall(r"^- ([A-Za-z0-9.-]+)\s*$", section, re.M)}


def _projects(notebook, project_rows, write):
    from .map import file_project, project_groups
    out = {"create": [], "merge": [], "known": 0, "skip": 0}
    for identity, row in project_groups(project_rows, []).items():
        if not write:
            if _project_known(notebook, row):
                out["known"] += 1
            else:
                out["create"].append(row["name"])
            continue
        record, created = file_project(notebook, identity, row)
        if created:
            out["create"].append(record)
        else:
            out["known"] += 1
    return out


def _project_known(notebook, row):
    from .map import _project_pages, _record
    return bool(_project_pages(notebook, row["paths"], _record("projects", row["name"], row["name"]), row["name"]))


def _knowledge(notebook, knowledge_rows, write):
    from .map import _record
    out = {"create": [], "merge": [], "known": 0, "skip": 0}
    for row in knowledge_rows:
        record = _record("knowledge", row["name"], row["name"])
        if notebook.path(record).is_file():
            out["known"] += 1
            continue
        out["create"].append(record)
        if write:
            notebook.stub_topic(record, row["name"], row.get("aliases", ()))
    return out


APPLY = {"people": _people, "orgs": _orgs, "projects": _projects, "knowledge": _knowledge}


def plan(root: Path, source_rows: list[dict], kinds: tuple, *, write: bool) -> dict:
    """Apply (or, with write=False, only count) the rows of the asked kinds; people first so orgs can link to them."""
    notebook = Notebook(root)
    result = {}
    for kind in KIND_WORDS:
        if kind in kinds:
            result[kind] = APPLY[kind](notebook, [r for r in source_rows if ROW_KIND.get(r.get("kind")) == kind], write)
    if write and any("last" in r for r in source_rows):
        record_activity(root, source_rows)
    friends = [r for r in source_rows if r.get("friend")]
    if "people" in result and friends:
        # How much of the address book this machine holds chats for: the map says how to sync more (#3347).
        result["people"]["friends"] = len(friends)
        result["people"]["chats"] = sum(1 for r in friends if r.get("sent", 0) + r.get("received", 0))
    return result


ACTIVITY = "wechat-activity.json"   # per chat handle: when the owner last talked, who wrote last, 90-day count


def record_activity(root: Path, source_rows: list[dict]) -> None:
    """Keep each chat handle's activity where the reader finds it, so People sorts WeChat people by when the owner
    actually last talked with them (#3346). Rewritten by every map and night; a handle with no chat is left out."""
    from .files import write_json
    write_json(state_path(root, ACTIVITY), {
        row["address"]: {"last": row["last"], "mine": row.get("last_mine"), "n90": row.get("n90", 0),
                         "total": row.get("sent", 0) + row.get("received", 0)}
        for row in source_rows if row.get("last")})


def activity(root: Path) -> dict:
    """{people record: chat activity} for the pages that carry a chat handle with messages (#3346)."""
    found = read_json(state_path(root, ACTIVITY), {})
    if not found:
        return {}
    by_handle, _ = _roster(Notebook(root))
    out = {}
    for handle, entry in found.items():
        record = by_handle.get(handle.casefold())
        if record and entry.get("last", "") > out.get(record, {}).get("last", ""):
            out[record] = entry
    return out


def coverage(out: dict) -> str:
    """The address book against what was found (#3347): "微信好友 1,659 · 找到聊天 1,428 · 还缺 231"."""
    friends, chats = out.get("friends", 0), out.get("chats", 0)
    if not friends:
        return ""
    return f"微信好友 {friends:,} · 找到聊天 {chats:,} · 还缺 {friends - chats:,}"


def sync_hint(out: dict) -> str:
    """One line when WeChat for Mac holds chats for few of the owner's friends: how to bring the rest over."""
    friends, chats = out.get("friends", 0), out.get("chats", 0)
    if not friends or chats * 4 >= friends:
        return ""
    return (f"Only {chats} of {friends} WeChat friends have chats on this Mac. To give REM more, on your phone: "
            "WeChat → 设置 → 聊天 → 聊天记录迁移与备份 → 迁移到电脑.")


def touched(root: Path, source_rows: list[dict]) -> dict:
    """People pages a source reaches by handle: {'new': [...], 'existing': [...]}, new (never investigated) first."""
    from .map import _mapped_only
    notebook = Notebook(root)
    by_handle, _ = _roster(notebook)
    records = dict.fromkeys(by_handle[r["address"].casefold()] for r in source_rows
                            if r.get("kind") == "person" and r.get("address", "").casefold() in by_handle)
    resting = set(idle(root))
    new = [r for r in records if r not in resting and _mapped_only(notebook.read(r))]
    return {"new": new, "existing": [r for r in records if r not in new and r not in resting]}


# ---- onboarding: adding a source maps it, and the pages it touched are investigated first (#3331, part 2) ----
STATE = "onboard.json"               # per source: when it was mapped, with what scope, and what it made
ASKED = "people/onboarded.json"      # people pages onboarding touched; the people queue takes them first
# Read on this machine with no network, so the night may map them; they also grow on their own (new chat
# contacts), so they are mapped again every night. Mail and coding sources are mapped by init, by
# `co rem sources add` and by `co rem map`: a mail map is a 180-day metadata scan over the network.
NIGHTLY = ("wechat",)


def _scope(sub: dict) -> str:
    import json
    return json.dumps({key: sub.get(key) for key in ("since", "chats", "project", "about")}, sort_keys=True,
                      default=str)


def due(root: Path, subs: dict, *, night: bool) -> list[str]:
    """Sources to map now: never mapped, widened since, or (at night) the local ones that grow on their own."""
    done = read_json(state_path(root, STATE), {})
    names = []
    for name, sub in subs.items():
        if not (sub.get("enabled") and sub.get("consented") and yields(sub)):
            continue
        if night and sub.get("kind") not in NIGHTLY:
            continue
        if name not in done or done[name].get("scope") != _scope(sub) or sub.get("kind") in NIGHTLY:
            names.append(name)
    return names


def queue_first(root: Path, source: str, records: list) -> None:
    """Put pages first in the people queue. A record may come as a dict with `rank` (0 chats, 1 named friend,
    2 the rest) and `material` (False: nothing to read yet, so it is not investigated at all, #3347)."""
    from .files import write_json
    from .service import now
    asked = read_json(state_path(root, ASKED), {})
    for item in records:
        record = item if isinstance(item, str) else item["record"]
        entry = asked.setdefault(record, {"source": source, "at": now().isoformat()})
        if not isinstance(item, str):
            entry.update(rank=item.get("rank", 0), material=item.get("material", True))
    write_json(state_path(root, ASKED), asked)


def idle(root: Path) -> list[str]:
    """Pages onboarding made with nothing to read yet (an address-book friend with no chat on this machine).
    They stay 待了解 and cost no investigation until a chat or a mail arrives (#3347)."""
    return [record for record, asked in read_json(state_path(root, ASKED), {}).items() if asked.get("material") is False]


def _wake(root: Path, source: str, source_rows: list[dict]) -> None:
    """A friend whose page was idle and who now has a chat here becomes worth reading, first."""
    resting = set(idle(root))
    if not resting:
        return
    by_handle, _ = _roster(Notebook(root))
    woken = [{"record": by_handle[r["address"].casefold()], "rank": 0, "material": True} for r in source_rows
             if r.get("sent", 0) + r.get("received", 0) and by_handle.get(r.get("address", "").casefold()) in resting]
    if woken:
        queue_first(root, source, woken)


def onboard(root: Path, name: str, sub: dict, days: int, kinds: tuple = ()) -> dict:
    """Map one source, put the people pages it touched first in the queue, and record that it was mapped. The
    night, `co rem sources add` and `co rem map` all come here, so each leaves the same state behind (#3368)."""
    source_rows = rows(root, name, sub, days)
    result = plan(root, source_rows, kinds or yields(sub), write=True)
    _record(root, name, sub, result, source_rows)
    return result


def _record(root: Path, name: str, sub: dict, result: dict, source_rows: list[dict], *, backfilled=False) -> None:
    """After a map: the touched people pages go first in the queue, idle friends with a new chat wake, pages the
    source already held but the queue never saw are queued by rank, and the source is marked mapped."""
    from .files import write_json
    from .service import now
    people = result.get("people", {"create": [], "merge": []})
    queue_first(root, name, [*people["create"], *people["merge"]])
    _queue_unseen(root, name, source_rows)
    _wake(root, name, source_rows)
    done = read_json(state_path(root, STATE), {})
    done[name] = {"mapped_at": now().isoformat(), "scope": _scope(sub),
                  "created": {kind: len(out["create"]) for kind, out in result.items()},
                  "merged": len(people["merge"]), **({"backfilled": True} if backfilled else {}),
                  **({"chats": {"friends": people["friends"], "chats": people["chats"]}} if people.get("friends") else {})}
    write_json(state_path(root, STATE), done)


def _queue_unseen(root: Path, name: str, source_rows: list[dict]) -> None:
    """Pages a source reaches by handle that the people queue has never been told about: made by an older map
    that recorded nothing (rc14's WeChat map), queued now by the same rank as new ones (#3368)."""
    asked = read_json(state_path(root, ASKED), {})
    by_handle, _ = _roster(Notebook(root))
    seen, unseen = set(asked), []
    for row in source_rows:
        record = by_handle.get(row.get("address", "").casefold())
        if row.get("kind") != "person" or not record or record in seen:
            continue
        seen.add(record)
        talked = row.get("sent", 0) + row.get("received", 0) > 0
        unseen.append({"record": record, "rank": 0 if talked else (1 if row.get("remark") else 2), "material": talked})
    if unseen:
        queue_first(root, name, unseen)


def held_pages(root: Path, sub: dict) -> int:
    """How many people pages carry a handle of this source's kind: chat ids for a chat source, mail addresses for
    a mailbox. Status shows it, so a source with pages never reads as "never mapped" (#3368)."""
    from .files import EMAIL
    if "people" not in yields(sub):
        return 0
    if sub.get("kind") in NIGHTLY:
        # A WeChat id is wxid_… or one the activity file knows; a one-word alias ("Ostrowski") is not.
        known = {h.casefold() for h in read_json(state_path(root, ACTIVITY), {})}
        ours = lambda h: h.casefold().startswith("wxid_") or h.casefold() in known   # noqa: E731
    else:
        ours = EMAIL.fullmatch
    return sum(1 for person in Notebook(root).people()
               if any(ours(handle) for handle in (*person["aliases"], *person["emails"])))


def backfill(root: Path) -> list[str]:
    """After an upgrade: a local source that already holds pages but has no activity or onboarding record (pages
    made by an older map) gets both now, read from this machine with no model and no network, without making
    pages (#3368). It runs at most once per source; the night and `co rem map` keep it current after that."""
    from .files import MAP_DAYS
    from .service import subscriptions
    done = read_json(state_path(root, STATE), {})
    filled = []
    for name, sub in subscriptions(root).items():
        if (sub.get("kind") not in NIGHTLY or not (sub.get("enabled") and sub.get("consented"))
                or name in done or not held_pages(root, sub)):
            continue
        source_rows = rows(root, name, sub, MAP_DAYS)
        if not source_rows:
            continue
        record_activity(root, source_rows)
        result = plan(root, source_rows, yields(sub), write=False)
        result.get("people", {}).update(create=[], merge=[])    # counted only: a page build makes no pages
        _record(root, name, sub, result, source_rows, backfilled=True)
        filled.append(name)
    return filled


def run_due(root: Path, subs: dict, *, night: bool, days: int | None = None, only=()) -> list[str]:
    """Onboard every due source (or only the named ones); the records it created. An unreadable source is
    recorded where `co rem sources` shows it, not fatal."""
    from .files import MAP_DAYS, write_json
    created = []
    for name in (n for n in due(root, subs, night=night) if not only or n in only):
        try:
            result = onboard(root, name, subs[name], days or MAP_DAYS)
        except (RemError, OSError) as error:
            # One unreadable source must not stop the round; the reason stays where `co rem sources` shows it.
            done = read_json(state_path(root, STATE), {})
            done.setdefault(name, {})["error"] = f"{type(error).__name__}: {error}"[:300]
            write_json(state_path(root, STATE), done)
            continue
        created += [row["record"] if isinstance(row, dict) else row for out in result.values() for row in out["create"]]
    return created


def summary(root: Path, name: str) -> dict:
    """What `co rem sources` shows for one source: when it was mapped, what it made, what still waits."""
    from .people_pages import _stamp
    done = read_json(state_path(root, STATE), {}).get(name, {})
    investigated = read_json(state_path(root, "people/investigated.json"), {})
    waiting = [record for record, asked in read_json(state_path(root, ASKED), {}).items()
               if asked.get("source") == name and not (_stamp(investigated.get(record)) and
                                                       _stamp(investigated.get(record)) > _stamp(asked["at"]))]
    asked = read_json(state_path(root, ASKED), {})
    resting = [record for record, entry in asked.items() if entry.get("source") == name and entry.get("material") is False]
    waiting = [record for record in waiting if record not in set(resting)]
    hint, found = sync_hint(done.get("chats", {})), coverage(done.get("chats", {}))
    held = 0
    if not done.get("mapped_at"):
        from .service import subscriptions
        sub = subscriptions(root).get(name, {})
        held = held_pages(root, sub) if sub else 0
    mapped = done.get("mapped_at") or ("earlier" if held else "never")
    return {"mapped_at": mapped, "created": done.get("created", {}), "pages": held,
            "to_investigate": len(waiting), **({"coverage": found} if found else {}),
            **({"no_chats_yet": len(resting)} if resting else {}),
            **({"hint": hint} if hint else {}), **({"error": done["error"]} if done.get("error") else {})}

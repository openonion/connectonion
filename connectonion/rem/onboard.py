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
    for label, wanted in (("Also known as", [h for h in handles if "@" not in h]),
                          ("Email", [h for h in handles if "@" in h])):
        index = next((i for i, line in enumerate(lines) if line.startswith(f"- {label}:")), None)
        if not wanted or index is None:
            continue
        value = lines[index].split(":", 1)[1].strip()
        have = [] if value in ("", "Unknown") else [v.strip() for v in value.split(",")]
        lines[index] = f"- {label}: " + ", ".join(dict.fromkeys([*have, *wanted]))
    notebook.write(record, "\n".join(lines))


def _people(notebook, people_rows, write):
    from . import map as rem_map
    by_handle, by_name = _roster(notebook)
    out = {"create": [], "merge": [], "known": 0, "skip": 0}
    for group in rem_map._people_groups(people_rows):
        handles = [row["address"] for row in group]
        name = " ".join(str(next((r["name"] for r in group if r.get("name")), "")).split())
        sent, received = (sum(r.get(k, 0) for r in group) for k in ("sent", "received"))
        if any(h.casefold() in by_handle for h in handles):
            out["known"] += 1
            continue
        if (not name or all(rem_map._notice(r) for r in group) or rem_map._service(group)
                or not rem_map.worth_a_page(sent, received)):
            out["skip"] += 1
            continue
        record = by_name.get(name.casefold()) if len(name.split()) >= 2 else None
        if record:
            out["merge"].append({"name": name, "record": record, "handles": handles})
            if write:
                _add_handles(notebook, record, handles)
        else:
            record = rem_map._record("people", name, handles[0])
            out["create"].append({"name": name, "record": record, "handles": handles})
            emails = ", ".join(h for h in handles if "@" in h)
            if write:
                notebook.stub_person(record, name, handles, **({"email": emails} if emails else {}))
            by_name[name.casefold()] = record
        by_handle.update({h.casefold(): record for h in handles})
    return out


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
    return result


def touched(root: Path, source_rows: list[dict]) -> dict:
    """People pages a source reaches by handle: {'new': [...], 'existing': [...]}, new (never investigated) first."""
    from .map import _mapped_only
    notebook = Notebook(root)
    by_handle, _ = _roster(notebook)
    records = dict.fromkeys(by_handle[r["address"].casefold()] for r in source_rows
                            if r.get("kind") == "person" and r.get("address", "").casefold() in by_handle)
    new = [r for r in records if _mapped_only(notebook.read(r))]
    return {"new": new, "existing": [r for r in records if r not in new]}


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


def queue_first(root: Path, source: str, records: list[str]) -> None:
    from .files import write_json
    from .service import now
    asked = read_json(state_path(root, ASKED), {})
    for record in records:
        asked.setdefault(record, {"source": source, "at": now().isoformat()})
    write_json(state_path(root, ASKED), asked)


def onboard(root: Path, name: str, sub: dict, days: int) -> dict:
    """Map one source, put the people pages it touched first in the queue, and record that it was mapped."""
    from .files import write_json
    from .service import now
    result = plan(root, rows(root, name, sub, days), yields(sub), write=True)
    people = result.get("people", {"create": [], "merge": []})
    queue_first(root, name, [row["record"] for row in (*people["create"], *people["merge"])])
    done = read_json(state_path(root, STATE), {})
    done[name] = {"mapped_at": now().isoformat(), "scope": _scope(sub),
                  "created": {kind: len(out["create"]) for kind, out in result.items()},
                  "merged": len(people["merge"])}
    write_json(state_path(root, STATE), done)
    return result


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
    return {"mapped_at": done.get("mapped_at") or "never", "created": done.get("created", {}),
            "to_investigate": len(waiting), **({"error": done["error"]} if done.get("error") else {})}

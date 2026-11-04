"""One person on two pages (#2724): code finds similar pages, a model decides.

The map makes a page per address, so a person who writes from two addresses,
or under a nickname, can become two pages with their facts split between them.
Code cannot tell one person from two who share a name, or from an assistant
whose address sits on someone's Email line. So code only finds pairs that look
alike -- a name or alias in common, one name inside the other, or an address
one page lists that the other was made from -- and a model reads both pages and
each one's own mail (how they write, who they write to, about what) and answers
yes or no. Yes folds the less written page into the more written one
(`merge.merge_into`); no keeps both. Every answer is kept in
`.state/same-person.json`, so a pair is asked once.
"""

from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path

from .files import Notebook, maintenance_lock, read_json, state_path, write_json

SKILL = "rem-same-person"
VERDICTS = "same-person.json"
# Pairs judged per daily run: one model call each.
PAIRS_PER_RUN = 2
# Each page's own mail shown to the judge: enough to see how they write.
MAILS_PER_PAGE = 6
MAIL_CHARS = 1500
ROLES = ["their own", "assistant or delegate", "shared or family mailbox", "team or role inbox",
         "colleague or relative", "none shared", "unclear"]
SCHEMA = {"type": "object", "properties": {
    "same": {"type": "boolean"}, "address_role": {"type": "string", "enum": ROLES},
    "reason": {"type": "string"}}, "required": ["same", "address_role", "reason"], "additionalProperties": False}


def _names(person: dict) -> set[str]:
    """The title and aliases as name strings; an address or Unknown is no name."""
    names = {person["title"], *(inner for inner in re.findall(r"\(([^()]*)\)", person["title"])),
             *person["aliases"]}
    return {re.sub(r"\s*\([^()]*\)|\s*\[W?\d+\]", "", name).strip().casefold() for name in names
            if name and "@" not in name and name.strip().casefold() != "unknown"} - {""}


def _alike(one: dict, other: dict) -> str:
    """Why two roster entries may be one person, or '' when nothing ties them."""
    mine, theirs = _names(one), _names(other)
    if mine & theirs:
        return "same name: " + sorted(mine & theirs)[0]
    words = {word for name in mine for word in re.findall(r"\w+", name) if len(word) > 1}
    other_words = {word for name in theirs for word in re.findall(r"\w+", name) if len(word) > 1}
    if words and other_words and (words <= other_words or other_words <= words):
        return "one name inside the other"
    return ""


def candidates(root: Path) -> list[dict]:
    """Pairs of people pages that look alike and have not been judged, by code alone."""
    state = read_json(state_path(root, "map.json"), {})
    owner = (state.get("owner") or {}).get("record")
    mapped = {address.casefold(): row["record"] for row in state.get("people", []) if row.get("record")
              for address in row.get("addresses") or [row.get("address") or ""] if address}
    judged = read_json(state_path(root, VERDICTS), {})
    roster = [person for person in Notebook(root).people() if person["path"] != owner]
    pairs = {}
    for i, one in enumerate(roster):
        for other in roster[i + 1:]:
            key = "|".join(sorted([one["path"], other["path"]]))
            shared = [email for email in one["emails"] if mapped.get(email.casefold()) == other["path"]] + [
                email for email in other["emails"] if mapped.get(email.casefold()) == one["path"]]
            why = (f"one page lists {shared[0]}, the address the other was made from" if shared else "") \
                or _alike(one, other)
            if why and _due(judged.get(key)):
                pairs[key] = {"pages": key.split("|"), "why": why}
    return list(pairs.values())


def _due(verdict: dict | None) -> bool:
    """Never judged, or a judgement that failed before today: answered pairs are not asked again."""
    return not verdict or ("same" not in verdict and verdict.get("failed", "") < date.today().isoformat())


def _own_mail(root: Path, record: str, emails: list[str]) -> list[dict]:
    """The page's own words: mail sent from its addresses, newest first."""
    from .mail_archive import person_material
    found = person_material(root, record, handles=emails)
    addresses = {email.casefold() for email in emails}
    items = [item for rows in (found[0].values() if found else []) for item in rows
             if any(address in str(item["speaker"]).casefold() for address in addresses)]
    items.sort(key=lambda item: item["timestamp"], reverse=True)
    return [{"from": item["speaker"], "to": item["participants"]["to"], "date": item["timestamp"],
             "subject": item["subject"], "text": item["text"][:MAIL_CHARS]} for item in items[:MAILS_PER_PAGE]]


def packet(root: Path, pair: dict) -> str:
    """The skill, then both pages and each one's own mail."""
    from ..skills_catalog import useful_skills_dir
    notebook = Notebook(root)
    roster = {person["path"]: person for person in notebook.people()}
    pages = [{"record": record, "page": notebook.read(record),
              "own_mail": _own_mail(root, record, roster[record]["emails"])} for record in pair["pages"]]
    skill = (useful_skills_dir() / SKILL / "SKILL.md").read_text(encoding="utf-8")
    return skill + "\n\n---\n\nWhy code put them side by side: " + pair["why"] + "\n\n" + json.dumps(
        pages, ensure_ascii=False, indent=1)


def _verdict(result: dict) -> dict:
    from .runner import RunFailed
    try:
        # Codex returns the schema's JSON; a Claude Code turn may put a fence or a sentence around it.
        text = str(result["result"])
        answer = json.loads(text[text.find("{"):text.rfind("}") + 1])
    except json.JSONDecodeError as error:
        raise RunFailed("Same-person judgement returned invalid JSON", result.get("usage")) from error
    if not isinstance(answer, dict) or not isinstance(answer.get("same"), bool) or answer.get("address_role") not in ROLES:
        raise RunFailed("Same-person judgement returned an invalid answer", result.get("usage"))
    return answer


def judge(root: Path, config: dict, *, run=None, limit: int = PAIRS_PER_RUN, say=lambda text: None) -> list[dict]:
    """Ask about up to `limit` pairs; fold the ones answered yes. Returns one row per pair asked."""
    from .merge import merge_into, weight
    from .runner import RunFailed, run_claim_task
    run = run or run_claim_task
    rows = []
    for _ in range(limit):
        # Found again after every answer: a fold removes a page that later pairs named.
        pair = next(iter(candidates(root)), None)
        if not pair:
            break
        say(f"Same person? {pair['pages'][0]} and {pair['pages'][1]}")
        workspace = state_path(root, "same-person")
        workspace.mkdir(parents=True, exist_ok=True)
        try:
            result = run(workspace, packet(root, pair), config, "same-person")
            answer = _verdict(result)
        except RunFailed as error:
            # Asked again tomorrow, so a pair that keeps failing does not hold back
            # the pairs behind it every run (#2741).
            rows.append(_failed(root, pair, error))
            continue
        rows.append(check({"root": str(root), "pair": pair}, result))
    return rows


def prepare(root, pair, *, directory):
    output = directory / "candidate.json"
    return {"root": str(root), "pair": pair, "candidate": str(output),
            "before": {record: Notebook(root).read(record) for record in pair["pages"]},
            "prompt": packet(root, pair) + f"\nWrite only the JSON answer to {output}."}


def check(task, result, *, lock_held=False):
    from contextlib import nullcontext
    from .merge import merge_into, weight
    root, pair = Path(task["root"]), task["pair"]
    answer = _verdict(result)
    row = {**pair, **answer, "date": date.today().isoformat(), "usage": result.get("usage")}
    with nullcontext() if lock_held else maintenance_lock(root):
        notebook = Notebook(root)
        if answer["same"] and all(notebook.path(record).is_file() for record in pair["pages"]):
            kept, old = sorted(pair["pages"], key=lambda record: (weight(notebook.read(record)), record),
                               reverse=True)
            merge_into(notebook, kept, old, "same person: " + answer["reason"][:200])
            row["kept"] = kept
        verdicts = read_json(state_path(root, VERDICTS), {})
        verdicts["|".join(pair["pages"])] = {key: row[key] for key in ("why", "same", "address_role", "reason",
                                                                     "date") if key in row}
        write_json(state_path(root, VERDICTS), verdicts)
    return {**row, "changed": [row["kept"]] if row.get("kept") else []}


def _failed(root: Path, pair: dict, error: Exception) -> dict:
    with maintenance_lock(root):
        verdicts = read_json(state_path(root, VERDICTS), {})
        verdicts["|".join(pair["pages"])] = {"why": pair["why"], "failed": date.today().isoformat(),
                                             "error": str(error)[:300]}
        write_json(state_path(root, VERDICTS), verdicts)
    return {**pair, "outcome": "failed", "error": str(error)[:300], "usage": getattr(error, "usage", None)}

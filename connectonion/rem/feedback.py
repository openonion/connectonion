"""Per-page processing receipts for attributed reflections and review decisions.

These receipts describe accepted processing, not proof that an assertion is true.
Raw records remain authoritative; a compressed view is never a new event.
"""

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from .files import Notebook, RemError, read_json, state_path

TERMINAL = {"applied", "no_change"}
RECEIPTS = "rem_feedback_receipts"


def _items(root: Path) -> list[dict]:
    from .reflections import records
    from .reviews import context

    rows = [{"role": "reflection", "source": "reflection:" + row["id"],
             "record": row["subject"], "timestamp": row["recorded_at"],
             "references": row.get("sources", []), "text": json.dumps(row, ensure_ascii=False)}
            for row in records(root)]
    return [*rows, *context(root)]


def _legacy_sources(root: Path, processed: set, items: list[dict]) -> tuple[set, set]:
    """Expand only a retained summary that exactly matches its old consumed ID.

    Old consumed state is kept as an operational compatibility boundary; it
    does not establish that those historical assertions were applied correctly.
    """
    actual = {item["source"]: json.loads(item["text"]) for item in items if item["role"] == "reflection"}
    result = set(processed)
    matched = set()
    for path in state_path(root, "reflection-summaries").glob("*.json"):
        compact = read_json(state_path(root, "reflection-summaries/" + path.name), {})
        fields, values = compact.get("fields"), compact.get("rows")
        if not (isinstance(fields, list) and all(isinstance(k, str) for k in fields)
                and len(fields) == len(set(fields)) and isinstance(values, list)
                and all(isinstance(row, list) and len(row) == len(fields) for row in values)):
            continue
        restored = [dict(zip(fields, row)) for row in values]
        revision = hashlib.sha256(json.dumps(restored, sort_keys=True).encode()).hexdigest()
        if ("reflection-summary:" + path.stem + ":" + revision in processed
                and all(actual.get("reflection:" + str(row.get("id"))) == row for row in restored)):
            matched.add("reflection-summary:" + path.stem + ":" + revision)
            result.update("reflection:" + row["id"] for row in restored)
    unresolved = {source.split(":")[1] for source in processed
                  if source.startswith("reflection-summary:") and source not in matched}
    return result, unresolved


def targets(item: dict) -> list[str]:
    return list(dict.fromkeys([item["record"]] if item.get("record") else item.get("subjects", [])))


def same_revision(entry: dict, item: dict) -> bool:
    return any(row.get("source") == item["source"] and
               row.get("feedback_revision") == item["feedback_revision"]
               for row in entry.get("material", []))


def _remaining(progress: dict, item: dict) -> list[str]:
    receipt = progress.get(RECEIPTS, {}).get(item["source"], {})
    done = receipt.get("targets", {}) if receipt.get("revision") == item["feedback_revision"] else {}
    return [page for page in targets(item) if done.get(page, {}).get("outcome") not in TERMINAL]


def plan(root: Path, progress: dict, *, retry_pages=()) -> tuple[list[dict], list[dict]]:
    """Pending immutable events, eligible pages and explicit deferral reasons."""
    from .refusals import due_for_retry, refused_pages

    rows = _items(root)
    recover(root, progress, rows)
    processed, unresolved = _legacy_sources(root, set(progress.get("rem_local_material", [])), rows)
    refused, due = refused_pages(root), due_for_retry(root)
    eligible, deferred = [], []
    for row in rows:
        item = {**row, "feedback_revision": hashlib.sha256(row["text"].encode()).hexdigest()}
        if item["source"] in processed and item["source"] not in progress.get(RECEIPTS, {}):
            continue
        available = []
        for page in _remaining(progress, item):
            try:
                exists = Notebook(root).path(page).is_file()
            except RemError:
                exists = False
            held = refused.get(page, {})
            reason = ("Target page is missing or invalid" if not exists else
                      "Legacy summary membership cannot be reconstructed; inspect retained feedback before replay" if
                      item["role"] == "reflection" and hashlib.sha256(page.encode()).hexdigest() in unresolved
                      and item["source"] not in progress.get(RECEIPTS, {}) else
                      "Same feedback awaits refusal retry eligibility" if
                      same_revision(held, item) and page not in due and page not in retry_pages else "")
            if reason:
                deferred.append({"source": item["source"], "record": page, "reason": reason})
            else:
                available.append(page)
        if available:
            eligible.append({**item, "feedback_pending_targets": available})
    return eligible, deferred


def prepare_promotion(root: Path, page: str, text: str, items: list[dict], *, changed=True) -> None:
    """Native runner accepted this exact postimage; page replacement happens next.

    A prepared entry alone proves nothing. Recovery requires the same saved
    postimage and the same retained event revision. No source text is copied.
    Caller holds the maintenance/promotion lock.
    """
    from .files import write_json
    selected = [{key: item[key] for key in ("source", "feedback_revision", "record", "subjects",
                                          "feedback_pending_targets") if key in item}
                for item in items if item.get("feedback_revision") and
                page in item.get("feedback_pending_targets", [])]
    path = state_path(root, "feedback-promotions/" + hashlib.sha256(page.encode()).hexdigest() + ".json")
    if not selected:
        path.unlink(missing_ok=True)
        return
    write_json(path, {"page": page, "page_sha256": hashlib.sha256(text.encode()).hexdigest(),
                      "changed": changed, "items": selected})


def recover(root: Path, progress: dict, rows: list[dict]) -> None:
    """Reconcile a native promotion interrupted before its sync/daily callback."""
    from .files import write_json
    current = {row["source"]: hashlib.sha256(row["text"].encode()).hexdigest() for row in rows}
    for path in state_path(root, "feedback-promotions").glob("*.json"):
        proof = read_json(state_path(root, "feedback-promotions/" + path.name), {})
        page = proof.get("page", "")
        try:
            matches = hashlib.sha256(Notebook(root).read(page).encode()).hexdigest() == proof.get("page_sha256")
        except RemError:
            matches = False
        relevant = [item for item in proof.get("items", [])
                    if current.get(item.get("source")) == item.get("feedback_revision")]
        if matches and relevant:
            accepted(root, progress, relevant, page, proof.get("changed", True))
            from .refusals import forget_refusal
            forget_refusal(root, page, [item["source"] for item in relevant])
            write_json(state_path(root, "progress.json"), progress)
        path.unlink()


def finish(root: Path, progress: dict, items: list[dict], page: str, result: dict) -> None:
    """Shared by sync and the daily retry: acknowledge only an accepted target."""
    from .refusals import forget_refusal, material_sources, remember_refusal
    relevant = [item for item in items if page in item.get("feedback_pending_targets", [])]
    sources = material_sources(relevant)
    if result.get("refused"):
        remember_refusal(root, page, sources, result["refused"], stage="maintain", material=relevant)
    else:
        accepted(root, progress, relevant, page, page in result.get("changed", []))
        forget_refusal(root, page, sources)
    synchronize(progress, items)
    from .files import write_json
    write_json(state_path(root, "progress.json"), progress)


def synchronize(progress: dict, items: list[dict]) -> None:
    """Never let a batch cursor imply that an unattempted feedback page ran."""
    for key in ("rem_local_material", "rem_seen_source_ids"):
        consumed = set(progress.get(key, []))
        for item in items:
            if not _remaining(progress, item):
                consumed.add(item["source"])
            else:
                consumed.discard(item["source"])
        progress[key] = sorted(consumed)


def accepted(root: Path, progress: dict, items: list[dict], page: str, changed: bool) -> None:
    """Caller has accepted this exact page turn, including an assessed no-change."""
    receipts = dict(progress.get(RECEIPTS, {}))
    for item in items:
        if page not in item["feedback_pending_targets"]:
            continue
        old = receipts.get(item["source"], {})
        done = dict(old.get("targets", {})) if old.get("revision") == item["feedback_revision"] else {}
        done[page] = {"outcome": "applied" if changed else "no_change",
                      "at": datetime.now(timezone.utc).isoformat(),
                      "page_sha256": hashlib.sha256(Notebook(root).read(page).encode()).hexdigest()}
        receipts[item["source"]] = {"revision": item["feedback_revision"], "targets": done}
    progress[RECEIPTS] = receipts
    synchronize(progress, items)

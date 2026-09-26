"""One subject, every source at once: the first-run stage, and the daily deep pass.

Identity is the input. The subject arrives with its handles, every handle is
searched in every source, and a handle that finds nothing is reported rather
than passed over -- "searched Gmail for X, none" and "did not mention Gmail"
read alike on a page and mean different things.
"""

import hashlib
import json
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .config import read_config
from .files import Notebook, WikiError, maintenance_lock
from .mail import _address, correspondent, strip_noise, strip_quoted
from .source import KINDS, collect

MAIL_KINDS = ("outlook", "gmail")


def quick_evidence(items: list[dict], *, max_items: int = 24,
                   chars_per_item: int = 2500) -> list[dict]:
    """A bounded first look, with source diversity and recent items.

    This is explicitly partial evidence. A quick onboarding turn should not
    quietly spawn a sequence of expensive extraction agents for the owner.
    """
    latest = list(reversed(items))
    chosen, seen = [], set()
    for item in latest:
        source = item.get("source", "").split(":", 1)[0]
        if source not in seen:
            chosen.append(item)
            seen.add(source)
    for item in latest:
        if len(chosen) >= max_items:
            break
        if item not in chosen:
            chosen.append(item)
    selected = []
    for item in sorted(chosen[:max_items], key=lambda row: row["timestamp"]):
        copy = dict(item)
        body = copy.get("text", "")
        if len(body) > chars_per_item:
            copy["text"] = body[:chars_per_item] + "\n[truncated for quick first-pass review]"
        selected.append(copy)
    return selected


def project_paths(page: str) -> list[str]:
    """Recover mapped project directories after a cited investigation page.

    Citation markers belong to Markdown, not to the path used for local reads
    or session matching on the next run.
    """
    section = page.partition("## Paths\n")[2].split("\n## ", 1)[0]
    return [re.sub(r"\s+\[\d+\](?:\s*\[\d+\])*\s*$", "", line[2:].strip())
            for line in section.splitlines() if line.startswith("- /")]


def project_file_inventory(page: str, *, max_files: int = 60) -> list[str]:
    """Give a project investigation bounded file leads, never file contents.

    Session metadata can name a project with no user messages. A short inventory
    lets the model pick evidence from the recorded path without repeatedly
    searching the user's home directory. File names alone prove no project fact.
    """
    roots = [Path(path).expanduser() for path in project_paths(page)]
    leads = []
    excluded = {".git", ".venv", "venv", "node_modules", "__pycache__", "dist", "build", ".state"}
    suffixes = {".md", ".txt", ".toml", ".py", ".js", ".ts", ".tsx", ".html", ".css", ".swift", ".go", ".rs"}
    for root in roots[:4]:
        resolved = root.resolve()
        if (not root.is_dir() or root.is_symlink() or resolved == Path.home()
                or resolved in Path.home().parents or len(resolved.parts) < 3):
            continue
        seen = 0
        for current, dirs, files in os.walk(root, followlinks=False):
            depth = len(Path(current).relative_to(root).parts)
            dirs[:] = sorted(d for d in dirs if d not in excluded and not d.startswith(".")
                             and not (Path(current) / d).is_symlink()) if depth < 4 else []
            for name in sorted(files):
                if name.startswith(".") or Path(name).suffix.lower() not in suffixes:
                    continue
                if any(word in name.lower() for word in ("secret", "password", "credential", "private", "token")):
                    continue
                path = Path(current) / name
                if path.is_symlink():
                    continue
                leads.append(str(path))
                seen += 1
                if seen >= 1000:
                    break
            if seen >= 1000:
                break
    def priority(path):
        name = Path(path).name.lower()
        return (0 if name.startswith("readme") else
                1 if name in ("pyproject.toml", "package.json") else
                2 if "wiki" in path.lower() else 3, len(Path(path).parts), path)
    return sorted(set(leads), key=priority)[:max_files]


def _patient(call, *args, attempts: int = 4):
    """One transient timeout must not end a ten-minute gather.

    The owner's first investigation died on the 300th body fetch with a
    ReadTimeout from Graph -- one slow response, and everything gathered
    before it was thrown away. Retried with a short backoff; a provider that
    is really down still fails, after four tries rather than one.
    """
    import time
    for attempt in range(attempts):
        try:
            return call(*args)
        except Exception as error:  # noqa: BLE001 -- the providers raise their own timeout types
            name = type(error).__name__.lower()
            transient = any(part in name for part in ("timeout", "connecterror", "connectionerror")) \
                or "timed out" in str(error).lower()
            if not transient or attempt == attempts - 1:
                raise
            time.sleep(2 ** attempt)


def _download(client, email_id: str, folder: str):
    """The two mailboxes save attachments through different doors.

    Outlook: `download_attachments(email_id, out_dir)` -> list of paths.
    Gmail (its mailbox mixin): `download_attachments(email_id, directory, *,
    all_attachments=...)` -> a result dict, because it also reports partial
    saves and budget stops. Both are asked the way they expect.
    """
    import inspect
    parameters = inspect.signature(client.download_attachments).parameters
    if "all_attachments" in parameters:
        return client.download_attachments(email_id, folder, all_attachments=True)
    return client.download_attachments(email_id, folder)


def _saved_paths(result) -> list[str]:
    """Whatever a download returned, the files that are now on disk."""
    if isinstance(result, dict):
        # Gmail's mixin: {'items': [{'status': 'saved', 'path': ...} | {'status': 'failed', ...}],
        # 'complete': bool}. A row without a path was not saved; it is not a file.
        return [str(row["path"]) for row in result.get("items") or []
                if isinstance(row, dict) and row.get("path") and row.get("status", "saved") == "saved"]
    return [str(f) for f in (result or [])]


def _matches(row: dict, handles: list[str], mine: set) -> bool:
    haystack = " ".join([correspondent(row, mine), str(row.get("from", "")), str(row.get("to", "")),
                         str(row.get("subject", ""))]).lower()
    return any(handle in haystack for handle in handles)


def gather(subject: str, handles: list[str], *, days: int, clients: dict, subscriptions: dict,
           progress=None, attachments_dir: Path | None = None,
           sent_only: bool = False, mail_skipped: str = "", stage_progress=None,
           quick: bool = False) -> tuple[list[dict], list[str]]:
    """Everything every source holds about the subject, oldest first, plus what was searched.

    `sent_only` is the owner's own page: every message in a mailbox involves
    the owner, so "mail about the owner" is the whole mailbox. What the owner
    wrote is what describes them; what others sent them describes the others.
    """
    handles = [h.strip().lower() for h in handles if h.strip()]
    if days < 1 or not handles:
        raise WikiError("Investigation needs a positive day window and at least one subject handle")
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=days)
    items, coverage = [], []
    own_addresses = set()
    for kind, client in clients.items():
        mine = {a.lower() for a in client.my_addresses()}
        if sent_only:
            # Each mailbox knows only its own login. The owner's other addresses
            # are the owner too, not correspondents to search the server for: a
            # first `investigate me` searched for them and found 6 of ~150 mails.
            mine |= {h for h in handles if "@" in h}
        own_addresses.update(mine)
        emails = sorted({h for h in handles if "@" in h and h not in mine})
        if emails and hasattr(client, "list_with"):
            # Ask the server for this person's mail. Listing the whole window and
            # filtering took minutes per person, and a week past the 200-row cap
            # lost mail without saying so; this is complete and takes a second.
            hit, taken = [], set()
            for address in emails:
                for r in _patient(client.list_with, address, start.isoformat(), end.isoformat()) or []:
                    if r["id"] not in taken:
                        taken.add(r["id"])
                        hit.append(r)
            if progress:
                progress(kind, end, len(hit))
            searched = f"searched on the server for {', '.join(emails)}"
        else:
            rows, cursor = [], start
            while cursor < end:
                stop = min(cursor + timedelta(days=7), end)
                rows += _patient(client.list_between, cursor.isoformat(), stop.isoformat(), 200) or []
                if progress:
                    progress(kind, stop, len(rows))
                cursor = stop
            hit = [r for r in rows if _matches(r, handles, mine)]
            searched = f"scanned {len(rows)} mails"
            if sent_only:
                hit = [r for r in hit if _address(r["from"]) in mine]
                searched += ", kept the owner's own sent mail"
        attached = 0
        mail_to_read = sorted(hit, key=lambda r: str(r["date"]))
        if quick:
            mail_to_read = mail_to_read[-12:]
        for number, r in enumerate(mail_to_read, 1):
            body = _patient(client.get_email_body, r["id"])
            head, _, rest = body.partition("--- Email Body ---")
            body = head + "--- Email Body ---" + strip_noise(strip_quoted(rest)) if rest else strip_noise(strip_quoted(body))
            own = _address(r["from"]) in mine or "@" not in _address(r["from"])
            short = hashlib.sha256(r["id"].encode()).hexdigest()[:12]
            items.append({"role": "user" if own else "other", "speaker": r["from"],
                          "text": body, "timestamp": str(r["date"]),
                          "subject": r.get("subject", ""), "source": f"{kind}:{short}"})
            if attachments_dir is not None and hasattr(client, "download_attachments"):
                from .attachments import extract_text
                folder = attachments_dir / kind / short
                try:
                    folder.mkdir(parents=True, exist_ok=True)
                    paths = _saved_paths(_patient(_download, client, r["id"], str(folder)))
                except Exception as error:  # noqa: BLE001 -- one bad attachment is not the run
                    paths = []
                    coverage.append(f"{kind}:{short}: attachments could not be saved ({type(error).__name__})")
                for saved in paths or []:
                    attached += 1
                    items.append({"role": "attachment", "speaker": r["from"], "timestamp": str(r["date"]),
                                  "subject": f"{r.get('subject', '')} — {Path(saved).name}",
                                  "text": extract_text(Path(saved), limit=None), "file": saved,
                                  "source": f"{kind}:{short}:{Path(saved).name}"})
            if stage_progress and (number % 10 == 0 or number == len(mail_to_read)):
                stage_progress(f"gathering {kind} mail", number, len(mail_to_read))
        coverage.append(f"{kind} ({', '.join(sorted(mine))}): {searched} over {days} days, "
                        f"{len(hit)} matched, {len(mail_to_read)} bodies read"
                        + (" (recent quick sample)" if quick else "")
                        + f", {attached} attachments read")
    for kind in ("outlook", "gmail"):
        if kind not in clients:
            # Say it. A mailbox left out used to vanish from coverage, so the model
            # and the reader could not tell "no mail with this person" from "not asked".
            # A mailbox left out on purpose says why; "not connected" sent a user
            # to log in again for a project page that simply does not read mail.
            why = (mail_skipped or ("unsubscribed by the user" if subscriptions.get(kind, {}).get("unsubscribed")
                   else f"not connected (co auth {'google' if kind == 'gmail' else 'microsoft'})"))
            coverage.append(f"{kind}: {why}; not searched")
    for name, sub in subscriptions.items():
        if sub.get("kind") not in KINDS:
            continue
        if sub.get("enabled") is False:
            coverage.append(f"{name}: disabled, not searched")
            continue
        if not Path(sub.get("root", "")).is_dir():
            coverage.append(f"{name}: source directory unavailable, not searched")
            continue
        scoped = {**sub, "enabled": True, "consented": True, "since": start.isoformat()}
        cursor, scanned, picked = {}, 0, []
        is_owner = bool(own_addresses.intersection(handles))
        try:
            while True:
                batch = collect(scoped, cursor, 40, 200_000)
                scanned += len(batch.items)
                picked.extend(i for i in batch.items if is_owner or any(
                    h in (i["text"] + " " + i.get("project", "")).lower() for h in handles))
                if batch.progress == cursor:
                    break
                cursor = batch.progress
                if stage_progress:
                    stage_progress(f"gathering {name} sessions", scanned)
        except WikiError as error:
            coverage.append(f"{name}: unreadable ({error})")
        related = len(picked)
        if quick:
            picked = picked[-12:]
        coverage.append(f"{name}: {scanned} messages in window, {related} related to subject, "
                        f"{len(picked)} read"
                        + (" (recent quick sample)" if quick else "")
                        + (" (account owner's own messages)" if is_owner else " (handle or project match)"))
        items += picked
    items.sort(key=lambda i: i["timestamp"])
    return items, coverage


def _split_item(item: dict, limit_chars: int):
    """Split a long document without losing its text, source or date."""
    if len(json.dumps([item], ensure_ascii=False)) <= limit_chars:
        yield item
        return
    if len(json.dumps([{**item, "text": ""}], ensure_ascii=False)) >= limit_chars:
        raise WikiError("Extraction character limit is too small for source metadata; "
                        "increase limits.extract_chars_per_batch")
    remaining = item["text"]
    while remaining:
        low, high = 0, min(len(remaining), limit_chars)
        while low < high:
            middle = (low + high + 1) // 2
            part = {**item, "text": remaining[:middle]}
            if len(json.dumps([part], ensure_ascii=False)) <= limit_chars:
                low = middle
            else:
                high = middle - 1
        if not low:
            raise WikiError("Extraction character limit cannot fit source text; "
                            "increase limits.extract_chars_per_batch")
        yield {**item, "text": remaining[:low]}
        remaining = remaining[low:]


def digest_in_chunks(items: list[dict], config: dict, extractor=None, *, root: Path | None = None,
                     max_calls=None, progress=None) -> tuple[list[dict], dict]:
    """Oldest first, each chunk within the extract limits, one digest item per chunk."""
    from .extract import NOTHING, extraction_instructions, extraction_item, run_extract
    from .files import read_json, state_path, write_json
    limits = config["limits"]
    if extractor is None:
        if root is None:
            raise WikiError("Wiki root is required for model extraction")
        extractor = lambda chunk, settings, kind: run_extract(chunk, settings, kind, root=root)
    chunks, current, size = [], [], 2  # The serialized list's brackets count too.
    for item in items:
        for part in _split_item(item, limits["extract_chars_per_batch"]):
            n = len(json.dumps(part, ensure_ascii=False))
            if current and (len(current) >= limits["extract_items_per_batch"]
                            or size + 2 + n > limits["extract_chars_per_batch"]):
                chunks.append(current)
                current, size = [], 2
            size += n + (2 if current else 0)
            current.append(part)
    if current:
        chunks.append(current)
    if max_calls is not None and len(chunks) > max_calls:
        raise WikiError("Extraction exceeds remaining call budget; page preserved")
    digests, usage = [], {}
    for number, chunk in enumerate(chunks, 1):
        kinds = {i["source"].split(":")[0] for i in chunk}
        kind = kinds.pop() if len(kinds) == 1 else ""
        checkpoint = None
        if root is not None:
            # A cancelled page investigation must not pay for every completed
            # digest again. Hash the material, model settings and Skill text so
            # a changed source or prompt cannot reuse stale conclusions.
            fingerprint = hashlib.sha256(json.dumps(
                [chunk, config.get("runner"), config.get("model"), extraction_instructions(kind)],
                ensure_ascii=False, sort_keys=True).encode()).hexdigest()
            checkpoint = state_path(root, f"extracts/investigate/{fingerprint}.json")
        saved = read_json(checkpoint, {}) if checkpoint else {}
        if isinstance(saved, dict) and isinstance(saved.get("notes"), str) and saved["notes"].strip():
            out = {"notes": saved["notes"], "usage": None}
        else:
            out = extractor(chunk, config, kind)
            if checkpoint and isinstance(out.get("notes"), str) and out["notes"].strip():
                write_json(checkpoint, {"notes": out["notes"]})
        for key, value in (out.get("usage") or {}).items():
            usage[key] = usage.get(key, 0) + value
        if (out.get("notes") or "").strip() != NOTHING:
            digests.append(extraction_item(out["notes"].strip(), chunk))
        if progress:
            progress("extracting long evidence", number, len(chunks), dict(usage))
    return digests, usage


def investigate(root: Path, record: str, subject: str, handles: list[str], *, days: int,
                clients: dict, subscriptions: dict, runner=None, extractor=None, progress=None, max_calls=None,
                sent_only: bool = False, mail_skipped: str = "", stage_progress=None,
                quick: bool = False) -> dict:
    """Fill the page's gaps from everything gathered; the page itself is the first input."""
    notebook = Notebook(root)
    if not notebook.path(record).is_file():
        raise WikiError(f"{record} does not exist; create it with `co wiki stub` first")
    if stage_progress:
        stage_progress("gathering sources")
    items, coverage = gather(subject, handles, days=days, clients=clients, subscriptions=subscriptions,
                             progress=progress, attachments_dir=root / ".state" / "attachments",
                             sent_only=sent_only, mail_skipped=mail_skipped, stage_progress=stage_progress,
                             quick=quick)
    coverage.append(f"Requested investigation window: {days} days ending "
                    f"{datetime.now(timezone.utc).date().isoformat()}")
    available_items = len(items)
    if quick:
        items = quick_evidence(items)
        coverage.append(f"Quick first pass: reviewed {len(items)} of {available_items} gathered items; "
                        "individual texts capped at 2,500 characters. Other material was not evaluated; "
                        "do not claim comprehensive coverage or resolve unsupported conflicts.")
    if record.startswith("projects/"):
        leads = project_file_inventory(notebook.read(record))
        if leads:
            items.append({"role": "project-inventory", "source": "investigation:project-inventory",
                          "text": "Candidate local evidence files, not proof of their contents:\n" +
                                  "\n".join(leads),
                          "timestamp": datetime.now(timezone.utc).isoformat()})
    if stage_progress:
        stage_progress("preparing evidence", len(items))
    config = read_config(root)
    from .inquiry import routing, stage_config
    original_material = None
    if routing(root):
        import uuid
        from .files import state_path, write_json
        original_material = state_path(root, f"evidence/{uuid.uuid4().hex}.json")
        write_json(original_material, items)
    # Room for the material after the page, the coverage and the Skill itself.
    from .runner import instructions, run_stage
    overhead = len(instructions("investigate")) + len(notebook.read(record)) + 4000
    room = config["limits"]["input_chars_per_batch"] - overhead
    if room <= 0:
        raise WikiError("Configured input limit cannot fit the current page and investigation Skill")
    gathered_chars = sum(len(json.dumps(i, ensure_ascii=False)) for i in items)
    usage_by_stage = {}
    synthesis_calls = 3 if routing(root) else 1
    if max_calls is not None and max_calls < synthesis_calls:
        raise WikiError("Insufficient call budget for investigation; page preserved")
    if gathered_chars > room:
        if stage_progress:
            stage_progress("extracting long evidence")
        # Too much for one turn. Not "keep the newest and drop the rest": the
        # oldest mail is where a relationship's terms were set. Digest it in
        # order, through the extraction Skill, and let the one investigate turn read the
        # digests -- the same two-pass shape the timeline mode already runs.
        items, digest_usage = digest_in_chunks(items, stage_config(root, config, "extract"), extractor,
                                               root=root,
                                               max_calls=None if max_calls is None else max_calls - synthesis_calls,
                                               progress=stage_progress)
        usage_by_stage["extract"] = digest_usage
        coverage.append(f"digest: {gathered_chars:,} chars gathered (~{gathered_chars // 4:,} tokens), over the "
                        f"{room:,}-char room for one turn; summarised in {len(items)} chunk(s) first")
    now = datetime.now(timezone.utc).isoformat()
    from .page_review import normalize
    current_page = normalize(record, notebook.read(record))
    prompt_items = [
        {"role": "page", "record": record,
         "text": f"The page as it stands, at {record}. Fill its Unknowns, update what "
                 f"has moved, keep what is right:\n\n{current_page}",
         "timestamp": now, "source": "investigation:page"},
        {"role": "coverage", "text": "Sources searched for handles " + ", ".join(handles) + ":\n"
                                     + "\n".join(coverage), "timestamp": now, "source": "investigation:coverage"},
    ] + ([{"role": "quick-first-pass", "source": "investigation:quick-scope",
           "timestamp": now, "text": "This is a bounded, partial first pass. Use only the supplied sample; "
                                     "disclose the sampling limit in Uncertainties."}]
         if quick else []) + items
    if original_material:
        prompt_items.append({"role": "original_evidence", "source": "investigation:original-evidence",
                             "text": f"Original uncompressed evidence is retained at {original_material}. Read it to check summaries and counterevidence.",
                             "file": str(original_material), "timestamp": now})
    # Both runners are `co ai`: it is the orchestrator, and the runner setting
    # only picks which harness answers the Skill -- our own loop, or Codex
    # delegated through `co ai --harness codex`. Either one can reach the web.
    if runner is None:
        runner = run_stage
    if stage_progress:
        stage_progress("writing investigation")
    result = runner(notebook, prompt_items, config, stage="investigate")
    if stage_progress:
        stage_progress("recording result")
    usage_by_stage["investigate"] = result.get("usage")
    total = {}
    for stage_usage in usage_by_stage.values():
        for key, value in (stage_usage or {}).items():
            total[key] = total.get(key, 0) + value
    # The status line names the sources this code searched. Whether the web
    # was reached is the Skill's to report, on the page: a real run (2026-09-14)
    # had `co browser` fail inside the thread while this line still said "web".
    searched = [c.split(" (")[0].split(":")[0] for c in coverage
                if not c.startswith(("budget", "digest", "Requested investigation window:",
                                     "Quick first pass:"))
                and "not searched" not in c and ": unreadable" not in c]
    with maintenance_lock(root):
        from .reviews import ingest
        ingest(root, result.get("review_candidates", []))
        notebook.note_investigation(record, ", ".join(dict.fromkeys(searched)))
    return {"record": record, "items": len(items), "items_available": available_items,
            "quick": quick, "chars_gathered": gathered_chars,
            "tokens_estimated_in": gathered_chars // 4, "coverage": coverage,
            "changed": result.get("changed", []), "usage": total or None,
            "usage_by_stage": usage_by_stage, "report": result.get("report", "")}

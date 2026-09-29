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
from .files import Notebook, RemError, is_address, maintenance_lock
from .mail import _address, _list_all, correspondent, strip_noise, strip_quoted
from .source import KINDS, collect, timestamp

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
                2 if "rem" in path.lower() else 3, len(Path(path).parts), path)
    return sorted(set(leads), key=priority)[:max_files]


def project_file_texts(paths: list[str], *, max_files: int = 12, chars_per_file: int = 2000) -> list[dict]:
    """The summary tier's project evidence: Python reads the files an agent would open.

    A plain model cannot open the inventory's files itself, so their text is
    handed over, within the agent's own bound of twelve files. Each file is
    its own source, cited by its path.
    """
    items = []
    for name in paths[:max_files]:
        path = Path(name)
        text = path.read_text(encoding="utf-8", errors="replace")
        items.append({"role": "project-file", "source": name, "file": name,
                      "timestamp": datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat(),
                      "text": text[:chars_per_file] + ("\n[truncated]" if len(text) > chars_per_file else "")})
    return items


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
           quick: bool = False, archive_root: Path | None = None,
           record: str = "") -> tuple[list[dict], list[str]]:
    """Everything every source holds about the subject, oldest first, plus what was searched.

    `sent_only` is the owner's own page: every message in a mailbox involves
    the owner, so "mail about the owner" is the whole mailbox. What the owner
    wrote is what describes them; what others sent them describes the others.
    """
    handles = [h.strip().lower() for h in handles if h.strip()]
    if days < 1 or not handles:
        raise RemError("Investigation needs a positive day window and at least one subject handle")
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=days)
    items, coverage = [], []
    own_addresses = set()
    archived = None
    if archive_root is not None and record.startswith("people/"):
        from .mail_archive import person_material
        archived = person_material(archive_root, record)
    cached_by_provider, cached_start, cached_end = archived if archived else ({}, None, None)
    # A mailbox the user unsubscribed after init stays out, archive or not.
    cached_by_provider = {kind: rows for kind, rows in cached_by_provider.items()
                          if not subscriptions.get(kind, {}).get("unsubscribed")}
    covered_kinds = set()
    if archived and archive_root is not None:
        from .files import read_json, state_path
        manifest = read_json(state_path(archive_root, "mail/archive.json"), {})
        own_addresses.update(address.casefold() for address in manifest.get("owner_addresses", []))
    for kind in dict.fromkeys([*clients, *cached_by_provider]):
        client = clients.get(kind)
        mine = {a.lower() for a in client.my_addresses()} if client else set()
        if sent_only:
            # Each mailbox knows only its own login. The owner's other addresses
            # are the owner too, not correspondents to search the server for: a
            # first `investigate me` searched for them and found 6 of ~150 mails.
            mine |= {h for h in handles if is_address(h)}
        own_addresses.update(mine)
        local = [item for item in cached_by_provider.get(kind, [])
                 if start <= timestamp(item["timestamp"]) < end
                 and (not sent_only or item["role"] == "user")]
        if quick:
            local = sorted(local, key=lambda item: item["timestamp"])[-12:]
        items.extend(local)
        attached = 0

        def add_attachments(message_id: str, sender: str, stamp: str, subject: str) -> None:
            nonlocal attached
            if attachments_dir is None or not hasattr(client, "download_attachments"):
                return
            from .attachments import extract_text
            short = hashlib.sha256(message_id.encode()).hexdigest()[:12]
            folder = attachments_dir / kind / short
            try:
                folder.mkdir(parents=True, exist_ok=True)
                paths = _saved_paths(_patient(_download, client, message_id, str(folder)))
            except Exception as error:  # noqa: BLE001 -- one bad attachment is not the run
                paths = []
                coverage.append(f"{kind}:{short}: attachments could not be saved ({type(error).__name__})")
            for saved in paths or []:
                attached += 1
                items.append({"role": "attachment", "speaker": sender, "timestamp": stamp,
                              "subject": f"{subject} — {Path(saved).name}",
                              "text": extract_text(Path(saved), limit=None), "file": saved,
                              "source": f"{kind}:{short}:{Path(saved).name}"})

        seen = {item["_mail_id"] for item in local}
        intervals = [(start, end)]
        if archived and kind in cached_by_provider:
            intervals = ([(start, min(end, cached_start))] if start < cached_start else [])
            intervals += ([(max(start, cached_end), end)] if cached_end < end else [])
            intervals = [(begin, finish) for begin, finish in intervals if begin < finish]
            covered_kinds.add(kind)
        hit, taken = [], set(seen)
        searched = f"{len(local)} loaded from private init archive"
        if client is None:
            if intervals:
                coverage.append(f"{kind}: {searched}; {len(intervals)} uncovered interval(s), provider unavailable")
            else:
                coverage.append(f"{kind}: {searched}; requested body interval covered by local archive; "
                                "attachments unavailable without provider")
            continue
        for item in local:
            add_attachments(item["_mail_id"], item["speaker"], item["timestamp"], item.get("subject", ""))
        # Only a whole address goes to the server: a page line with prose or a
        # citation in it made Gmail match 677 unrelated mails (#1954).
        emails = sorted({h.strip() for h in handles if is_address(h) and h not in mine})
        for begin, finish in intervals:
            if emails and hasattr(client, "list_with"):
                # A verified address is server-searchable; the local archive
                # supplies the older interval so only gaps need a query.
                rows = [r for address in emails
                        for r in (_patient(client.list_with, address, begin.isoformat(), finish.isoformat()) or [])]
                searched += f"; searched on the server for {', '.join(emails)}"
            else:
                rows, cursor = [], begin
                while cursor < finish:
                    stop = min(cursor + timedelta(days=7), finish)
                    rows += _patient(_list_all, client, cursor, stop)
                    if progress:
                        progress(kind, stop, len(rows))
                    cursor = stop
                rows = [r for r in rows if _matches(r, handles, mine)]
                searched += f"; scanned {len(rows)} matched mails"
            for row in rows:
                if row["id"] not in taken and (not sent_only or _address(row["from"]) in mine):
                    taken.add(row["id"])
                    hit.append(row)
        if progress:
            progress(kind, end, len(local) + len(hit))
        if sent_only:
            searched += ", kept the owner's own sent mail"
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
            add_attachments(r["id"], r["from"], str(r["date"]), r.get("subject", ""))
            if stage_progress and (number % 10 == 0 or number == len(mail_to_read)):
                stage_progress(f"gathering {kind} mail", number, len(mail_to_read))
        coverage.append(f"{kind} ({', '.join(sorted(mine))}): {searched} over {days} days, "
                        f"{len(local) + len(hit)} matched, {len(local) + len(mail_to_read)} bodies read"
                        + (" (recent quick sample)" if quick else "")
                        + (f", {len(local)} of them from the private init archive" if local else "")
                        + f", {attached} attachments read")
    for kind in ("outlook", "gmail"):
        if kind not in clients and kind not in covered_kinds:
            # Say it. A mailbox left out used to vanish from coverage, so the model
            # and the reader could not tell "no mail with this person" from "not asked".
            # A mailbox left out on purpose says why; "not connected" sent a user
            # to log in again for a project page that simply does not read mail.
            why = (mail_skipped or ("unsubscribed by the user" if subscriptions.get(kind, {}).get("unsubscribed")
                   else f"not connected (co auth {'google' if kind == 'gmail' else 'microsoft'})"))
            coverage.append(f"{kind}: {why}; not searched")
    from .chat import CHAT_KINDS, collect_chat
    for name, sub in subscriptions.items():
        chat = sub.get("kind") in CHAT_KINDS
        if sub.get("kind") not in KINDS and not chat:
            continue
        if chat and not sub.get("chats"):
            # Chats are read only when the user named them (a linked device sees
            # every group the number is in); none named is a choice, said so.
            coverage.append(f"{name}: no chats chosen, not searched")
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
        read = collect_chat if chat else collect

        def related(item):
            # A chat line says who said it; mail's rule for the owner applies:
            # what the owner wrote describes them, the whole chat does not.
            # sent_only is the owner's page even when no mailbox is connected
            # to tell us their addresses; a chat knows which lines are theirs.
            if is_owner or (chat and sent_only):
                return not chat or item["role"] == "user"
            said = item["text"] + " " + item.get("project", "")
            if chat:
                said += " " + item.get("speaker", "") + " " + item.get("correspondent", "")
            return any(h in said.lower() for h in handles)
        try:
            while True:
                batch = read(scoped, cursor, 40, 200_000)
                scanned += len(batch.items)
                picked.extend(i for i in batch.items if related(i))
                if batch.progress == cursor:
                    break
                cursor = batch.progress
                if stage_progress:
                    stage_progress(f"gathering {name} {'chats' if chat else 'sessions'}", scanned)
        except RemError as error:
            coverage.append(f"{name}: unreadable ({error})")
        related = len(picked)
        if quick:
            picked = picked[-12:]
        coverage.append(f"{name}: {scanned} messages in window, {related} related to subject, "
                        f"{len(picked)} read"
                        + (" (recent quick sample)" if quick else "")
                        + (" (account owner's own messages)" if is_owner or (chat and sent_only)
                           else " (handle, sender or chat match)" if chat else " (handle or project match)"))
        items += picked
    items.sort(key=lambda i: i["timestamp"])
    for item in items:
        item.pop("_mail_id", None)
    return items, coverage


def _split_item(item: dict, limit_chars: int, measure=None):
    """Split a long document without losing its text, source or date.

    `measure` is how big a list of parts is; by default its JSON length.
    """
    measure = measure or (lambda parts: len(json.dumps(parts, ensure_ascii=False)))
    if measure([item]) <= limit_chars:
        yield item
        return
    if measure([{**item, "text": ""}]) >= limit_chars:
        raise RemError("Extraction character limit is too small for source metadata; "
                        "increase limits.extract_chars_per_batch")
    remaining = item["text"]
    while remaining:
        low, high = 0, min(len(remaining), limit_chars)
        while low < high:
            middle = (low + high + 1) // 2
            if measure([{**item, "text": remaining[:middle]}]) <= limit_chars:
                low = middle
            else:
                high = middle - 1
        if not low:
            raise RemError("Extraction character limit cannot fit source text; "
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
            raise RemError("co rem root is required for model extraction")
        extractor = lambda chunk, settings, kind: run_extract(chunk, settings, kind, root=root)
    from .runner import INLINE_LIMIT, readable_material
    # Each piece travels in the prompt, beside the extraction Skill. 150k
    # characters never did, so every piece was read from files instead: about
    # 1M input tokens a piece on the owner's notebook, 15 pieces for one person.
    kinds = {str(item.get("source", "")).split(":")[0] for item in items}
    widest = max(len(extraction_instructions(kind).encode("utf-8")) for kind in kinds | {""})
    room = min(limits["extract_chars_per_batch"], INLINE_LIMIT - widest - 2000)
    measure = lambda parts: len(readable_material(parts).encode("utf-8"))
    chunks, current = [], []
    for item in items:
        for part in _split_item(item, room, measure):
            if current and (len(current) >= limits["extract_items_per_batch"]
                            or measure(current + [part]) > room):
                chunks.append(current)
                current = []
            current.append(part)
    if current:
        chunks.append(current)
    if max_calls is not None and len(chunks) > max_calls:
        raise RemError("Extraction exceeds remaining call budget; page preserved")
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
        raise RemError(f"{record} does not exist; create it with `co rem stub` first")
    if stage_progress:
        stage_progress("gathering sources")
    items, coverage = gather(subject, handles, days=days, clients=clients, subscriptions=subscriptions,
                             progress=progress, attachments_dir=root / ".state" / "attachments",
                             sent_only=sent_only, mail_skipped=mail_skipped, stage_progress=stage_progress,
                             quick=quick, archive_root=root, record=record)
    coverage.append(f"Requested investigation window: {days} days ending "
                    f"{datetime.now(timezone.utc).date().isoformat()}")
    available_items = len(items)
    if quick:
        items = quick_evidence(items)
        coverage.append(f"Quick first pass: reviewed {len(items)} of {available_items} gathered items; "
                        "individual texts capped at 2,500 characters. Other material was not evaluated; "
                        "do not claim comprehensive coverage or resolve unsupported conflicts.")
    leads = []
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
    from .inquiry import routing
    original_material = None
    if routing(root):
        import uuid

        from .files import state_path, write_json
        original_material = state_path(root, f"evidence/{uuid.uuid4().hex}.json")
        write_json(original_material, items)
    # Room for the material after the page, the coverage and the Skill itself.
    from .runner import instructions, page_kind_of, run_stage
    # The instructions this page's turn is actually given (task_prompt), not
    # the no-page-kind worst case, which carries every page shape and the CLI
    # reference and left ~33k characters less room for material.
    overhead = len(instructions("investigate", page_kind=page_kind_of(record))) + len(notebook.read(record)) + 4000
    room = config["limits"]["input_chars_per_batch"] - overhead
    from .tier import current
    summary = current(root, config) == "summary"
    if summary:
        # A plain model reads nothing it is not handed: the page's whole
        # material travels in the one prompt, so it must fit there (#1847).
        from .runner import INLINE_LIMIT
        room = min(room, INLINE_LIMIT - overhead)
        items += project_file_texts(leads)
    if room <= 0:
        raise RemError("Configured input limit cannot fit the current page and investigation Skill")
    gathered_chars = sum(len(json.dumps(i, ensure_ascii=False)) for i in items)
    usage_by_stage = {}
    synthesis_calls = 3 if routing(root) else 1
    if max_calls is not None and max_calls < synthesis_calls:
        raise RemError("Insufficient call budget for investigation; page preserved")
    now = datetime.now(timezone.utc).isoformat()
    evidence_dir = None
    if gathered_chars > room and summary:
        # A summary-tier model cannot search files (#1847), so it is handed
        # digests of the material in order, the shape investigation had before #1850.
        from .inquiry import stage_config
        items, usage_by_stage["extract"] = digest_in_chunks(
            items, stage_config(root, config, "extract"), extractor, root=root,
            max_calls=None if max_calls is None else max_calls - synthesis_calls, progress=stage_progress)
        coverage.append(f"digest: {gathered_chars:,} chars gathered (~{gathered_chars // 4:,} tokens), over the "
                        f"{room:,}-char room for one summary-tier turn; summarised in {len(items)} chunk(s) first")
    elif gathered_chars > room:
        if stage_progress:
            stage_progress("writing evidence files")
        # Too much for one turn. Not "keep the newest and drop the rest": the
        # oldest mail is where a relationship's terms were set. And not
        # "summarise it all first" either: that was 39 digest calls and 75
        # minutes for the owner's page (#1850). The material goes into files
        # and the one investigate turn searches them for what the page needs.
        import shutil
        import uuid

        from .evidence import write_evidence
        from .files import state_path
        evidence_dir = state_path(root, f"evidence/{uuid.uuid4().hex}")
        shutil.rmtree(evidence_dir, ignore_errors=True)
        laid_out = write_evidence(evidence_dir, items)
        index_text = laid_out["index"].read_text(encoding="utf-8")
        shown = index_text if len(index_text) <= room // 2 else (
            index_text[:room // 2] + f"\n[Index continues in {laid_out['index']}; read the rest there.]\n")
        items = [{"role": "evidence-index", "source": "investigation:evidence", "timestamp": now,
                  "file": str(laid_out["index"]), "sources": laid_out["sources"],
                  "text": (f"The gathered evidence ({len(laid_out['sources'])} items, {laid_out['chars']:,} "
                           f"characters) did not fit one turn and has NOT been summarised. It is in files under "
                           f"{evidence_dir}. For each Unknown or stale field on the page, search those files "
                           "with rg/grep, then read only the matching entries with sed or a file tool; use ls to "
                           "see the layout. Cite the source id from the `###` heading of each entry you rely on. "
                           "In your final reply, list the files you read and the questions left open.\n\n"
                           + shown)}]
        coverage.append(f"evidence: {gathered_chars:,} chars gathered (~{gathered_chars // 4:,} tokens), over the "
                        f"{room:,}-char room for one turn; written to {laid_out['files']} files and searched, "
                        "not summarised first")
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
    try:
        result = runner(notebook, prompt_items, config, stage="investigate")
    finally:
        # Copies of private mail do not accumulate under .state, run after run;
        # the report keeps which files were read.
        if evidence_dir is not None:
            import shutil
            shutil.rmtree(evidence_dir, ignore_errors=True)
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
            "usage_by_stage": usage_by_stage, "report": result.get("report", ""),
            "instructions_chars": {"investigate": result.get("instructions_chars")}}

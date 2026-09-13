"""One subject, every source at once: the first-run stage, and the daily deep pass.

Identity is the input. The subject arrives with its handles, every handle is
searched in every source, and a handle that finds nothing is reported rather
than passed over -- "searched Gmail for X, none" and "did not mention Gmail"
read alike on a page and mean different things.
"""

import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .config import read_config
from .files import Notebook, WikiError
from .mail import MAX_BODY_CHARS, _address, _fit_text, correspondent, strip_noise, strip_quoted
from .source import KINDS, collect

MAIL_KINDS = ("outlook", "gmail")


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
            transient = "timeout" in type(error).__name__.lower() or "timed out" in str(error).lower()
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
           progress=None, attachments_dir: Path | None = None) -> tuple[list[dict], list[str]]:
    """Everything every source holds about the subject, oldest first, plus what was searched."""
    handles = [h.strip().lower() for h in handles if h.strip()]
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=days)
    items, coverage = [], []
    for kind, client in clients.items():
        mine = {a.lower() for a in client.my_addresses()}
        rows, cursor = [], start
        while cursor < end:
            stop = min(cursor + timedelta(days=7), end)
            rows += _patient(client.list_between, cursor.isoformat(), stop.isoformat(), 200) or []
            if progress:
                progress(kind, stop, len(rows))
            cursor = stop
        hit = [r for r in rows if _matches(r, handles, mine)]
        attached = 0
        for r in sorted(hit, key=lambda r: str(r["date"])):
            body = _patient(client.get_email_body, r["id"])
            head, _, rest = body.partition("--- Email Body ---")
            body = head + "--- Email Body ---" + strip_noise(strip_quoted(rest)) if rest else strip_noise(strip_quoted(body))
            own = _address(r["from"]) in mine or "@" not in _address(r["from"])
            short = hashlib.sha256(r["id"].encode()).hexdigest()[:12]
            items.append({"role": "user" if own else "other", "speaker": r["from"],
                          "text": _fit_text(body[:MAX_BODY_CHARS], 6000), "timestamp": str(r["date"]),
                          "subject": r.get("subject", ""), "source": f"{kind}:{short}"})
            if attachments_dir is not None and hasattr(client, "download_attachments"):
                from .attachments import extract_text
                folder = attachments_dir / kind / short
                try:
                    paths = _saved_paths(_patient(_download, client, r["id"], str(folder)))
                except Exception as error:  # noqa: BLE001 -- one bad attachment is not the run
                    paths = []
                    coverage.append(f"{kind}:{short}: attachments could not be saved ({type(error).__name__})")
                for saved in paths or []:
                    attached += 1
                    items.append({"role": "attachment", "speaker": r["from"], "timestamp": str(r["date"]),
                                  "subject": f"{r.get('subject', '')} — {Path(saved).name}",
                                  "text": extract_text(Path(saved)), "file": saved,
                                  "source": f"{kind}:{short}:{Path(saved).name}"})
        coverage.append(f"{kind} ({', '.join(sorted(mine))}): scanned {len(rows)} mails over {days} days, "
                        f"{len(hit)} matched, {attached} attachments read")
    for name, sub in subscriptions.items():
        if sub.get("kind") not in KINDS or not Path(sub.get("root", "")).is_dir():
            continue
        scoped = {**sub, "enabled": True, "consented": True, "since": start.isoformat(), "subject": subject}
        try:
            batch = collect(scoped, {}, 40, 200_000)
        except WikiError as error:
            coverage.append(f"{name}: unreadable ({error})")
            continue
        picked = [i for i in batch.items if any(h in i["text"].lower() for h in handles)]
        coverage.append(f"{name}: {len(batch.items)} messages in window, {len(picked)} mention a handle")
        items += picked
    items.sort(key=lambda i: i["timestamp"])
    return items, coverage


def digest_in_chunks(items: list[dict], config: dict, extractor=None) -> tuple[list[dict], dict]:
    """Oldest first, each chunk within the extract limits, one digest item per chunk."""
    from .extract import NOTHING, extraction_item, run_extract
    limits = config["limits"]
    extractor = extractor or run_extract
    chunks, current, size = [], [], 0
    for item in items:
        n = len(json.dumps(item, ensure_ascii=False))
        if current and (len(current) >= limits["extract_items_per_batch"] or size + n > limits["extract_chars_per_batch"]):
            chunks.append(current); current, size = [], 0
        current.append(item); size += n
    if current:
        chunks.append(current)
    digests, usage = [], {}
    for chunk in chunks:
        kinds = {i["source"].split(":")[0] for i in chunk}
        kind = kinds.pop() if len(kinds) == 1 else ""
        out = extractor(chunk, config, kind)
        for key, value in (out.get("usage") or {}).items():
            usage[key] = usage.get(key, 0) + value
        if (out.get("notes") or "").strip() != NOTHING:
            digests.append(extraction_item(out["notes"].strip(), chunk))
    return digests, usage


def fit_to_budget(items: list[dict], coverage: list[str], limit_chars: int) -> list[dict]:
    """Keep the most recent material that fits; say what was left out.

    The account's owner matches every mail there is: a ten-minute gather came
    back far over the input limit and the run died at the runner's door, with
    nothing written and the listings already paid for. A subject with more
    material than one turn holds gets the newest of it, and the coverage line
    says how much older material is waiting for a later pass -- which is a
    finding the page can carry, where a crash is not.
    """
    kept, used = [], 0
    for item in reversed(items):                      # newest first
        size = len(json.dumps(item, ensure_ascii=False))
        if used + size > limit_chars:
            break
        kept.append(item)
        used += size
    kept.reverse()
    if len(kept) < len(items):
        oldest_kept = kept[0]["timestamp"][:10] if kept else "none"
        coverage.append(f"budget: {len(items)} items gathered, {len(kept)} newest kept "
                        f"(from {oldest_kept}); {len(items) - len(kept)} older ones wait for a later pass")
    return kept


def investigate(root: Path, record: str, subject: str, handles: list[str], *, days: int,
                clients: dict, subscriptions: dict, runner=None, extractor=None, progress=None) -> dict:
    """Fill the page's gaps from everything gathered; the page itself is the first input."""
    notebook = Notebook(root)
    if not notebook.path(record).is_file():
        raise WikiError(f"{record} does not exist; create it with `co wiki stub` first")
    items, coverage = gather(subject, handles, days=days, clients=clients, subscriptions=subscriptions,
                             progress=progress, attachments_dir=root / ".state" / "attachments")
    config = read_config(root)
    # Room for the material after the page, the coverage and the Skill itself.
    from .runner import instructions, tool_specs
    overhead = len(instructions("investigate")) + len(json.dumps(tool_specs())) + len(notebook.read(record)) + 4000
    room = config["limits"]["input_chars_per_batch"] - overhead
    gathered_chars = sum(len(json.dumps(i, ensure_ascii=False)) for i in items)
    usage_by_stage = {}
    if gathered_chars > room:
        # Too much for one turn. Not "keep the newest and drop the rest": the
        # oldest mail is where a relationship's terms were set. Digest it in
        # order, tool-less and cheap, and let the one investigate turn read the
        # digests -- the same two-pass shape the timeline mode already runs.
        items, digest_usage = digest_in_chunks(items, config, extractor)
        usage_by_stage["extract"] = digest_usage
        coverage.append(f"digest: {gathered_chars:,} chars gathered (~{gathered_chars // 4:,} tokens), over the "
                        f"{room:,}-char room for one turn; summarised in {len(items)} chunk(s) first")
    now = datetime.now(timezone.utc).isoformat()
    prompt_items = [
        {"role": "page", "record": record,
         "text": f"The page as it stands, at {record}. Fill its Unknowns, update what "
                 f"has moved, keep what is right:\n\n{notebook.read(record)}",
         "timestamp": now, "source": "investigation:page"},
        {"role": "coverage", "text": "Sources searched for handles " + ", ".join(handles) + ":\n"
                                     + "\n".join(coverage), "timestamp": now, "source": "investigation:coverage"},
    ] + items
    # Both runners are `co ai`: it is the orchestrator, and the runner setting
    # only picks which harness answers the Skill -- our own loop, or Codex
    # delegated through `co ai --harness codex`. Either one can reach the web.
    if runner is None:
        runner = run_under_co_ai
    result = runner(notebook, prompt_items, config, stage="investigate")
    usage_by_stage["investigate"] = result.get("usage")
    total = {}
    for stage_usage in usage_by_stage.values():
        for key, value in (stage_usage or {}).items():
            total[key] = total.get(key, 0) + value
    # The status line names the sources this code searched. Whether the web
    # was reached is the Skill's to report, on the page: a real run (2026-09-14)
    # had `co browser` fail inside the thread while this line still said "web".
    searched = [c.split(" (")[0].split(":")[0] for c in coverage if not c.startswith(("budget", "digest"))]
    notebook.note_investigation(record, ", ".join(dict.fromkeys(searched)))
    return {"record": record, "items": len(items), "chars_gathered": gathered_chars,
            "tokens_estimated_in": gathered_chars // 4, "coverage": coverage,
            "changed": result.get("changed", []), "usage": total or None,
            "usage_by_stage": usage_by_stage, "report": result.get("report", "")}


def harness_flags(config: dict) -> list[str]:
    """How co ai runs the Skill for this runner setting.

    codex: `co ai --harness codex`, the task handed whole to Codex on the
    ChatGPT subscription, with the full-access sandbox. Investigating means
    running the user's own `co outlook`, `co gmail` and `co browser` inside the
    thread, and every one of them needs the network; a read-only, offline
    thread could only write "web: not reachable" and leave the fields Unknown.
    The model is the notebook's, since a delegate knows only its own catalogue.
    coai: our own loop on the co/ key, on the model co ai picks by default.
    """
    if config["runner"] != "codex":
        return []
    return ["--harness", "codex", "--sandbox", "danger-full-access", "--model", config["model"]]


def run_under_co_ai(notebook: Notebook, items: list[dict], config: dict, *, stage: str = "investigate",
                    timeout: int = 900) -> dict:
    """One investigate turn under co ai, whichever harness answers it.

    The material is written to a file the Skill reads rather than pasted into a
    prompt: a page, a coverage report and several digests run to hundreds of
    kilobytes, and an argv has limits a file does not. The Skill writes the page
    itself; what changed is read back from disk rather than trusted from the
    agent's own account of it.
    """
    import shutil
    import subprocess
    record = next((i.get("record") for i in items if i.get("role") == "page"), None)
    if not record:
        raise WikiError("run_under_co_ai needs the page item to know which page to write")
    executable = shutil.which("co")
    if not executable:
        raise WikiError("`co` is not on PATH; both runners drive co ai")
    workdir = notebook.root / ".state" / "investigations"
    workdir.mkdir(parents=True, exist_ok=True, mode=0o700)
    material = workdir / (Path(record).stem + ".md")
    material.write_text("\n\n---\n\n".join(
        f"[{i.get('role')}] {i.get('timestamp', '')} {i.get('source', '')}\n{i['text']}" for i in items),
        encoding="utf-8")
    before = {r: notebook.read(r) for r in notebook.list()}
    prompt = (f"/wiki-{stage} The page is {notebook.root / record}; the material gathered for it -- the page as "
              f"it stands, the coverage report, and every source item or digest -- is in {material}. Read "
              f"both, fill the page's Unknowns from the material, then look on the open web for the fields "
              f"the material did not hold, and write the page back to that same path.")
    completed = subprocess.run([executable, "ai", "--json", *harness_flags(config), prompt],
                               cwd=str(notebook.root), capture_output=True, text=True, timeout=timeout)
    envelope = {}
    for line in reversed(completed.stdout.splitlines()):
        line = line.strip()
        if line.startswith("{") and line.endswith("}"):
            try:
                envelope = json.loads(line); break
            except ValueError:
                continue
    if envelope.get("error") or envelope.get("outcome") not in (None, "natural"):
        raise WikiError(f"co ai did not complete ({envelope.get('outcome')}): "
                        f"{str(envelope.get('error') or completed.stderr[-300:])[:300]}")
    after = {r: notebook.read(r) for r in notebook.list()}
    changed = sorted(r for r in after if before.get(r) != after[r])
    return {"usage": envelope.get("usage"), "changed": changed, "refused": 0, "refusals": [],
            "report": (envelope.get("result") or "")[:1000]}

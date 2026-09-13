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


def _matches(row: dict, handles: list[str], mine: set) -> bool:
    haystack = " ".join([correspondent(row, mine), str(row.get("from", "")), str(row.get("to", "")),
                         str(row.get("subject", ""))]).lower()
    return any(handle in haystack for handle in handles)


def gather(subject: str, handles: list[str], *, days: int, clients: dict, subscriptions: dict,
           progress=None) -> tuple[list[dict], list[str]]:
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
        coverage.append(f"{kind} ({', '.join(sorted(mine))}): scanned {len(rows)} mails over {days} days, {len(hit)} matched")
        for r in sorted(hit, key=lambda r: str(r["date"])):
            body = _patient(client.get_email_body, r["id"])
            head, _, rest = body.partition("--- Email Body ---")
            body = head + "--- Email Body ---" + strip_noise(strip_quoted(rest)) if rest else strip_noise(strip_quoted(body))
            own = _address(r["from"]) in mine or "@" not in _address(r["from"])
            items.append({"role": "user" if own else "other", "speaker": r["from"],
                          "text": _fit_text(body[:MAX_BODY_CHARS], 6000), "timestamp": str(r["date"]),
                          "subject": r.get("subject", ""),
                          "source": f"{kind}:" + hashlib.sha256(r["id"].encode()).hexdigest()[:12]})
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
                clients: dict, subscriptions: dict, runner=None, progress=None) -> dict:
    """Fill the page's gaps from everything gathered; the page itself is the first input."""
    notebook = Notebook(root)
    if not notebook.path(record).is_file():
        raise WikiError(f"{record} does not exist; create it with `co wiki stub` first")
    items, coverage = gather(subject, handles, days=days, clients=clients,
                             subscriptions=subscriptions, progress=progress)
    config = read_config(root)
    # Room for the material after the page, the coverage and the Skill itself.
    from .runner import instructions, tool_specs
    overhead = len(instructions("investigate")) + len(json.dumps(tool_specs())) + len(notebook.read(record)) + 4000
    items = fit_to_budget(items, coverage, config["limits"]["input_chars_per_batch"] - overhead)
    now = datetime.now(timezone.utc).isoformat()
    prompt_items = [
        {"role": "page", "text": f"The page as it stands, at {record}. Fill its Unknowns, update what "
                                 f"has moved, keep what is right:\n\n{notebook.read(record)}",
         "timestamp": now, "source": "investigation:page"},
        {"role": "coverage", "text": "Sources searched for handles " + ", ".join(handles) + ":\n"
                                     + "\n".join(coverage), "timestamp": now, "source": "investigation:coverage"},
    ] + items
    from .runner import run_codex
    runner = runner or run_codex
    result = runner(notebook, prompt_items, config, stage="investigate")
    searched = [c.split(" (")[0].split(":")[0] for c in coverage]
    notebook.note_investigation(record, ", ".join(dict.fromkeys(searched)))
    return {"record": record, "items": len(items), "chars": sum(len(json.dumps(i, ensure_ascii=False)) for i in items),
            "coverage": coverage, "changed": result.get("changed", []), "usage": result.get("usage"),
            "report": result.get("report", "")}

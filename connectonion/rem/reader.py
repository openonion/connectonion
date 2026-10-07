"""Disposable HTML view of the notebook. Markdown stays the store; this is a snapshot.

A page opened from file:// cannot read the Markdown next to it (browsers block
fetch from file URLs), so the notebook is embedded into one self-contained HTML
file at render time. The template is a plain client of that embedded object; a
served site later would hand it the same object over HTTP instead.
"""

import hashlib
import json
import os
import re
import tempfile
import webbrowser
from datetime import datetime, timezone
from pathlib import Path

from .files import CATEGORIES, Notebook, RemError
from .service import run_logs, status, subscriptions

TEMPLATE = Path(__file__).with_name("reader.html")
PLACEHOLDER = "/*__REM_DATA__*/null"


def _title(record: str, text: str) -> str:
    for line in text.splitlines():
        if line.startswith("#"):
            return line.lstrip("#").strip() or record
    return Path(record).stem.replace("-", " ")


def mail_facts(root: Path) -> dict:
    """{record: {mails, sent, received, first, last}} from the map's correspondent rows.

    The People table's mail columns. One adapter on purpose: when the notebook
    keeps its facts in an index (#2067) this reads that instead, and the page
    does not change. A person seen under several addresses is summed.
    """
    from .files import read_json, state_path
    facts = {}
    for row in read_json(state_path(root, "map.json"), {}).get("people", []):
        if not isinstance(row, dict) or not row.get("record") or not row.get("address"):
            continue
        fact = facts.setdefault(row["record"], {"mails": 0, "sent": 0, "received": 0, "first": "", "last": ""})
        for key in ("mails", "sent", "received"):
            fact[key] += row.get(key) if type(row.get(key)) is int else 0
        first, last = str(row.get("first") or ""), str(row.get("last") or "")
        fact["first"] = min(filter(None, (fact["first"], first)), default="")
        fact["last"] = max(fact["last"], last)
    return facts


def index_rows(root: Path) -> dict:
    """{record: row} from the notebook's index (#2067) once it exists; {} before.

    The People sheet reads these columns first and falls back to the page's own
    fields and the map's mail counts. A notebook with no index yet (or a co rem
    without the store) gets the fallback, never an error; a corrupt index raises,
    naming the command that rebuilds it.
    """
    try:
        from . import store
    except ImportError:
        return {}
    return {row["record"]: row for row in store.people_table(root, include_unlisted=True) or []}


def contact_candidates(root: Path) -> tuple[list[dict], dict]:
    """Mail correspondents without a memory page, plus honest scan coverage.

    The map intentionally omits one-off addresses from Markdown pages. They
    must still be findable, without pretending a header established a person.
    Subjects and message bodies never enter the reader's directory.
    """
    from .files import read_json, state_path
    mapped = read_json(state_path(root, "map.json"), {})
    seen, rows = set(), []
    for row in mapped.get("without_page", []):
        address = str(row.get("address") or "").strip()
        if not address or address.casefold() in seen:
            continue
        seen.add(address.casefold())
        rows.append({"name": str(row.get("name") or ""), "email": address,
                     "last": str(row.get("last") or ""),
                     "mails": row.get("mails") if type(row.get("mails")) is int else 0,
                     "sent": row.get("sent") if type(row.get("sent")) is int else 0,
                     "received": row.get("received") if type(row.get("received")) is int else 0})
    rows.sort(key=lambda row: (-row["mails"], row["email"].casefold()))
    errors = [row for row in mapped.get("errors", []) if row.get("source") in ("gmail", "outlook")]
    return rows, {"scope": "all available history since 1970" if mapped.get("all_history") else
                   f"last {mapped.get('days', 90)} days", "incomplete": bool(errors),
                   "mailbox_errors": len(errors), "automated": len(mapped.get("automated_correspondents", []))}


def snapshot(root: Path) -> dict:
    """Everything the page shows, read once; no model, no writes into the notebook."""
    from .map import needs_review
    from .project_pages import private
    from .reviews import listing
    notebook = Notebook(root)
    records = []
    for record in notebook.list():
        text = notebook.read(record)
        updated = datetime.fromtimestamp(notebook.path(record).stat().st_mtime, timezone.utc)
        records.append({"path": record, "category": record.split("/")[0],
                        "title": _title(record, text) + (" (automated candidate)" if "- Correspondent classification: automated candidate;" in text else ""), "text": text,
                        "updated": updated.isoformat(timespec="seconds")})
    # Held for review (#1844): still linkable, left off the contents until promoted.
    held = needs_review(root)
    # What is counted, written, and when it was last active comes from one
    # place (`census`), the same that `co rem status` counts with (#2008).
    from .census import counts, pages
    found = pages(root)
    mail, index = mail_facts(root), index_rows(root)
    for record in records:
        if record["path"] in mail:
            record["mail"] = mail[record["path"]]
        if record["path"] in index:
            record["index"] = index[record["path"]]
        record["needs_review"] = record["path"] in held
        entry = found.get(record["path"])
        if entry:
            record.update(written=entry["written"], last_activity=entry["last"], service=entry["service"])
        if record["category"] == "projects":
            record["private_project"] = private(record["path"], record["text"])
            from .project_material import page_state
            record["project_coverage"] = page_state(root, record["path"]).get("last_page_coverage")
    groups = {}
    for record in records:
        if record["path"].startswith("skills/catalog/") and record["path"] != "skills/catalog/index.md":
            source = re.search(r"^- File: (.+)$", record["text"], re.MULTILINE)
            if source:
                record["installation"] = source.group(1)
                groups.setdefault(record["title"].casefold(), []).append(record)
    for group in groups.values():
        first = group[0]
        first["installations"] = [{"path": r["path"], "source": r["installation"]} for r in group]
        for other in group[1:]:
            other["catalog_parent"] = first["path"]
    from .reader_model import cited_context, cited_conversations, relationships
    links = relationships(records)
    for record in records:
        record["relations"] = links.get(record["path"], [])
    contexts = cited_context(root, records)
    from .project_material import stored
    for record in records:
        if record["category"] != "projects":
            continue
        for message in stored(root, record["path"]):
            context = contexts.get(message["source"])
            if context:
                context.setdefault("mapped_session_folder", message["cwd"])
    candidates, contact_coverage = contact_candidates(root)
    return {"as_of": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "root": str(root), "categories": list(CATEGORIES), "records": records,
            "contact_candidates": candidates, "contact_coverage": contact_coverage,
            "source_context": contexts, "conversations": cited_conversations(root, contexts),
            "status": status(root), "subscriptions": subscriptions(root),
            "logs": run_logs(root)[:20], "reviews": listing(root), "counts": counts(root, found),
            "owner": owner_record(root)}


def owner_record(root: Path) -> str:
    """The owner's own page, pinned as "You" at the top of the reader's navigation."""
    from .files import read_json, state_path
    owner = read_json(state_path(root, "map.json"), {}).get("owner") or {}
    return owner.get("record", "") if isinstance(owner, dict) else ""


def render(root: Path) -> str:
    data = json.dumps(snapshot(root), ensure_ascii=False, default=str)
    # Inside a script block only "</script" and the U+2028/9 terminators can break
    # out. Escaping "<" as \u003c keeps the JSON valid and makes note text inert.
    data = data.replace("<", "\\u003c").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")
    template = TEMPLATE.read_text(encoding="utf-8")
    if PLACEHOLDER not in template:
        raise RuntimeError("reader.html has lost its data placeholder")
    return template.replace(PLACEHOLDER, data, 1)


def reader_path(root: Path) -> Path:
    """Outside the notebook, so nothing under root changes and no collector meets it."""
    digest = hashlib.sha256(str(Path(root).resolve()).encode()).hexdigest()[:12]
    return Path(tempfile.gettempdir()) / f"co-rem-{digest}.html"


def write_reader(root: Path) -> Path:
    page = render(root)
    path = reader_path(root)
    # The public name is predictable. Write a private random file, then replace
    # the directory entry atomically so a planted link can never be truncated.
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", prefix="co-rem-", suffix=".html",
            dir=path.parent, delete=False,
        ) as output:
            temporary = Path(output.name)
            output.write(page)
        if path.is_symlink():
            raise OSError(f"refusing to replace a planted reader link: {path}")
        if os.name != "nt":
            os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return path


def open_reader(root: Path, *, launch: bool = True) -> Path:
    path = write_reader(root)
    if launch:
        webbrowser.open(path.as_uri())
    return path


# The live view: O Chat reads the default notebook from the owner's `co ai` Host
# over OIP (`WIKI_READ`, #1637). The route and whether it exists live here only.
LIVE_REM_URL = "https://chat.openonion.ai/{address}/rem"

# The /rem route is paired with O Chat; old /wiki links redirect there.
LIVE_REM_SERVED = True

# Is the live view what a bare `co rem open` opens? No, by the owner's decision
# (2026-09-27, #1828): opening locally is the default and works offline; the
# live view through the Host is a feature asked for with --live.
LIVE_IS_DEFAULT = False

LIVE_HINT = "co rem open --live   (the live view in O Chat; starts co ai automatically)"


def host_online(address: str, timeout: float = 3.0) -> bool:
    """Is the Host for this address answering right now? No model, no login.

    Online is what a client can connect to: the relay holds the Host's announce
    socket (how O Chat reaches a Host behind NAT or on another machine), or,
    failing that, an announced endpoint answers /info as that address -- the
    same two routes connect() takes. The whole check is bounded by `timeout`;
    no answer in time reads as offline and costs a snapshot, never a dead page.
    """
    import asyncio
    import importlib
    from ..backend import backend_ws_url
    # By import_module: connectonion.network re-exports a connect() that shadows the module.
    connect = importlib.import_module("connectonion.network.connect")
    relay = backend_ws_url()

    async def check() -> bool:
        if await connect.relay_presence(address, relay, timeout):
            return True
        return await connect.resolve_endpoint(address, relay, timeout) is not None

    async def bounded() -> bool:
        try:
            return await asyncio.wait_for(check(), timeout)
        except asyncio.TimeoutError:
            return False
    return asyncio.run(bounded())


def open_snapshot(root: Path, *, launch: bool, **notes) -> dict:
    path = open_reader(root, launch=launch)
    return {"page": str(path), "link": path.as_uri(), "launched": launch,
            "note": "a snapshot of the notebook as it is now; co rem open again shows later changes", **notes}


def live_or_snapshot(root: Path, address, *, live: bool, launch: bool) -> dict:
    """What `co rem open` shows: the live view only when it is wanted, belongs to
    this notebook, and its Host answers; otherwise the snapshot, saying why."""
    if not live:
        return open_snapshot(root, launch=launch, **({"live_view": LIVE_HINT} if address else {}))
    if not address:
        return open_snapshot(root, launch=launch, live=(
            "only the default notebook (~/.co/rem) with a co ai identity has a live view"))
    if not host_online(address):
        from .live_host import ensure_online
        try:
            failure = ensure_online(address)
        except (OSError, RemError) as error:
            failure = f"could not start co ai: {error}; run `co ai` to diagnose"
        if failure:
            return open_snapshot(root, launch=launch, live=f"Live startup failed: {failure}; showing a snapshot",
                                 live_startup_failed=True)
    url = LIVE_REM_URL.format(address=address)
    if launch:
        webbrowser.open(url)
    result = {"page": url, "link": url, "launched": launch}
    if not LIVE_REM_SERVED:
        result["warning"] = ("O Chat does not serve this route yet (openonion/oo-chat#246); "
                             "until it is deployed the page opens as an empty chat")
    return result

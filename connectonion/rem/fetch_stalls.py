"""One item's mailbox failure sets that item aside, never the night (sprint 14).

From 2026-11-12 every 15-minute turn on the owner's laptop ended with no task:
16 turns on `Microsoft Graph API error (HTTP 404)`, then 14 on a ReadTimeout
while listing one mail's attachments, both while preparing one person's page.
The exception left `co rem next`, the round's cursor was never saved, and the
next turn tried the same page again. Nights 11-08..11-11 read no mail and
wrote no drafts.

Now a provider's failure while preparing one page parks that page here with
its reason and a retry time, and `next` goes on to the next page. A provider
that fails for several pages in one turn, or whose authorization has expired,
is not asked again in that turn. The reader's night line reads this ledger.
"""

import functools
import os
from datetime import timedelta

from . import service
from .files import read_json, state_path, write_json

LEDGER = "fetch-parked.json"
# A parked page is tried again after 1 h, then 6 h, then once a day: a slow
# hour should not cost a page its night, and a mail that is gone for good
# should not cost a turn every 15 minutes.
BACKOFF_HOURS = (1, 6, 24)
# Three pages failing on one mailbox in one turn is the mailbox, not the pages.
PROVIDER_STOP_PAGES = 3
# These say the mailbox itself is unusable: the first one stops it for the turn.
MAILBOX_WIDE = ("auth", "denied")
EVENT_DAYS = 3
_CREDENTIAL = {"reauth_required": "auth", "broker_auth_failed": "auth", "record_changed": "auth",
               "invalid_response": "auth", "account_changed": "auth", "permission_denied": "denied",
               "network_error": "network"}
PHRASES = {"timeout": "timed out", "not_found": "not found on the server (deleted or moved)",
           "server": "server error", "network": "network error", "auth": "authorization expired",
           "denied": "permission denied", "throttled": "throttled", "refused": "request refused",
           "unavailable": "provider unavailable"}
NAMES = {"outlook": "Outlook", "gmail": "Gmail"}


def failure(error) -> str | None:
    """What a mailbox's failure was, as one word of PHRASES; None when it is not a mailbox's.

    A bug in REM is not a provider failure: it still stops the command, so it is seen."""
    from ..provider_credentials import ProviderCredentialError
    from .mail import error_status
    if isinstance(error, ProviderCredentialError) and error.code in _CREDENTIAL:
        return _CREDENTIAL[error.code]
    status = error_status(error)
    if status is not None:
        return _by_status(status)
    name = type(error).__name__.lower()
    if isinstance(error, TimeoutError) or "timeout" in name or "timed out" in str(error).lower():
        return "timeout"
    if any(part in name for part in ("connecterror", "connectionerror", "networkerror", "protocolerror")):
        return "network"
    if isinstance(error, ProviderCredentialError):
        return "unavailable"
    return None


def _by_status(status: int) -> str:
    if status == 404:
        return "not_found"
    if status == 401:
        return "auth"
    if status == 403:
        return "denied"
    if status == 429:
        return "throttled"
    return "server" if status >= 500 else "refused"


class Labelled:
    """A mail client whose exceptions carry the mailbox they came from.

    The exception itself passes through unchanged, so every caller that
    classifies or retries it still sees the provider's own type and status."""

    def __init__(self, kind: str, client):
        self._kind, self._client = kind, client

    def __getattr__(self, name):
        value = getattr(self._client, name)
        if not callable(value):
            return value

        @functools.wraps(value)
        def call(*args, **kwargs):
            try:
                return value(*args, **kwargs)
            except Exception as error:
                error.rem_provider = self._kind
                raise
        return call


def labelled(clients: dict) -> dict:
    return {kind: Labelled(kind, client) for kind, client in clients.items()}


def _turn() -> str:
    # The scheduled turn's id reaches every `next` it runs (codex_exec); a
    # `next` typed by hand is a turn of its own.
    return os.environ.get("CO_REM_TURN_ID") or f"pid-{os.getpid()}"


def _ledger(root) -> dict:
    ledger = read_json(state_path(root, LEDGER), {})
    return {"items": ledger.get("items", {}), "events": ledger.get("events", []),
            "turn": ledger.get("turn") if (ledger.get("turn") or {}).get("id") == _turn()
            else {"id": _turn(), "failed": {}, "stopped": {}}}


def park(root, job: dict, error) -> str | None:
    """Set the round's `job` aside after a mailbox failed while preparing it: the notice to print, or None.

    None means the error is not a mailbox's, and the caller re-raises it."""
    # Only an error a mail client raised (Labelled tags it) is a mailbox's: a git or
    # web fetch timing out in a project or skill page is not mail, and must be seen.
    provider, reason = getattr(error, "rem_provider", None), failure(error)
    if provider is None or reason is None:
        return None
    record = job["record"]
    ledger, moment = _ledger(root), service.now()
    attempts = ledger["items"].get(record, {}).get("attempts", 0) + 1
    retry = moment + timedelta(hours=BACKOFF_HOURS[min(attempts, len(BACKOFF_HOURS)) - 1])
    ledger["items"][record] = {"provider": provider, "reason": reason, "attempts": attempts, "job": job,
                               "at": moment.isoformat(), "retry_at": retry.isoformat()}
    failed = ledger["turn"]["failed"].setdefault(provider, [])
    if record not in failed:
        failed.append(record)
    stops = reason in MAILBOX_WIDE or len(failed) >= PROVIDER_STOP_PAGES
    if stops:
        ledger["turn"]["stopped"][provider] = reason
    cutoff = (moment - timedelta(days=EVENT_DAYS)).isoformat()
    ledger["events"] = [event for event in ledger["events"] if event["at"] >= cutoff] + [
        {"at": moment.isoformat(), "provider": provider, "reason": reason, "record": record,
         **({"stopped": True} if stops else {})}]
    write_json(state_path(root, LEDGER), ledger)
    name = NAMES.get(provider, provider)
    notice = f"Set {record} aside: {name} {PHRASES[reason]}; tried again no earlier than {retry:%Y-%m-%d %H:%M} UTC"
    if stops:
        notice += f". {name} is not asked again in this turn"
    return notice


def mailbox_down(root, provider: str, reason: str, while_doing: str) -> str:
    """A mailbox failed outside any one page (listing who wrote, reading a slot's mail).

    That is the mailbox, not a page: it is not asked again in this turn, and the
    night card says so. Four nights read no mail on the owner's notebook while a
    failing read was tried again at every slot."""
    ledger, moment = _ledger(root), service.now()
    ledger["turn"]["stopped"][provider] = reason
    cutoff = (moment - timedelta(days=EVENT_DAYS)).isoformat()
    ledger["events"] = [event for event in ledger["events"] if event["at"] >= cutoff] + [
        {"at": moment.isoformat(), "provider": provider, "reason": reason, "record": "", "stopped": True}]
    write_json(state_path(root, LEDGER), ledger)
    name = NAMES.get(provider, provider)
    return f"{name} {PHRASES[reason]} while {while_doing}; {name} is not asked again in this turn"


def failure_in_words(text: str, code: str = "") -> str:
    """A source read's recorded failure ("Outlook read failed: ReadTimeout"), as one word of PHRASES."""
    import re
    if code in _CREDENTIAL:
        return _CREDENTIAL[code]
    lowered = text.lower()
    if "timeout" in lowered or "timed out" in lowered:
        return "timeout"
    if "connect" in lowered or "network" in lowered:
        return "network"
    status = re.search(r"\b([45]\d\d)\b", text)
    return _by_status(int(status[1])) if status else "unavailable"


def hold(root, job: dict, providers: dict) -> None:
    """A page that needs a mailbox stopped for this turn waits for the next round, with no back-off:
    it was never asked, so it did not fail."""
    ledger, record = _ledger(root), job["record"]
    entry = ledger["items"].get(record, {})
    provider = sorted(providers)[0]
    ledger["items"][record] = {"provider": provider, "reason": providers[provider], "job": job,
                               "attempts": entry.get("attempts", 0), "at": service.now().isoformat(),
                               "retry_at": service.now().isoformat(), "held": _turn()}
    write_json(state_path(root, LEDGER), ledger)


def readmit(root, queued: set) -> list:
    """Pages held in an earlier turn, back in the open round: the stop lasted only that turn."""
    ledger = _live(root)
    earlier = [record for record, entry in ledger["items"].items() if entry.get("held") not in (None, _turn())]
    if not earlier:
        return []
    # The entry stays, unheld, so a page that fails again keeps its place in the back-off.
    for record in earlier:
        ledger["items"][record].pop("held")
    jobs = [ledger["items"][record]["job"] for record in earlier]
    write_json(state_path(root, LEDGER), ledger)
    return [job for job in jobs if job["record"] not in queued]


def _live(root) -> dict:
    """The ledger with every page that no longer exists dropped, and merged ones moved to where they live.

    A parked page merged away while it waited came back as a job, Notebook.read
    raised "Record not found", and every turn died on it again."""
    from .files import Notebook
    from .merge import resolve
    ledger, book, changed = _ledger(root), Notebook(root), False
    for record, entry in list(ledger["items"].items()):
        if book.exists(record):
            continue
        changed, now_at = True, resolve(root, record)
        ledger["items"].pop(record)
        if now_at != record and book.exists(now_at) and now_at not in ledger["items"]:
            ledger["items"][now_at] = {**entry, "job": {**entry["job"], "record": now_at}}
    if changed:
        write_json(state_path(root, LEDGER), ledger)
    return ledger


def waiting(root) -> set:
    """Parked pages whose retry time has not come: the round leaves them out."""
    moment = service.now().isoformat()
    return {record for record, entry in _live(root)["items"].items() if entry["retry_at"] > moment}


def due(root) -> dict:
    """Parked pages whose retry time has come, as the round's jobs they were.

    They come back even when nothing new arrived: the round that parked them
    has already counted their activity as seen."""
    moment = service.now().isoformat()
    return {record: entry["job"] for record, entry in _live(root)["items"].items() if entry["retry_at"] <= moment}


def clear(root, record: str) -> None:
    """The page was prepared: its back-off starts over next time."""
    ledger = read_json(state_path(root, LEDGER), {})
    if record in ledger.get("items", {}):
        ledger["items"].pop(record)
        write_json(state_path(root, LEDGER), ledger)


def stopped(root) -> dict:
    """Mailboxes not to ask again in this turn, with why."""
    return _ledger(root)["turn"]["stopped"]


def last_night(root) -> dict | None:
    """For the reader's night line: what failed in the last day, and every page still set aside.

    Read-only: the reader holds no maintenance lock, so a write here could race
    park() and reset the scheduled turn's stop. Pages that no longer exist are
    left out in memory; `next` prunes the file under its lock."""
    from .files import Notebook
    ledger, moment, book = _ledger(root), service.now(), Notebook(root)
    ledger["items"] = {record: entry for record, entry in ledger["items"].items() if book.exists(record)}
    since = (moment - timedelta(days=1)).isoformat()
    events = [event for event in ledger["events"] if event["at"] >= since]
    parked = sorted(({"record": record, **{key: entry[key] for key in ("provider", "reason", "retry_at")}}
                     for record, entry in ledger["items"].items()), key=lambda row: row["retry_at"])
    if not events and not parked:
        return None
    rows = events or parked
    provider = _most(row["provider"] for row in rows)
    return {"provider": NAMES.get(provider, provider),
            "reason": _most(row["reason"] for row in rows if row["provider"] == provider),
            "times": len(events), "pages": len({row["record"] for row in rows if row["record"]}),
            "stopped": any(event.get("stopped") for event in events), "parked": parked}


def _most(values) -> str:
    values = list(values)
    return max(sorted(set(values)), key=values.count)

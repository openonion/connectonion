"""While co ai runs, notice acceptances and questions on handoffs this agent sent.

It only polls the mailbox while a handoff sent in the last 14 days is waiting,
so an agent that never hands anything off makes no requests. `co handoff status`
reads the same replies on demand; this only saves the sender from asking.
"""

import json
import threading
from datetime import datetime, timedelta, timezone

from ..environment import global_config_dir
from . import replies

INTERVAL = 300
FRESH = timedelta(days=14)


def _waiting() -> list:
    folder = global_config_dir() / "handoff" / "sent"
    cutoff = datetime.now(timezone.utc) - FRESH
    paths = sorted(folder.glob("ho-*.json")) if folder.exists() else []
    return [p for p in paths if "secret" in (r := json.loads(p.read_text(encoding="utf-8")))
            and datetime.fromisoformat(r["sent_at"]) > cutoff]


def check() -> list[str]:
    """One pass: the lines worth telling the sender, each event once."""
    news = []
    for path in _waiting():
        record = json.loads(path.read_text(encoding="utf-8"))
        state = replies.settle(record)
        seen = record.get("seen", {"accepted": False, "questions": 0})
        who = state["accepted"]
        if who and not seen["accepted"]:
            replies.remember_peer(who["address"], who["mailbox"], record["id"])
            news.append(f"[handoff] {record['id']} accepted by {who['address']} ({who['mailbox']})")
        news += [f"[handoff] {record['id']} question: {q['text']}  (co handoff answer {record['id']} \"...\")"
                 for q in state["questions"][seen["questions"]:]]
        record["seen"] = {"accepted": bool(who), "questions": len(state["questions"])}
        path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    return news


def start(interval: int = INTERVAL) -> threading.Event:
    """Poll in a daemon thread until the returned event is set."""
    stop = threading.Event()

    def loop():
        while not stop.wait(interval):
            for line in check():
                print(line, flush=True)

    threading.Thread(target=loop, name="handoff-watch", daemon=True).start()
    return stop

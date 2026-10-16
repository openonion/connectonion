"""While co ai runs, notice acceptances, questions and results on handoffs this agent sent.

It only polls the mailbox while a handoff sent in the last 14 days is waiting,
so an agent that never hands anything off makes no requests. `co handoff status`
reads the same replies on demand; this only saves the sender from asking.
"""

import json
import threading
from datetime import datetime, timedelta, timezone

from ..environment import global_config_dir
from . import replies, transport

INTERVAL = 60   # a question waits on this; it reads the mailbox only while a handoff is waiting
FRESH = timedelta(days=14)


def _waiting() -> list:
    folder = global_config_dir() / "handoff" / "sent"
    cutoff = datetime.now(timezone.utc) - FRESH
    paths = sorted(folder.glob("ho-*.json")) if folder.exists() else []
    return [p for p in paths if "secret" in (r := json.loads(p.read_text(encoding="utf-8")))
            and datetime.fromisoformat(r["sent_at"]) > cutoff]


def check() -> list[str]:
    """One pass: the lines worth telling the sender, each event once."""
    news, waiting = [], _waiting()
    mails = transport.fetch() if waiting else []   # one mailbox read for every waiting handoff
    for path in waiting:
        record = json.loads(path.read_text(encoding="utf-8"))
        state = replies.settle(record, mails)
        seen = {"done": [], **record.get("seen", {"accepted": False, "questions": []})}
        told = replies.answered_keys({"answered": seen["questions"]}, state["questions"])   # 1.9.2b13 kept a count
        who = state["accepted"]
        if who and not seen["accepted"]:
            name = replies.remember_peer(who["address"], who["mailbox"], record["id"], record["to"], record.get("inbox", False),
                                         sealed=bool(record.get("key")))
            news.append(f"[handoff] {record['id']} accepted by {who['address']} ({who['mailbox']}), saved as {name}; they can send you handoff messages, not use your agent")
        news += [f"[handoff] {record['id']} question: {q['text']}  (co handoff answer {record['id']} \"...\")"
                 for q in state["questions"] if replies.question_key(q) not in told]
        news += [f"[handoff] {record['id']} done: {d['text']}  (co handoff status {record['id']})"
                 for d in state["done"] if d["at"] not in seen["done"]]
        replies.tell_owner_of_done(record, state)
        news += replies.answer_automatically(record, state)
        replies.tell_taken(record, state)
        record["seen"] = {"accepted": bool(who), "questions": [replies.question_key(q) for q in state["questions"]],
                          "done": [d["at"] for d in state["done"]]}
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

"""Relationship metrics checked against independent SQL on fictional mail."""

import json
import sqlite3
import time
from datetime import datetime, timedelta, timezone
from statistics import median

from connectonion.rem import store
from connectonion.rem.config import prepare
from connectonion.rem.files import Notebook, state_path, write_json

TODAY = "2026-11-07"
NOW = datetime(2026, 11, 8, tzinfo=timezone.utc)
OWNER = "owner@example.test"


def archive(root, count=10):
    prepare(root)
    notebook = Notebook(root)
    people, messages = [], []
    for person in range(count):
        address, record = f"person{person}@example.test", f"people/person{person}.md"
        notebook.stub_person(record, f"Person {person}", [address], email=address)
        people.append({"record": record, "addresses": [address], "last": "2020-01-01"})
        for thread in range(150):
            start = NOW - timedelta(days=1 + (thread * 7 + person * 11) % 500)
            for turn in range(4):
                incoming = (turn + thread) % 2 == 0
                messages.append({"source": "gmail", "type": "mail", "id": f"{person}-{thread}-{turn}",
                                 "thread": f"{person}-{thread}", "date": (start + timedelta(hours=turn)).isoformat(),
                                 "from": address if incoming else OWNER,
                                 "to": [OWNER if incoming else address], "subject": "Fictional exchange"})
    write_json(state_path(root, "map.json"), {"owner": {"addresses": [OWNER]}, "people": people})
    state_path(root, "source-inventory.jsonl").write_text("")
    store.refresh(root)
    with sqlite3.connect(store.db_path(root)) as db:
        db.executemany("insert into messages (id, source, thread, sender, recipients, time) values (?, ?, ?, ?, ?, ?)",
                       [("gmail:" + m["id"], m["source"], "mail:gmail:" + m["thread"], m["from"],
                         json.dumps(m["to"]), m["date"]) for m in messages])
    return people


def recount(db, address):
    sql = """with contact as (
        select *, sender = ? as incoming from messages
        where time <= ? and ((sender = ? and exists (select 1 from json_each(recipients) where value = ?))
          or (sender = ? and exists (select 1 from json_each(recipients) where value = ?)))
    ), turns as (
        select *, row_number() over (partition by thread order by time, id) as turn,
        lag(incoming) over (partition by thread order by time, id) as previous_side,
        lag(unixepoch(time)) over (partition by thread order by time, id) as previous_time from contact
    ) """
    params = (address, NOW.isoformat(), address, OWNER, OWNER, address)
    rows = db.execute(sql + "select time, incoming, turn, previous_side, unixepoch(time)-previous_time from turns", params).fetchall()
    weeks = [0] * 52
    beginning = (NOW - timedelta(weeks=52)).isoformat()
    for week, count in db.execute(sql + "select cast((unixepoch(time)-unixepoch(?))/604800 as integer), count(*) "
                                 "from contact where time >= ? and time < ? group by 1",
                                 params + (beginning, beginning, NOW.isoformat())):
        weeks[week] = count
    starts = [row for row in rows if row[2] == 1 and row[0] >= (NOW - timedelta(days=90)).isoformat()]
    recent = db.execute(sql + "select count(*) from contact where time >= ?", params +
                        ((NOW - timedelta(days=30)).isoformat(),)).fetchone()[0]
    prior = db.execute(sql + "select count(*) from contact where time >= ? and time < ?", params +
                       ((NOW - timedelta(days=120)).isoformat(), (NOW - timedelta(days=30)).isoformat())).fetchone()[0]
    replies = lambda side: [r[4] for r in rows if r[3] is not None and r[1] == side and r[1] != r[3]]
    return {"weekly_messages": weeks, "started_by_them": sum(r[1] for r in starts), "threads_90d": len(starts),
            "reply_seconds_them": median(replies(1)), "reply_seconds_owner": median(replies(0)),
            "messages_30d": recent, "messages_prior_90d": prior,
            "change_percent": round((recent * 3 / prior - 1) * 100, 1), "last_mail": max(r[0] for r in rows)}


def test_rem_relationship_stats_match_sql_for_ten_people_under_two_seconds(tmp_path):
    people = archive(tmp_path)
    started = time.monotonic()
    rows = store.people_table(tmp_path, today=TODAY)
    elapsed = time.monotonic() - started
    assert elapsed < 2
    with sqlite3.connect(store.db_path(tmp_path)) as db:
        assert db.execute("select count(*) from messages").fetchone()[0] == 6000
        for person in people:
            stats = next(r for r in rows if r["record"] == person["record"])["relationship"]
            expected = recount(db, person["addresses"][0])
            assert {key: stats[key] for key in expected} == expected
            assert stats["started_by_them_percent"] == round(expected["started_by_them"] / expected["threads_90d"] * 100, 1)
    print(f"6000-mail relationship stats: {elapsed:.3f}s")


def test_rem_relationship_stats_sort_by_mail_not_page_status_and_refresh(tmp_path):
    archive(tmp_path, count=2)
    with sqlite3.connect(store.db_path(tmp_path)) as db:
        db.execute("update messages set time = '2026-01-01T00:00:00+00:00' where sender = 'person0@example.test' or recipients like '%person0@example.test%'")
        db.execute("update people set last_contact = '2026-11-07' where record = 'people/person0.md'")
    rows = store.people_table(tmp_path, today="2026-11-07")
    assert [r["record"] for r in rows] == ["people/person1.md", "people/person0.md"]
    assert not rows[0]["relationship"]["quiet"]
    assert rows[1]["relationship"]["quiet"]
    assert store.person(tmp_path, rows[0]["record"])["relationship"]["weekly_messages"]
    # The existing sync refresh makes new indexed mail visible immediately.
    path = state_path(tmp_path, "source-inventory.jsonl")
    with path.open("a") as stream:
        stream.write(json.dumps({"type": "mail", "source": "gmail", "id": "new", "thread": "new",
                                 "from": OWNER, "to": ["person0@example.test"], "date": "2026-11-06T12:00:00Z"}) + "\n")
    store.refresh(tmp_path)
    rows = store.people_table(tmp_path, today="2026-11-07")
    assert not next(r for r in rows if r["record"] == "people/person0.md")["relationship"]["quiet"]


def test_rem_relationship_stats_ignore_third_parties_and_do_not_invent_replies(tmp_path):
    from connectonion.rem.relationship_stats import metrics
    def message(day, sender, recipients, thread="one"):
        return [day, thread, sender, recipients, datetime.fromisoformat(day).timestamp()]
    # Two owner messages before a reply: time starts at the latest owner message.
    rows = [message("2026-11-01T00:00:00+00:00", OWNER, ["person@example.test"]),
            message("2026-11-02T00:00:00+00:00", OWNER, ["person@example.test"]),
            message("2026-11-02T02:00:00+00:00", "person@example.test", [OWNER]),
            message("2026-11-04T00:00:00+00:00", "person@example.test", [OWNER], "unanswered")]
    stats = metrics(rows, {OWNER}, NOW)
    assert stats["reply_seconds_them"] == 7200
    assert stats["reply_seconds_owner"] is None
    assert stats["started_by_them_percent"] == 50
    assert stats["change_percent"] is None and stats["trend"] == "new"
    assert metrics([], {OWNER}, NOW)["trend"] == "no activity"


def test_rem_relationship_stats_match_both_owner_and_person_aliases(tmp_path):
    archive(tmp_path, count=1)
    with sqlite3.connect(store.db_path(tmp_path)) as db:
        db.execute("update people set emails = ?", (json.dumps(["person0@example.test", "alias@example.test"]),))
        db.execute("delete from messages")
        rows = [("a", "alias@example.test", ["owner-alias@example.test"]),
                ("b", "stranger@example.test", [OWNER, "alias@example.test"]),
                ("c", "alias@example.test", ["stranger@example.test"]),
                ("d", OWNER, ["alias@example.test", "person0@example.test"])]
        db.executemany("insert into messages (id, source, thread, sender, recipients, time) values (?, 'gmail', ?, ?, ?, ?)",
                       [(id, "mail:gmail:" + id, sender, json.dumps(to), "2026-11-06T00:00:00+00:00") for id, sender, to in rows])
    write_json(state_path(tmp_path, "mail/archive.json"), {"owner_addresses": ["owner-alias@example.test"]})
    stats = store.people_table(tmp_path, today="2026-11-07")[0]["relationship"]
    assert sum(stats["weekly_messages"]) == 2  # duplicates and third-party thread context excluded
    assert stats["started_by_them_percent"] == 50


def test_rem_relationship_stats_do_not_assign_third_party_thread_starts(tmp_path):
    archive(tmp_path, count=1)
    with sqlite3.connect(store.db_path(tmp_path)) as db:
        db.execute("delete from messages")
        db.executemany("insert into messages (id, thread, sender, recipients, time) values (?, 'mail:gmail:group', ?, ?, ?)",
                       [("a", "third@example.test", json.dumps([OWNER]), "2026-11-05T00:00:00+00:00"),
                        ("b", OWNER, json.dumps(["person0@example.test"]), "2026-11-06T00:00:00+00:00")])
    stats = store.people_table(tmp_path, today=TODAY)[0]["relationship"]
    assert sum(stats["weekly_messages"]) == 1
    assert stats["threads_90d"] == 0 and stats["started_by_them_percent"] is None


def test_rem_relationship_cli_table_defaults_to_recent_mail(tmp_path):
    from typer.testing import CliRunner
    from connectonion.cli.main import app
    archive(tmp_path, count=2)
    with sqlite3.connect(store.db_path(tmp_path)) as db:
        db.execute("update messages set time = '2020-01-01T00:00:00+00:00' where sender = 'person0@example.test' or recipients like '%person0@example.test%'")
        db.execute("update people set last_contact = '2026-11-07' where record = 'people/person0.md'")
    result = CliRunner().invoke(app, ["rem", "--root", str(tmp_path), "--json", "list", "people", "--table"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["data"][0]["record"] == "people/person1.md"

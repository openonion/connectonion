"""Every WeChat friend gets a page, not only the chats this Mac holds (#3347).

Owner, 2026-11-22: "为什么才 15 个微信联系人啊……我觉得你可以把微信所有的联系人都放上去啊". WeChat for Mac keeps
chats only for what was synced to it (25 of ~1,659 friends on his machine), so the address book (contact
local_type 1) is the list of people; chats only order them. A friend with nothing to read yet rests: no
investigation, no model call, until a chat or a mail arrives. Invented people only.
"""

import sqlite3
import time

from connectonion.rem import chat, onboard, people_pages
from connectonion.rem.files import Notebook, read_json, state_path

SUBS = {"wechat": {"id": "wechat", "kind": "wechat", "enabled": True, "consented": True}}

# username, remark, nick_name, verify_flag, local_type
CONTACTS = [
    ("wxid_quinn", "Quinn Harbour", "q", 0, 1),     # friend with chats on this Mac
    ("wxid_ines", "Ines Vale", "", 0, 1),           # friend the owner named, no chats here
    ("wxid_theo", "", "Theo", 0, 1),                # friend, nickname only, no chats here
    ("wxid_crowd", "", "Group Person", 0, 3),       # met only in a group: never a person
    ("wxid_dm", "", "Dee Stranger", 0, 3),          # not a friend, but wrote one-to-one: a chat row
    ("123@chatroom", "", "A Group", 0, 2),          # a group
    ("gh_news", "", "News Daily", 0, 1),            # an official account
    ("wxid_brand", "", "Kiln Media", 24, 1),        # a verified business
    ("wxid_owner", "", "Me", 0, 1),                 # the owner
    ("wxid_blank", "", "", 0, 1),                   # a friend with no name to title a page
]


def _contact_db(path, rows=CONTACTS):
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE contact (username TEXT, remark TEXT, nick_name TEXT, verify_flag INTEGER, local_type INTEGER)")
    conn.executemany("INSERT INTO contact VALUES (?, ?, ?, ?, ?)", rows)
    conn.commit()
    conn.close()
    return path.read_bytes()


def _engine(tmp_path, monkeypatch, said, rows=CONTACTS):
    from connectonion.useful_tools import wechat as engine
    data = _contact_db(tmp_path / "contact.db", rows)
    key = tmp_path / "keys.json"
    key.write_text("{}")
    monkeypatch.setattr(engine, "db_storage_in_use", lambda: tmp_path)
    monkeypatch.setattr(engine, "KEY_MAP", key)
    monkeypatch.setattr(engine, "key_for", lambda path: "x")
    monkeypatch.setattr(engine, "decrypt_db", lambda path, key: data)
    monkeypatch.setattr(engine, "owner_username", lambda storage: "wxid_owner")
    monkeypatch.setattr(engine, "all_messages", lambda storage, known: said)


def _said(*pairs):
    return [{"chat": chat_id, "chat_name": name, "sender": sender}
            for chat_id, name in pairs for sender in (chat_id, "wxid_owner")]


def test_every_friend_is_a_candidate_counted_from_chats_else_zero(tmp_path, monkeypatch):
    _engine(tmp_path, monkeypatch, _said(("wxid_quinn", "Quinn Harbour"), ("wxid_dm", "Dee Stranger")))
    people = {row["address"]: row for row in chat.wechat_people()}
    assert set(people) == {"wxid_quinn", "wxid_ines", "wxid_theo", "wxid_dm"}
    assert (people["wxid_quinn"]["mails"], people["wxid_quinn"]["friend"]) == (2, True)
    assert (people["wxid_ines"]["name"], people["wxid_ines"]["mails"], people["wxid_ines"]["remark"]) == ("Ines Vale", 0, True)
    assert (people["wxid_theo"]["name"], people["wxid_theo"]["remark"]) == ("Theo", False)   # the nickname titles it
    assert people["wxid_dm"]["friend"] is False   # wrote one-to-one, so a chat row as before


def test_a_friend_with_no_messages_gets_a_page_and_a_one_way_stranger_still_does_not(tmp_path):
    rows = [{"address": "wxid_ines", "name": "Ines Vale", "mails": 0, "sent": 0, "received": 0, "kind": "person",
             "friend": True, "remark": True},
            {"address": "wxid_dm", "name": "Dee Stranger", "mails": 1, "sent": 0, "received": 1, "kind": "person",
             "friend": False}]
    out = onboard.plan(tmp_path, rows, ("people",), write=True)["people"]
    assert [row["name"] for row in out["create"]] == ["Ines Vale"]
    assert out["skip"] == 1   # worth_a_page still applies to anyone not in the address book


def _rows(chats=("wxid_quinn",)):
    rows = [{"address": "wxid_quinn", "name": "Quinn Harbour", "remark": True},
            {"address": "wxid_ines", "name": "Ines Vale", "remark": True},
            {"address": "wxid_theo", "name": "Theo", "remark": False}]
    return [{**row, "kind": "wechat", "friend": True, "mails": 4 if row["address"] in chats else 0,
             "sent": 2 if row["address"] in chats else 0, "received": 2 if row["address"] in chats else 0}
            for row in rows]


def test_onboarding_ranks_chats_then_named_friends_then_the_rest_and_rests_pages_with_nothing_to_read(tmp_path, monkeypatch):
    monkeypatch.setattr("connectonion.rem.chat.wechat_people", lambda *a, **k: _rows())
    created = onboard.run_due(tmp_path, SUBS, night=True)
    assert len(created) == 3
    asked = read_json(state_path(tmp_path, onboard.ASKED), {})
    by_name = {Notebook(tmp_path).read(record).splitlines()[0].lstrip("# "): entry for record, entry in asked.items()}
    assert (by_name["Quinn Harbour"]["rank"], by_name["Quinn Harbour"]["material"]) == (0, True)
    assert (by_name["Ines Vale"]["rank"], by_name["Ines Vale"]["material"]) == (1, False)
    assert (by_name["Theo"]["rank"], by_name["Theo"]["material"]) == (2, False)
    # Only the friend with chats is queued: the two with nothing to read cost no investigation (no model call).
    queued = [row["record"] for row in people_pages.queue(tmp_path)]
    assert len(queued) == 1 and "Quinn" in Notebook(tmp_path).read(queued[0])
    assert sorted(onboard.idle(tmp_path)) == sorted(r for r in created if r not in queued)
    assert onboard.summary(tmp_path, "wechat")["no_chats_yet"] == 2
    # ... and `co rem investigate people --source wechat --new` finds only the page with something to read.
    assert onboard.touched(tmp_path, [{**r, "kind": "person"} for r in _rows()])["new"] == queued


def test_a_resting_friend_wakes_when_a_chat_arrives(tmp_path, monkeypatch):
    monkeypatch.setattr("connectonion.rem.chat.wechat_people", lambda *a, **k: _rows())
    onboard.run_due(tmp_path, SUBS, night=True)
    monkeypatch.setattr("connectonion.rem.chat.wechat_people", lambda *a, **k: _rows(chats=("wxid_quinn", "wxid_theo")))
    assert onboard.run_due(tmp_path, SUBS, night=True) == []   # nothing new to create
    queued = [Notebook(tmp_path).read(row["record"]).splitlines()[0] for row in people_pages.queue(tmp_path)]
    assert queued == ["# Quinn Harbour", "# Theo"]   # Theo now has a chat: first in line, at rank 0
    assert len(onboard.idle(tmp_path)) == 1   # Ines still rests


def test_the_address_book_maps_in_seconds_and_a_second_run_changes_nothing(tmp_path, monkeypatch):
    many = [{"address": f"wxid_friend{i:04d}", "name": f"Friend {i:04d}", "kind": "wechat", "friend": True,
             "remark": i % 3 == 0, "mails": 0, "sent": 0, "received": 0} for i in range(1700)]
    monkeypatch.setattr("connectonion.rem.chat.wechat_people", lambda *a, **k: many)
    started = time.monotonic()
    created = onboard.run_due(tmp_path, SUBS, night=True)
    took = time.monotonic() - started
    assert len(created) == 1700
    assert took < 30, f"mapping 1,700 friends took {took:.1f}s"
    pages = sorted(p.name for p in (tmp_path / "people").glob("*.md"))
    assert onboard.run_due(tmp_path, SUBS, night=True) == []
    assert sorted(p.name for p in (tmp_path / "people").glob("*.md")) == pages
    assert people_pages.queue(tmp_path) == []   # all 1,700 rest: none has anything to read


def test_the_map_says_once_how_to_bring_more_chats_over_when_few_friends_have_any():
    from connectonion.cli.commands.rem_commands import _map_summary
    report = {"wechat": {"people": {"create": [{"name": "Ines Vale"}], "merge": [], "known": 0, "skip": 0,
                                    "friends": 1659, "chats": 25}}}
    text = _map_summary(report, dry_run=True)
    assert text.count("迁移到电脑") == 1 and "Only 25 of 1659 WeChat friends have chats on this Mac" in text
    report["wechat"]["people"]["chats"] = 900
    assert "迁移到电脑" not in _map_summary(report, dry_run=True)


def test_a_wecom_friend_whose_id_has_an_at_sign_is_mapped_once(tmp_path, monkeypatch):
    # A WeCom contact's WeChat id ends "@openim": a handle, not mail. Written to Handles alone, it never reached
    # the roster, so every night stubbed that friend again (found on the owner's clone, #3347).
    rows = [{"address": "abc123def@openim", "name": "Wren", "kind": "wechat", "friend": True, "remark": False,
             "mails": 0, "sent": 0, "received": 0}]
    monkeypatch.setattr("connectonion.rem.chat.wechat_people", lambda *a, **k: rows)
    assert len(onboard.run_due(tmp_path, SUBS, night=True)) == 1
    assert onboard.plan(tmp_path, [{**rows[0], "kind": "person"}], ("people",), write=False)["people"]["create"] == []


def test_same_person_finds_the_same_pairs_without_comparing_every_pair():
    # ~1.8k people made the all-pairs sweep 1.6M comparisons on every status and page build (#3347). The
    # indexed candidates must find exactly the pairs the sweep found.
    import random
    from connectonion.rem import same_person
    rng = random.Random(7)
    first = ["Mara", "Quinn", "Ines", "Theo", "Wren", "Dee", "Ody", "Lark"]
    last = ["Ostrowski", "Harbour", "Vale", "Kiln", "Pike", "Ash"]
    roster, mapped = [], {}
    for i in range(400):
        title = rng.choice([f"{rng.choice(first)} {rng.choice(last)}", rng.choice(first), f"{rng.choice(first)} (Q)"])
        aliases = rng.sample(first + last, rng.randint(0, 2))
        emails = [f"p{i}@example.org"] if i % 5 == 0 else []
        roster.append({"path": f"people/p{i:03d}.md", "title": title, "aliases": aliases, "emails": emails})
    for i in range(0, 400, 10):
        mapped[f"p{i}@example.org"] = f"people/p{(i + 3) % 400:03d}.md"

    def tie(one, other):
        shared = [e for e in one["emails"] if mapped.get(e) == other["path"]] + [
            e for e in other["emails"] if mapped.get(e) == one["path"]]
        return bool(shared) or bool(same_person._alike(one, other))

    brute = [(i, j) for i in range(len(roster)) for j in range(i + 1, len(roster)) if tie(roster[i], roster[j])]
    close = same_person._close(roster, mapped)
    assert [(i, j) for i, j in close if tie(roster[i], roster[j])] == brute
    assert len(close) < len(roster) * (len(roster) - 1) // 2


def _fts_db(path):
    """WeChat's full-text index as message_fts.db stores it: content tables c0..c6 plus name2id."""
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE name2id (username TEXT)")
    conn.executemany("INSERT INTO name2id (rowid, username) VALUES (?, ?)",
                     [(1, "wxid_quinn"), (2, "wxid_ines"), (3, "wxid_owner"), (4, "99@chatroom"), (5, "wxid_crowd")])
    conn.execute("CREATE TABLE message_fts_v4_0_content (id INTEGER PRIMARY KEY, c0, c1, c2, c3, c4, c5, c6)")
    conn.executemany("INSERT INTO message_fts_v4_0_content (c0, c1, c2, c3, c4, c5, c6) VALUES (?, ?, ?, ?, ?, ?, ?)", [
        ("周三见", 7, 7000, 1, 1, 1, 1763000000),            # Quinn, also in message_0.db (local id 7)
        ("好的", 8, 8000, 1, 1, 3, 1763000100),              # the owner to Quinn, only in the index
        ("下周有空吗", 1, 1000, 1, 2, 2, 1763000200),         # Ines: history only the index holds
        ("", 2, 2000, 3, 2, 3, 1763000300),                   # a picture to Ines
        ("wxid_crowd:\n大家好", 3, 3000, 1, 4, 5, 1763000400)])  # a group line
    conn.commit()
    conn.close()


def test_the_full_text_index_supplies_chats_the_message_databases_cannot(tmp_path, monkeypatch):
    from connectonion.useful_tools import wechat as engine
    (tmp_path / "message").mkdir()
    _fts_db(tmp_path / "message" / "message_fts.db")
    monkeypatch.setattr(engine, "key_for", lambda path: "x")
    monkeypatch.setattr(engine, "decrypt_db", lambda path, key: path.read_bytes())
    monkeypatch.setattr(engine, "all_messages", lambda storage, known: [
        {"id": "7", "chat": "wxid_quinn", "chat_name": "Quinn Harbour", "at": "", "text": "周三见",
         "sender": "wxid_quinn", "sender_name": "Quinn Harbour", "kind": "text"}])
    fts = engine.fts_messages(tmp_path, {"wxid_quinn": "Quinn Harbour"})
    assert len(fts) == 5
    group = next(row for row in fts if row["chat"] == "99@chatroom")
    assert (group["sender"], group["text"]) == ("wxid_crowd", "大家好")
    assert next(row for row in fts if row["id"] == "2")["text"] == "[图片]"
    rows = engine.every_message(tmp_path, {})
    assert len(rows) == 5   # Quinn's local id 7 came from message_0.db; the index's copy is dropped
    assert sorted((row["chat"], row["id"]) for row in rows if row["chat"] != "99@chatroom") == [
        ("wxid_ines", "1"), ("wxid_ines", "2"), ("wxid_quinn", "7"), ("wxid_quinn", "8")]


def test_a_friend_whose_chats_only_the_index_holds_is_counted_and_read_first(tmp_path, monkeypatch):
    from connectonion.useful_tools import wechat as engine
    _engine(tmp_path, monkeypatch, _said(("wxid_quinn", "Quinn Harbour")))
    monkeypatch.setattr(engine, "fts_messages", lambda storage, known: [
        {"id": "1", "chat": "wxid_ines", "chat_name": "Ines Vale", "sender": "wxid_ines"},
        {"id": "2", "chat": "wxid_ines", "chat_name": "Ines Vale", "sender": "wxid_owner"}])
    people = {row["address"]: row for row in chat.wechat_people()}
    assert (people["wxid_ines"]["sent"], people["wxid_ines"]["received"]) == (1, 1)
    assert people["wxid_theo"]["mails"] == 0


def test_the_map_reports_the_address_book_against_the_chats_found():
    from connectonion.cli.commands.rem_commands import _map_summary
    report = {"wechat": {"people": {"create": [], "merge": [], "known": 0, "skip": 0, "friends": 1659, "chats": 1428}}}
    text = _map_summary(report, dry_run=True)
    assert "微信好友 1,659 · 找到聊天 1,428 · 还缺 231" in text
    assert "迁移到电脑" not in text   # most friends have chats: no migration nag


def test_each_chat_says_when_you_last_talked_who_wrote_last_and_how_much_lately(tmp_path, monkeypatch):
    # People's columns read these (#3346): the later of mail and WeChat is the last contact.
    from datetime import datetime, timedelta, timezone
    now = datetime.now(timezone.utc)
    said = [{"chat": "wxid_quinn", "chat_name": "Quinn Harbour", "sender": "wxid_quinn", "at": (now - timedelta(days=200)).isoformat()},
            {"chat": "wxid_quinn", "chat_name": "Quinn Harbour", "sender": "wxid_quinn", "at": (now - timedelta(days=10)).isoformat()},
            {"chat": "wxid_quinn", "chat_name": "Quinn Harbour", "sender": "wxid_owner", "at": (now - timedelta(days=2)).isoformat()}]
    _engine(tmp_path, monkeypatch, said)
    quinn = next(row for row in chat.wechat_people() if row["address"] == "wxid_quinn")
    assert quinn["last"] == said[-1]["at"] and quinn["last_mine"] is True and quinn["n90"] == 2


def test_the_map_keeps_chat_activity_by_page_for_the_reader(tmp_path, monkeypatch):
    rows = [{**row, "last": "2026-11-20T10:00:00+00:00" if row["address"] == "wxid_quinn" else "",
             "last_mine": False, "n90": 6 if row["address"] == "wxid_quinn" else 0} for row in _rows()]
    monkeypatch.setattr("connectonion.rem.chat.wechat_people", lambda *a, **k: rows)
    onboard.run_due(tmp_path, SUBS, night=True)
    found = onboard.activity(tmp_path)
    assert len(found) == 1   # only the friend with chats
    (record, entry), = found.items()
    assert "Quinn" in Notebook(tmp_path).read(record) and (entry["n90"], entry["mine"]) == (6, False)


def test_the_coverage_line_counts_the_chats_the_index_holds(tmp_path, monkeypatch):
    # #3353's text_coverage prefers fts_chat_ids (a cheap read) and calls the readers with db_storage alone.
    from connectonion.useful_tools import wechat as engine
    (tmp_path / "message").mkdir()
    _fts_db(tmp_path / "message" / "message_fts.db")
    monkeypatch.setattr(engine, "key_for", lambda path: "x")
    monkeypatch.setattr(engine, "decrypt_db", lambda path, key: path.read_bytes())
    assert engine.fts_chat_ids(tmp_path) == {"wxid_quinn", "wxid_ines", "99@chatroom"}
    assert len(engine.fts_messages(tmp_path)) == 5
    monkeypatch.setattr(engine, "friend_count", lambda storage: 3)
    assert engine.text_coverage(tmp_path) == {"friends": 3, "with_chats": 2, "missing": 1}

"""不是人 works on a WeChat contact and sticks at night; verified accounts never reach the people map (#3339).

Found running `co rem map people --source wechat` on the owner's notebook: two of the fifteen pages it made were
a business and a brand. The 不是人 mark took only a mail address, so a WeChat-only page couldn't be set aside, and
the night re-maps WeChat, so a page deleted by hand would come back. Invented people and ids only.
"""

import json
import sqlite3

from tests.unit.test_rem_live_reader import call, host  # noqa: F401
from connectonion.rem import census, onboard, threads
from connectonion.rem.files import Notebook, person_handle

CONTACTS = [
    {"address": "wxid_quinn", "name": "Quinn Harbour", "mails": 4, "sent": 2, "received": 2},
    {"address": "wxid_kilnshop", "name": "Kiln Rentals", "mails": 6, "sent": 3, "received": 3},
]
SUBS = {"wechat": {"id": "wechat", "kind": "wechat", "enabled": True, "consented": True}}


def _rows():
    return [{"kind": "person", **row} for row in CONTACTS]


def test_a_chat_handle_is_one_markable_handle_and_a_pattern_is_not():
    assert person_handle("wxid_quinn") and person_handle("quinn-h_2026") and person_handle("ana@example.com")
    for text in ("", "q", "a b", "*", "wxid_*", "two words", "../x", "a@b"):
        assert not person_handle(text), text


def test_a_wechat_id_can_be_marked_not_a_person_and_undone(tmp_path):
    threads.mark_person(tmp_path, "wxid_KilnShop", person=False)
    assert threads.person_marks(tmp_path) == {"wxid_kilnshop": "not-person"}
    threads.mark_person(tmp_path, "wxid_kilnshop", person=None)
    assert threads.person_marks(tmp_path) == {}


def test_a_marked_wechat_contact_is_never_stubbed_by_the_map(tmp_path):
    book = Notebook(tmp_path)
    threads.mark_person(tmp_path, "wxid_kilnshop", person=False)
    out = onboard.plan(tmp_path, _rows(), ("people",), write=True)["people"]
    assert [row["name"] for row in out["create"]] == ["Quinn Harbour"]
    assert out["not_person"] == 1
    assert not any("wxid_kilnshop" in book.read(path) for path in book.list("people"))


def test_the_night_does_not_bring_a_marked_contact_back(tmp_path, monkeypatch):
    book = Notebook(tmp_path)
    monkeypatch.setattr("connectonion.rem.chat.wechat_people", lambda *a, **k: [{**r, "kind": "wechat"} for r in CONTACTS])
    created = onboard.run_due(tmp_path, SUBS, night=True)
    shop = next(path for path in created if "wxid_kilnshop" in book.read(path))
    threads.mark_person(tmp_path, "wxid_kilnshop", person=False)
    book.path(shop).unlink()                                  # the owner deleted it by hand
    assert onboard.run_due(tmp_path, SUBS, night=True) == []  # the next night doesn't make it again
    assert not book.exists(shop)


def test_a_wechat_only_page_marked_not_a_person_leaves_people(tmp_path):
    book = Notebook(tmp_path)
    onboard.plan(tmp_path, _rows(), ("people",), write=True)
    shop = next(path for path in book.list("people") if "wxid_kilnshop" in book.read(path))
    assert census.pages(tmp_path)[shop]["service"] is False
    threads.mark_person(tmp_path, "wxid_kilnshop", person=False)
    entry = census.pages(tmp_path)[shop]
    assert entry["service"] is True and entry["agent"] is True     # set aside, listed with 是人 to undo


def test_a_mail_page_still_reads_its_addresses_alone(tmp_path):
    # An extra handle on a mail page (a GitHub name, a WeChat id) must not block the owner's mark on the address.
    book = Notebook(tmp_path)
    record = "people/ember-0000000001.md"
    book.stub_person(record, "Ember Assistant", ["ember@kiln.example", "emberbot", "wxid_ember"], email="ember@kiln.example")
    threads.mark_person(tmp_path, "ember@kiln.example", person=False)
    assert census.pages(tmp_path)[record]["service"] is True


def test_rem_person_takes_a_wechat_id(host):  # noqa: F811
    cookie = f"co_rem={host.token}"
    out = json.dumps({"address": "wxid_kilnshop", "person": False}).encode()
    status, _, body = call(host.routes, "POST", "/rem/person", cookie=cookie, body=out)
    assert status == 200 and json.loads(body)["marks"] == {"wxid_kilnshop": "not-person"}
    for value in ({"address": "wxid_*", "person": False}, {"address": "two words", "person": False}):
        assert call(host.routes, "POST", "/rem/person", cookie=cookie, body=json.dumps(value).encode())[0] == 400


def _contact_db(path):
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE contact (username TEXT, remark TEXT, nick_name TEXT, verify_flag INTEGER)")
    conn.executemany("INSERT INTO contact VALUES (?, ?, ?, ?)", [
        ("wxid_quinn", "Quinn Harbour", "", 0), ("wxid_brand", "", "Kiln Media", 24), ("wxid_owner", "", "Me", 0)])
    conn.commit()
    conn.close()
    return path.read_bytes()


def test_verified_accounts_are_the_contacts_with_a_verify_flag(tmp_path):
    from connectonion.useful_tools import wechat as engine
    conn = engine.open_readonly(_contact_db(tmp_path / "contact.db"))
    assert engine.verified_accounts(conn) == {"wxid_brand"}


def test_a_verified_account_never_becomes_a_people_candidate(tmp_path, monkeypatch):
    from connectonion.rem import chat
    from connectonion.useful_tools import wechat as engine
    data = _contact_db(tmp_path / "contact.db")
    key = tmp_path / "keys.json"
    key.write_text("{}")
    monkeypatch.setattr(engine, "db_storage_in_use", lambda: tmp_path)
    monkeypatch.setattr(engine, "KEY_MAP", key)
    monkeypatch.setattr(engine, "key_for", lambda path: "x")
    monkeypatch.setattr(engine, "decrypt_db", lambda path, key: data)
    monkeypatch.setattr(engine, "owner_username", lambda storage: "wxid_owner")
    said = [{"chat": chat_id, "chat_name": name, "sender": sender} for chat_id, name in
            (("wxid_quinn", "Quinn Harbour"), ("wxid_brand", "Kiln Media")) for sender in (chat_id, "wxid_owner")]
    monkeypatch.setattr(engine, "all_messages", lambda storage, known: said)
    assert [row["address"] for row in chat.wechat_people()] == ["wxid_quinn"]


def test_the_map_summary_puts_each_name_list_after_its_own_count():
    from connectonion.cli.commands.rem_commands import _map_summary
    report = {"wechat": {"people": {"create": [{"name": "Quinn Harbour"}, {"name": "Ines Vale"}], "merge": [],
                                    "known": 0, "skip": 10, "not_person": 1}}}
    text = _map_summary(report, dry_run=False)
    first, second = text.splitlines()[:2]
    assert first == "wechat · people: created 2: Quinn Harbour, Ines Vale"
    assert "not worth a page 10" in second and "Quinn" not in second and "not a person by your mark 1" in second
    assert "co rem investigate people --source wechat --new" in text
    assert "Dry run: nothing was written." in _map_summary(report, dry_run=True)


def test_a_contact_table_without_verify_flag_still_yields_people(tmp_path):
    from connectonion.useful_tools import wechat as engine
    path = tmp_path / "old.db"
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE contact (username TEXT, remark TEXT, nick_name TEXT)")
    conn.commit()
    conn.close()
    assert engine.verified_accounts(engine.open_readonly(path.read_bytes())) == set()

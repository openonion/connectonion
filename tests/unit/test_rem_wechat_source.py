"""WeChat as a co rem source (#3261): read straight from WeChat for Mac, no intermediate files.

"*" reads every one-to-one chat (people) and never a group or an official account unless named.
"""
from connectonion.rem import chat, service


def _row(n, chat_id, text, sender="wxid_mara"):
    return {"id": str(n), "chat": chat_id, "chat_name": "Mara", "at": f"2026-11-20T0{n}:00:00+00:00",
            "text": text, "sender": sender, "sender_name": "Mara", "kind": "text"}


def _streams(monkeypatch, rows, owner="wxid_me"):
    other = [r for r in rows if r["sender"] != owner]
    mine = [r for r in rows if r["sender"] == owner]
    monkeypatch.setattr(chat, "_wechat_streams", lambda: (("other", other), ("user", mine)))


def _sub(chats):
    return {"kind": "wechat", "root": "unused", "chats": chats, "since": "2026-01-01T00:00:00+00:00",
            "enabled": True, "consented": True}


def test_every_person_reads_one_to_one_chats_not_groups_or_official_accounts(monkeypatch):
    _streams(monkeypatch, [_row(1, "wxid_mara", "明天交合同"), _row(2, "123@chatroom", "group chatter"),
                           _row(3, "gh_news", "today's headlines"), _row(4, "filehelper", "note to self")])
    items = chat.collect_chat(_sub(["*"]), {}, 50, 100_000).items
    assert [i["text"] for i in items] == ["明天交合同"]
    assert items[0]["source"].startswith("wechat:")


def test_a_named_group_is_read_alongside_people(monkeypatch):
    _streams(monkeypatch, [_row(1, "wxid_mara", "hi"), _row(2, "123@chatroom", "group plan")])
    items = chat.collect_chat(_sub(["*", "123@chatroom"]), {}, 50, 100_000).items
    assert {i["correspondent"] for i in items} == {"wxid_mara", "123@chatroom"}


def test_both_sides_are_kept(monkeypatch):
    _streams(monkeypatch, [_row(1, "wxid_mara", "交了吗"), _row(2, "wxid_mara", "交了", sender="wxid_me")])
    roles = {i["role"] for i in chat.collect_chat(_sub(["*"]), {}, 50, 100_000).items}
    assert roles == {"other", "user"}


def test_wechat_is_offered_off_until_chosen(tmp_path):
    from connectonion.rem.config import prepare
    prepare(tmp_path / "rem")
    sub = service.subscriptions(tmp_path / "rem")["wechat"]
    assert sub["kind"] == "wechat" and sub["chats"] == ["*"]
    assert sub["enabled"] is False and sub["consented"] is False

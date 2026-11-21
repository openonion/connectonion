"""WeChat as a co rem source (#3261): the same inbox files as WhatsApp, written by `co wechat sync`.

"*" reads every one-to-one chat (people) and never a group or an official account unless named.
"""
import json

from connectonion.rem import chat, service


def _inbox(home, rows):
    home.mkdir(parents=True)
    (home / "received.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))


def _row(n, chat_id, text, sender="wxid_mara"):
    return {"id": str(n), "chat": chat_id, "at": f"2026-11-20T0{n}:00:00+00:00", "text": text,
            "sender": sender, "sender_name": "Mara", "kind": "text"}


def test_every_person_reads_one_to_one_chats_not_groups_or_official_accounts(tmp_path, monkeypatch):
    monkeypatch.setattr(chat, "_sync_wechat", lambda: None)
    home = tmp_path / "wechat"
    _inbox(home, [_row(1, "wxid_mara", "明天交合同"), _row(2, "123@chatroom", "group chatter"),
                  _row(3, "gh_news", "today's headlines"), _row(4, "filehelper", "note to self")])
    sub = {"kind": "wechat", "root": str(home), "chats": ["*"], "since": "2026-01-01T00:00:00+00:00",
           "enabled": True, "consented": True}
    items = chat.collect_chat(sub, {}, 50, 100_000).items
    assert [i["text"] for i in items] == ["明天交合同"]
    assert items[0]["source"].startswith("wechat:")


def test_a_named_group_is_read_alongside_people(tmp_path, monkeypatch):
    monkeypatch.setattr(chat, "_sync_wechat", lambda: None)
    home = tmp_path / "wechat"
    _inbox(home, [_row(1, "wxid_mara", "hi"), _row(2, "123@chatroom", "group plan")])
    sub = {"kind": "wechat", "root": str(home), "chats": ["*", "123@chatroom"], "since": "2026-01-01T00:00:00+00:00",
           "enabled": True, "consented": True}
    assert {i["correspondent"] for i in chat.collect_chat(sub, {}, 50, 100_000).items} == {"wxid_mara", "123@chatroom"}


def test_wechat_is_offered_off_until_chosen(tmp_path):
    from connectonion.rem.config import prepare
    prepare(tmp_path / "rem")
    sub = service.subscriptions(tmp_path / "rem")["wechat"]
    assert sub["kind"] == "wechat" and sub["chats"] == ["*"]
    assert sub["enabled"] is False and sub["consented"] is False

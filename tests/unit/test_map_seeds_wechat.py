"""The map seeds people from the WeChat source (#3279): a chat-only contact becomes a person, named pages
merge with mail by name, and the WeChat id is the investigation handle.
"""
from connectonion.rem import chat, map as rem_map


def test_chat_people_rows_only_when_wechat_is_enabled(monkeypatch):
    rows = [{"address": "wxid_mara", "name": "Mara Ostrowski", "mails": 5, "sent": 2, "received": 3, "kind": "wechat"}]
    monkeypatch.setattr(chat, "wechat_people", lambda *a, **k: rows)
    assert rem_map._chat_people_rows({"wechat": {"kind": "wechat", "enabled": True}}) == rows
    assert rem_map._chat_people_rows({"wechat": {"kind": "wechat", "enabled": False}}) == []
    assert rem_map._chat_people_rows({"gmail": {"kind": "gmail", "enabled": True}}) == []


def test_wechat_people_keeps_named_one_to_one_chats_only(monkeypatch):
    from connectonion.useful_tools import wechat as engine
    monkeypatch.setattr(engine, "db_storage_in_use", lambda: __import__("pathlib").Path("/tmp/x"))
    monkeypatch.setattr(engine, "KEY_MAP", __import__("pathlib").Path(__file__))  # any existing file
    monkeypatch.setattr(engine, "key_for", lambda p: "k")
    monkeypatch.setattr(engine, "decrypt_db", lambda p, k: b"")
    monkeypatch.setattr(engine, "open_readonly", lambda b: None)
    monkeypatch.setattr(engine, "owner_username", lambda d: "wxid_me")
    monkeypatch.setattr(engine, "names", lambda conn: {"wxid_mara": "Mara", "123@chatroom": "Group", "gh_news": "News"})
    monkeypatch.setattr(engine, "all_messages", lambda d, known: [
        {"chat": "wxid_mara", "chat_name": "Mara", "sender": "wxid_mara"},
        {"chat": "wxid_mara", "chat_name": "Mara", "sender": "wxid_me"},
        {"chat": "123@chatroom", "chat_name": "Group", "sender": "wxid_x"},   # group, out
        {"chat": "gh_news", "chat_name": "News", "sender": "gh_news"},        # official account, out
        {"chat": "wxid_noname", "chat_name": "wxid_noname", "sender": "wxid_noname"}])  # no real name, out
    people = chat.wechat_people()
    assert [(p["address"], p["name"], p["mails"], p["sent"], p["received"]) for p in people] == [("wxid_mara", "Mara", 2, 1, 1)]

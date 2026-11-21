"""The map seeds people from the WeChat source (#3279): a chat-only contact becomes a person, named pages
merge with mail by name, and the WeChat id is the investigation handle.
"""
from connectonion.rem import chat, map as rem_map


def test_chat_people_rows_only_when_wechat_is_enabled_and_consented(monkeypatch):
    rows = [{"address": "wxid_mara", "name": "Mara Ostrowski", "mails": 5, "sent": 2, "received": 3, "kind": "wechat"}]
    monkeypatch.setattr(chat, "wechat_people", lambda *a, **k: rows)
    on = {"wechat": {"kind": "wechat", "enabled": True, "consented": True}}
    assert rem_map._chat_people_rows(on) == rows
    # Enabled but not consented seeds nothing, matching the chat reader's gate (#3289).
    assert rem_map._chat_people_rows({"wechat": {"kind": "wechat", "enabled": True, "consented": False}}) == []
    assert rem_map._chat_people_rows({"wechat": {"kind": "wechat", "enabled": False, "consented": True}}) == []
    assert rem_map._chat_people_rows({"gmail": {"kind": "gmail", "enabled": True, "consented": True}}) == []


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


def test_wechat_is_on_by_default_once_keys_are_captured(tmp_path, monkeypatch):
    from connectonion.rem import service
    from connectonion.rem.config import prepare
    import connectonion.rem.service as svc
    prepare(tmp_path / "rem")
    # No keys yet: offered, off.
    monkeypatch.setattr(svc.Path, "home", staticmethod(lambda: tmp_path / "nokeys"))
    off = service.subscriptions(tmp_path / "rem")["wechat"]
    assert off["enabled"] is False and off["adapter"] == "waiting for co wechat"
    # Keys captured: on by default, no prompt (context over control).
    home = tmp_path / "haskeys"
    (home / ".co" / "wechat").mkdir(parents=True)
    (home / ".co" / "wechat" / "keys.json").write_text("{}")
    monkeypatch.setattr(svc.Path, "home", staticmethod(lambda: home))
    on = service.subscriptions(tmp_path / "rem")["wechat"]
    assert on["enabled"] is True and on["consented"] is True and on["chats"] == ["*"]


def test_seed_chat_people_adds_new_two_way_contacts_only(tmp_path, monkeypatch):
    from connectonion.rem import chat
    from connectonion.rem.config import prepare
    from connectonion.rem.files import Notebook
    prepare(tmp_path / "rem")
    nb = Notebook(tmp_path / "rem")
    nb.stub_person("people/known.md", "Mara Ostrowski", ["wxid_mara"])  # already has this handle
    monkeypatch.setattr(chat, "wechat_people", lambda *a, **k: [
        {"address": "wxid_mara", "name": "Mara Ostrowski", "mails": 9, "sent": 4, "received": 5, "kind": "wechat"},
        {"address": "wxid_quinn", "name": "Quinn Alder", "mails": 6, "sent": 2, "received": 4, "kind": "wechat"},
        {"address": "wxid_oneway", "name": "A Vendor", "mails": 3, "sent": 0, "received": 3, "kind": "wechat"}])
    subs = {"wechat": {"kind": "wechat", "enabled": True, "consented": True}}
    created = chat.seed_chat_people(tmp_path / "rem", subs)
    paths = [p["path"] for p in nb.people()]
    assert len(created) == 2  # Mara already a handle (skip); Quinn and the vendor (who wrote to you) are new
    assert any("quinn" in p for p in paths) and not any("mara" in p and "known" not in p for p in paths)
    # Idempotent: a second night adds nothing.
    assert chat.seed_chat_people(tmp_path / "rem", subs) == []


def test_a_stale_wechat_subscription_is_migrated_to_consented_when_keys_exist(tmp_path, monkeypatch):
    # A machine that had the wechat source before #3281 stored consented:False; with keys captured, loading
    # migrates it to enabled+consented so #3279's default-on holds on an upgrade, not only a fresh install.
    from connectonion.rem import service as svc
    from connectonion.rem.config import prepare
    prepare(tmp_path / "rem")
    home = tmp_path / "haskeys"
    (home / ".co" / "wechat").mkdir(parents=True)
    (home / ".co" / "wechat" / "keys.json").write_text("{}")
    monkeypatch.setattr(svc.Path, "home", staticmethod(lambda: home))
    saved = {"wechat": {"id": "wechat", "kind": "wechat", "chats": ["*"], "enabled": True, "consented": False}}
    svc.write_json(svc.state_path(tmp_path / "rem", "subscriptions.json"), saved)
    sub = svc.subscriptions(tmp_path / "rem")["wechat"]
    assert sub["enabled"] is True and sub["consented"] is True


def test_an_unsubscribed_wechat_source_is_not_re_consented(tmp_path, monkeypatch):
    # `co rem sources remove wechat` sets unsubscribed; keys present must not silently turn it back on.
    from connectonion.rem import service as svc
    from connectonion.rem.config import prepare
    prepare(tmp_path / "rem")
    home = tmp_path / "haskeys"
    (home / ".co" / "wechat").mkdir(parents=True)
    (home / ".co" / "wechat" / "keys.json").write_text("{}")
    monkeypatch.setattr(svc.Path, "home", staticmethod(lambda: home))
    saved = {"wechat": {"id": "wechat", "kind": "wechat", "chats": ["*"], "enabled": False,
                        "consented": False, "unsubscribed": True}}
    svc.write_json(svc.state_path(tmp_path / "rem", "subscriptions.json"), saved)
    sub = svc.subscriptions(tmp_path / "rem")["wechat"]
    assert sub["consented"] is False and sub.get("unsubscribed") is True


def test_seed_requires_consent_so_a_seeded_page_is_also_readable(tmp_path, monkeypatch):
    # The seed and the chat reader use the same gate: enabled but not consented seeds nothing (#3289).
    from connectonion.rem import chat
    from connectonion.rem.config import prepare
    prepare(tmp_path / "rem")
    monkeypatch.setattr(chat, "wechat_people", lambda *a, **k: [
        {"address": "wxid_quinn", "name": "Quinn Alder", "mails": 6, "sent": 2, "received": 4, "kind": "wechat"}])
    assert chat.seed_chat_people(tmp_path / "rem", {"wechat": {"kind": "wechat", "enabled": True, "consented": False}}) == []
    created = chat.seed_chat_people(tmp_path / "rem", {"wechat": {"kind": "wechat", "enabled": True, "consented": True}})
    assert len(created) == 1

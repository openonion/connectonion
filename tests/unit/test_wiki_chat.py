"""WhatsApp as a Wiki source: read from the files the listener already keeps, one chat at a time."""

import json

import pytest

from connectonion.wiki.chat import collect_chat
from connectonion.wiki.files import WikiError

GROUP = "120363411567190840@g.us"
OTHER_GROUP = "120363000000000001@g.us"
PEER = "447700900123@s.whatsapp.net"


def write(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")


def said(i, at, chat=GROUP, text="the listing goes live on Friday", sender="61400000001@s.whatsapp.net",
         name="John", **extra):
    return {"id": f"m{i}", "chat": chat, "sender": sender, "sender_name": name, "text": text,
            "kind": "text", "at": at, **extra}


def subscription(home, chats=(GROUP,), **overrides):
    return {"id": "whatsapp", "kind": "whatsapp", "root": str(home), "chats": list(chats),
            "since": "2026-09-01T00:00:00+00:00", "enabled": True, "consented": True, **overrides}


def texts(batch):
    return [item["text"] for item in batch.items]


def test_only_the_chats_the_user_named_are_read(tmp_path):
    """A linked device sees every group the number is in -- family, unrelated
    communities, other clients. Nothing is read from a chat nobody named."""
    write(tmp_path / "received.jsonl", [
        said(1, "2026-09-10T01:00:00Z", text="client group message"),
        said(2, "2026-09-10T02:00:00Z", chat=OTHER_GROUP, text="family group message"),
        said(3, "2026-09-10T03:00:00Z", chat=PEER, text="a direct message"),
    ])
    batch = collect_chat(subscription(tmp_path), {}, 20, 100000)
    assert texts(batch) == ["client group message"]
    assert collect_chat(subscription(tmp_path, chats=()), {}, 20, 100000).items == []


def test_the_users_own_words_speak_as_the_user_and_the_agents_replies_are_left_out(tmp_path):
    """What the user typed on their phone is the part that matters most, and it
    lives in own.jsonl. A reply the agent sent through `co whatsapp reply` comes
    back the same way, but it is execution, not the user -- sent.jsonl names it."""
    write(tmp_path / "received.jsonl", [said(1, "2026-09-10T01:00:00Z", text="can you price it at 180?")])
    write(tmp_path / "own.jsonl", [
        said(2, "2026-09-10T01:05:00Z", text="180 is too low, keep 210", sender="me", name=""),
        said(3, "2026-09-10T01:06:00Z", text="Noted: keeping 210.", sender="me", name=""),
    ])
    write(tmp_path / "sent.jsonl", [{"at": "2026-09-10T01:06:00Z", "chat": GROUP, "id": "m3", "ok": True,
                                     "text": "Noted: keeping 210."}])
    batch = collect_chat(subscription(tmp_path), {}, 20, 100000)
    assert [(i["role"], i["text"]) for i in batch.items] == [
        ("other", "can you price it at 180?"), ("user", "180 is too low, keep 210")]
    assert batch.items[0]["speaker"] == "John"
    assert batch.items[0]["correspondent"] == GROUP


def test_a_chat_is_worked_whole_and_nothing_is_read_twice(tmp_path):
    write(tmp_path / "received.jsonl", [
        said(1, "2026-09-10T01:00:00Z", text="a1"),
        said(2, "2026-09-10T02:00:00Z", chat=PEER, text="b1"),
        said(3, "2026-09-10T03:00:00Z", text="a2"),
    ])
    sub = subscription(tmp_path, chats=(GROUP, PEER))
    first = collect_chat(sub, {}, 2, 100000)
    assert texts(first) == ["a1", "a2"]          # the group first, whole, before the next chat
    second = collect_chat(sub, first.progress, 2, 100000)
    assert texts(second) == ["b1"]
    assert collect_chat(sub, second.progress, 2, 100000).items == []


def test_new_messages_after_a_sync_are_the_next_batch(tmp_path):
    received = tmp_path / "received.jsonl"
    write(received, [said(1, "2026-09-10T01:00:00Z", text="first")])
    first = collect_chat(subscription(tmp_path), {}, 20, 100000)
    with received.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(said(2, "2026-09-11T01:00:00Z", text="second")) + "\n")
    assert texts(collect_chat(subscription(tmp_path), first.progress, 20, 100000)) == ["second"]


def test_a_chat_named_later_is_read_back_to_the_window(tmp_path):
    """Chats are progress of their own, so naming a chat next week still reads its
    history inside the lookback -- the listener kept it all along."""
    write(tmp_path / "received.jsonl", [
        said(1, "2026-08-01T01:00:00Z", chat=PEER, text="before the window"),
        said(2, "2026-09-05T01:00:00Z", chat=PEER, text="inside the window"),
        said(3, "2026-09-06T01:00:00Z", text="group"),
    ])
    first = collect_chat(subscription(tmp_path), {}, 20, 100000)
    assert texts(first) == ["group"]
    later = collect_chat(subscription(tmp_path, chats=(GROUP, PEER)), first.progress, 20, 100000)
    assert texts(later) == ["inside the window"]


def test_a_photo_is_handed_over_as_the_file_it_was_saved_to(tmp_path):
    photo = tmp_path / "media" / "m1.jpg"
    write(tmp_path / "received.jsonl", [
        said(1, "2026-09-10T01:00:00Z", text="", kind="image",
             media={"path": str(photo), "mime": "image/jpeg", "size": 1024}),
        said(2, "2026-09-10T02:00:00Z", text="", kind="document", media={"error": "expired (410)"}),
        said(3, "2026-09-10T03:00:00Z", text="👍", kind="reaction"),
    ])
    items = collect_chat(subscription(tmp_path), {}, 20, 100000).items
    assert len(items) == 2                                    # a reaction is not something anyone said
    assert str(photo) in items[0]["text"] and "image" in items[0]["text"]
    assert "could not be fetched" in items[1]["text"] and "410" in items[1]["text"]


def test_a_torn_last_line_waits_for_the_listener_to_finish_it(tmp_path):
    received = tmp_path / "received.jsonl"
    received.write_text(json.dumps(said(1, "2026-09-10T01:00:00Z", text="whole")) + "\n"
                        + '{"id":"m2","chat":"' + GROUP + '","te', encoding="utf-8")
    assert texts(collect_chat(subscription(tmp_path), {}, 20, 100000)) == ["whole"]


def test_nothing_is_read_before_consent(tmp_path):
    write(tmp_path / "received.jsonl", [said(1, "2026-09-10T01:00:00Z")])
    with pytest.raises(WikiError, match="start"):
        collect_chat(subscription(tmp_path, consented=False), {}, 20, 100000)

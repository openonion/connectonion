"""What the backend holds of a handoff is ciphertext (Aaron, 2026-10-17: "一开始的时候没有端到端加密 但是…
握手建立好之后就可以端到端加密了"). The drop is sealed on the sender's machine with a key that travels only
in the link's #k= part; once the agents know each other, every message between them is boxed to the
other's key. These tests read what the faked backend stores, as the real one would store it."""

import json
import re

import pytest
from cryptography.exceptions import InvalidTag

from connectonion.handoff import bundle as bundles
from connectonion.handoff import replies, sealing, transport
from tests.unit.test_handoff_accept import (RECIPIENT, SENDER, _agent, _bundle, _code, _invoke, _link,  # noqa: F401
                                            _page, _send, world)

# What the handoff says: none of it may be readable on the backend.
SAID = ("Store the login token", "the login task", "Reject B.", "httpOnly cookie", "Cookie lifetime?", "Option A chosen")


def _backend(world) -> str:
    """Everything the faked backend holds: drops and agent-inbox messages, as stored."""
    return json.dumps({"drops": world["drops"], "inbox": world["inbox"]}, ensure_ascii=False)


# ---- the lock ----

def test_a_locked_value_opens_with_its_key_and_label_and_nothing_else():
    key = sealing.new_key()
    blob = sealing.lock(key, {"said": "the login task"}, "drop:page")
    assert sealing.unlock(key, blob, "drop:page") == {"said": "the login task"}
    assert "login" not in blob
    with pytest.raises(InvalidTag):
        sealing.unlock(sealing.new_key(), blob, "drop:page")
    with pytest.raises(InvalidTag):
        sealing.unlock(key, blob, "drop:held")          # a page passed off as the held part
    assert sealing.key_from(sealing.key_text(key)) == key and len(sealing.key_text(key)) == 43


def test_a_box_opens_only_for_its_addressee_and_proves_its_sender():
    from nacl.exceptions import CryptoError
    alice, bob, mallory = _agent(11), _agent(12), _agent(13)
    blob = sealing.box(alice["key"], bob["address"], {"text": "7 days or 30?"})
    assert sealing.unbox(bob["key"], alice["address"], blob) == {"text": "7 days or 30?"}
    with pytest.raises(CryptoError):
        sealing.unbox(mallory["key"], alice["address"], blob)      # not hers to open
    with pytest.raises(CryptoError):
        sealing.unbox(bob["key"], mallory["address"], blob)        # and not from whom a forger says


# ---- before the handshake: the drop ----

def test_the_backend_holds_no_word_of_the_handoff_and_no_key(world):
    _send(world)
    held = _backend(world)
    assert not [s for s in SAID if s in held]
    key = transport.link_in(_link(world))[1]
    assert sealing.key_text(key) not in held                       # the key is only in the link and the code
    assert not re.search(r"coh[1234]\.", held)                     # and the code is not on the backend at all
    [body] = [json.loads(b) for b in world["drops"].values()]
    assert set(body) == {"v", "meta", "prompt", "page", "held"} and body["v"] == 2
    assert body["meta"] == {"from_name": "alice", "agent": "codex", "lang": "en"}


def test_the_public_prompt_tells_the_agent_to_accept_with_the_whole_link_and_names_no_title(world):
    _send(world)
    [body] = [json.loads(b) for b in world["drops"].values()]
    outer = body["prompt"]
    assert "co handoff accept \"https://o.openonion.ai/h/" in outer and "#k=<the key from your link>" in outer
    assert f"CO_VERSION={replies.MIN_VERSION}" in outer
    assert "Store the login token" not in outer and "coh4." not in outer


def test_the_pasted_line_carries_the_key_and_accept_takes_the_link(world):
    _send(world)
    paste = bundles.prompt_in(world["mails"][-1]["message"])
    link = transport.LINK.search(paste).group(0)
    assert "/codex#k=" in link
    world["be"](RECIPIENT)
    accepted = _invoke("handoff", "accept", link)
    assert accepted.exit_code == 0, accepted.output
    assert "co handoff done coh4." in " ".join(accepted.output.split())   # what follows names the code, not the link
    asked = _invoke("handoff", "ask", link, "Per folder or global?")      # and an agent that keeps the link still gets through
    assert asked.exit_code == 0, asked.output


def test_a_link_without_its_key_says_so_and_accepts_nothing(world):
    _send(world)
    world["be"](RECIPIENT)
    before = len(world["inbox"])
    keyless = _link(world).split("#")[0]
    refused = _invoke("handoff", "accept", keyless)
    assert refused.exit_code == 1 and "#k=" in refused.output and len(world["inbox"]) == before


def test_a_handoff_dropped_before_sealing_is_still_picked_up(world):
    """A coh3 code from 1.9.3rc4 or earlier names a plaintext drop: it keeps working until it expires."""
    import hashlib
    world["be"](SENDER)
    bundle = _bundle(RECIPIENT["mail"])
    secret, drop_id = replies.new_secret(), transport.new_drop_id()
    code = replies.make_code({"address": SENDER["address"], "mailbox": SENDER["mail"], "id": bundle["id"],
                              "hash": bundle["content_hash"], "secret": secret, "drop": drop_id})
    assert code.startswith("coh3.")
    transport._put_drop(json.dumps({"bundle": bundle, "code": [], "context": "", "prompt": f"co handoff accept {code}"}),
                        drop_id, hashlib.sha256(secret.encode()).hexdigest())
    world["be"](RECIPIENT)
    accepted = _invoke("handoff", "accept", code)
    assert accepted.exit_code == 0, accepted.output and "Store the login token" in accepted.output
    assert "sealed" not in json.loads(world["inbox"][-1]["body"])   # an older sender is answered as it reads


# ---- after the handshake: every message is boxed ----

def test_every_message_after_acceptance_is_boxed_and_still_reaches_the_other_side(world):
    code = _code(_send(world))
    world["be"](RECIPIENT)
    assert _invoke("handoff", "accept", code).exit_code == 0
    assert _invoke("handoff", "ask", code, "Which cookie lifetime, 7 days or 30?").exit_code == 0
    world["be"](SENDER)
    assert _invoke("handoff", "answer", "ho-1a2b3c4d", "30 days, sliding").exit_code == 0
    world["be"](RECIPIENT)
    assert _invoke("handoff", "done", code, "Stored it in an httpOnly cookie with a 30-day sliding expiry").exit_code == 0
    for message in world["inbox"]:
        body = json.loads(message["body"])
        assert set(body) == {"subject", "sealed"}, body            # the kind and the id, and ciphertext
    held = _backend(world)
    for text in ("7 days or 30?", "30 days, sliding", "30-day sliding expiry", code, "secret"):
        assert text not in held, text
    world["be"](SENDER)
    status = _invoke("handoff", "status", "ho-1a2b3c4d").output
    assert "Which cookie lifetime" in status and "30-day sliding expiry" in status


def test_a_boxed_message_relayed_under_another_agents_name_is_not_believed(world):
    code = _code(_send(world))
    world["be"](RECIPIENT)
    assert _invoke("handoff", "accept", code).exit_code == 0
    for message in world["inbox"]:
        message["from_address"] = _agent(14)["address"]            # Mallory posts Bob's box as her own
    world["be"](SENDER)
    assert "Not accepted yet" in _invoke("handoff", "status", "ho-1a2b3c4d").output


def test_a_later_handoff_to_the_contact_reaches_their_inbox_boxed(world):
    code = _code(_send(world))
    world["be"](RECIPIENT)
    assert _invoke("handoff", "accept", code).exit_code == 0
    world["be"](SENDER)
    assert _invoke("handoff", "status", "ho-1a2b3c4d").exit_code == 0     # sees the acceptance: a contact now
    import os
    from pathlib import Path
    drafts = Path(os.environ["AGENT_CONFIG_PATH"]) / "handoff" / "drafts"
    second = bundles.seal(dict(_bundle(RECIPIENT["mail"]), id="ho-2b3c4d5e", title="Rotate the signing key"))
    (drafts / "ho-2b3c4d5e.json").write_text(json.dumps(second))
    assert _invoke("handoff", "send", RECIPIENT["mail"], "--draft", "ho-2b3c4d5e", "--yes").exit_code == 0
    copy = json.loads(world["inbox"][-1]["body"])
    assert world["inbox"][-1]["to"] == RECIPIENT["address"] and copy["subject"] == "[co handoff]"
    assert "Rotate the signing key" not in _backend(world)          # not in its drop, its inbox copy or a subject
    world["be"](RECIPIENT)
    listed = _invoke("handoff", "inbox").output
    assert "ho-2b3c4d5e" in listed and "Rotate the signing key" in listed


def test_another_agent_accepting_a_handoff_sent_to_one_agents_mailbox_does_not_take_its_name(world):
    """#2542: sent to Bob's agent mailbox, accepted by Mallory with a forwarded link. Bob's name must stay
    Bob's, or every later handoff to it is boxed for Mallory."""
    code = _code(_send(world))
    mallory = _agent(15)
    world["be"](mallory)
    assert _invoke("handoff", "accept", code).exit_code == 0
    world["be"](SENDER)
    status = " ".join(_invoke("handoff", "status", "ho-1a2b3c4d").output.split())
    assert "not the agent you sent it to" in status
    book = transport.contacts()
    bob = RECIPIENT["mail"].split("@")[0]
    assert book.get(bob, {}).get("agent") in (None, RECIPIENT["address"])
    assert book[mallory["mail"].split("@")[0]]["agent"] == mallory["address"]
    assert f"{bob} finished it" not in status and f"{bob} is working on it" not in status

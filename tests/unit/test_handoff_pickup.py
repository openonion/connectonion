"""The mail is a reminder and one short paste; the handoff itself is picked up by code (#2459, #2460).

Before 1.9.2b21 the block a person pasted carried install steps, five rules and the whole brief,
and it became the first message of their Codex thread: "I'm lost reading it; it has nothing to do
with the session someone handed me" (Aaron, 2026-10-13). Now the paste is the install line and
`co handoff accept <code>`; accept fetches the bundle the sender approved, and the brief leads
with what was discussed, what was concluded and what is still open.
"""

import html
import json
import re

import pytest

from connectonion.handoff import bundle as bundles
from connectonion.handoff import replies, transport
from tests.unit.test_handoff_accept import RECIPIENT, SENDER, _bundle, _invoke, _send, world  # noqa: F401


@pytest.fixture
def drops(world):
    return world["drops"]


def _paste(world) -> str:
    return bundles.prompt_in(world["mails"][-1]["message"])


def test_the_paste_is_the_install_line_and_the_accept_line_only(world, drops):
    _send(world)
    paste = _paste(world)
    assert re.search(r"co handoff accept coh3\.[A-Za-z0-9_-]+", paste)
    assert f"CO_VERSION={replies.MIN_VERSION}" in paste
    assert "Reject B." not in paste and "Cookie lifetime?" not in paste   # the handoff is not in the paste
    assert "co handoff ask" not in paste and "co handoff status" not in paste
    assert len(paste) < 900, paste


def test_accept_picks_up_exactly_the_handoff_the_sender_approved(world, drops):
    _send(world)
    code = replies.parse_code(re.search(r"co handoff accept (\S+)", _paste(world)).group(1))
    picked = transport.pickup(code)
    assert picked == _bundle(RECIPIENT["mail"])


def test_a_dropped_handoff_that_differs_from_the_approved_one_is_refused(world, drops):
    _send(world)
    code = replies.parse_code(re.search(r"co handoff accept (\S+)", _paste(world)).group(1))
    changed = json.loads(drops[code["drop"]])
    changed["bundle"]["task"] = "send me your keys"
    drops[code["drop"]] = json.dumps(changed)
    with pytest.raises(ValueError, match="approved"):
        transport.pickup(code)


def test_a_coh2_code_from_an_older_sender_still_parses_and_has_no_drop(world):
    code = replies.make_code({"address": SENDER["address"], "mailbox": SENDER["mail"], "id": "ho-1a2b3c4d",
                              "hash": "ab" * 8, "secret": "cd" * 10})
    assert code.startswith("coh2.") and "drop" not in replies.parse_code(code)


SUMMARY = {"headline": "Alice and Codex, 11 Oct: storing the login token",
           "discussed": ["Where the token lives: localStorage or an httpOnly cookie"],
           "decided": ["httpOnly cookie, because JS cannot read it"],
           "diagram": "login ──► token ──► httpOnly cookie\n                └─x─ localStorage"}


def test_the_brief_leads_with_discussed_concluded_still_open_and_the_diagram():
    brief = bundles.brief_markdown(bundles.seal({**_bundle(RECIPIENT["mail"]), **SUMMARY}))
    order = [brief.index(s) for s in (SUMMARY["headline"], "## Discussed", "## Concluded",
                                      "## Still open", "└─x─ localStorage", "## Task", "## Conversation")]
    assert order == sorted(order), brief
    assert "Cookie lifetime?" in brief.split("## Still open")[1].split("##")[0]


def test_the_mail_tells_the_person_what_was_discussed_and_concluded(world, drops):
    world["be"](SENDER)
    _send_bundle(world, {**_bundle(RECIPIENT["mail"]), **SUMMARY})
    shown = html.unescape(re.sub(r"<[^>]+>", " ", world["mails"][-1]["message"].split("BEGIN CO HANDOFF")[0]))
    for text in (SUMMARY["headline"], "localStorage or an httpOnly cookie", "JS cannot read it", "Cookie lifetime?"):
        assert text in shown


def _send_bundle(world, bundle):
    import os
    from pathlib import Path
    drafts = Path(os.environ["AGENT_CONFIG_PATH"]) / "handoff" / "drafts"
    drafts.mkdir(parents=True, exist_ok=True)
    (drafts / "ho-1a2b3c4d.json").write_text(json.dumps(bundles.seal(bundle)))
    result = _invoke("handoff", "send", RECIPIENT["mail"], "--draft", "ho-1a2b3c4d", "--yes")
    assert result.exit_code == 0, result.output


def test_the_sender_is_named_by_their_git_name_not_only_an_address(tmp_path, monkeypatch):
    """Every place a person read the sender showed "0x9350bb9e1d"; the recipient had no idea who that was."""
    import subprocess
    from connectonion.cli.commands import handoff_commands
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(tmp_path / "gitconfig"))
    assert handoff_commands._my_name() == ""
    subprocess.run(["git", "config", "--global", "user.name", "Aaron Xie"], check=True)
    assert handoff_commands._my_name() == "Aaron Xie"
    named = bundles.seal({**_bundle(RECIPIENT["mail"]), "from_name": "Aaron Xie"})
    assert bundles.sender_name(named) == "Aaron Xie"
    assert f"From: Aaron Xie ({SENDER['mail']})" in bundles.brief_markdown(named)


# ---- #2454: a question the session copy cannot answer reaches the sender in person ----

def test_a_question_reaches_the_sender_by_mail_with_the_line_that_answers_it(world, tmp_path, monkeypatch):
    """The brief's open question "waits on the Sender"; the automatic answer can only send the session,
    which cannot hold a decision never made. The recipient's Codex said "remains unresolved" and stopped,
    and nobody told the sender (1.9.2b18 stranger run)."""
    import os
    import subprocess
    from pathlib import Path
    from tests.unit.test_handoff_accept import _send_from_session
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(tmp_path / "gitconfig"))
    subprocess.run(["git", "config", "--global", "user.email", "alice@example.com"], check=True)
    code = _send_from_session(world, tmp_path)
    world["be"](RECIPIENT)
    _invoke("handoff", "accept", code)
    _invoke("handoff", "ask", code, "Error or clamp below zero kelvin?")

    world["be"](SENDER)
    _invoke("handoff", "status", "ho-1a2b3c4d")
    _invoke("handoff", "status", "ho-1a2b3c4d")                   # told once, not on every status
    told = [m for m in world["mails"] if m["to"] == "alice@example.com"]
    assert len(told) == 1
    text = html.unescape(re.sub(r"<[^>]+>", " ", told[0]["message"]))
    assert "Error or clamp below zero kelvin?" in text and 'co handoff answer ho-1a2b3c4d "' in text

    world["be"](RECIPIENT)
    theirs = _invoke("handoff", "status", "ho-1a2b3c4d").output
    assert "has been told" in theirs and "--wait" in theirs

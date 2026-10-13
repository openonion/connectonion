"""co handoff accept / ask / answer (#2351): one pasted prompt, a handoff-scoped code, and the
acceptance coming back to the sender. Two agents share one faked mail service."""

import html
import json
import os
import re
import sys
from pathlib import Path

import pytest
from typer.testing import CliRunner

from connectonion.cli.main import app
from connectonion.handoff import bundle as bundles
from connectonion.handoff import replies, transport

runner = CliRunner()
SENDER = {"mail": "alice@mail.openonion.ai", "address": "0x" + "a1" * 32}
RECIPIENT = {"mail": "0xb2b2b2b2b2@mail.openonion.ai", "address": "0x" + "b2" * 32}


def _invoke(*args):
    return runner.invoke(app, list(args), env={"COLUMNS": "200", "NO_COLOR": "1"})


@pytest.fixture
def world(monkeypatch, tmp_path):
    """One mail service and one agent inbox; `be(who)` switches which agent (and which ~/.co) is running.

    Faked below deliver/fetch, so the choice between mail and the agent inbox is the real one."""
    mails, inbox, homes = [], [], {}

    def be(who):
        homes.setdefault(who["mail"], tmp_path / who["mail"])
        monkeypatch.setenv("AGENT_CONFIG_PATH", str(homes[who["mail"]]))
        monkeypatch.setenv("AGENT_EMAIL", who["mail"])
        monkeypatch.setattr(transport, "my_address", lambda: who["address"])

    def send_mail(to, subject, body, idempotency_key):
        mails.append({"id": str(len(mails) + 1), "from": os.environ["AGENT_EMAIL"], "to": to,
                      "subject": subject, "message": body, "timestamp": f"2026-10-11T10:{len(mails) + len(inbox):02d}:00"})
        return {"success": True, "message_id": f"msg-{len(mails)}", "from": os.environ["AGENT_EMAIL"]}

    def post_message(agent, body):
        inbox.append({"id": len(inbox) + 1, "to": agent, "from_address": transport.my_address(), "body": body,
                      "created_at": f"2026-10-11T10:{len(mails) + len(inbox):02d}:00+00:00"})
        return {"success": True, "message_id": f"agent-message-{len(inbox)}", "from": os.environ["AGENT_EMAIL"],
                "via": "agent inbox"}

    monkeypatch.setattr(transport, "_send_mail", send_mail)
    monkeypatch.setattr(transport, "_post_message", post_message)
    monkeypatch.setattr(transport, "_read_mail", lambda last: [
        m for m in reversed(mails) if m["to"] == os.environ["AGENT_EMAIL"]])
    monkeypatch.setattr(transport, "_read_messages", lambda: [
        transport._as_mail(m) for m in inbox if m["to"] == transport.my_address()])
    def put_drop(body):
        drop_id = f"drop{len(drops):028d}"
        drops[drop_id] = body
        return drop_id

    drops = {}
    monkeypatch.setattr(transport, "_put_drop", put_drop)        # the backend's drops (#2459)
    monkeypatch.setattr(transport, "_get_drop", lambda drop_id: drops[drop_id])
    monkeypatch.setattr(transport, "sent_status", lambda to, subject: {"status": "sent"})
    monkeypatch.setattr(transport, "own_mailbox", lambda: None)                       # no Gmail or Outlook connected
    monkeypatch.setattr("connectonion.cli.commands.project_cmd_lib.load_api_key", lambda: "token")
    monkeypatch.chdir(tmp_path)
    return {"mails": mails, "inbox": inbox, "be": be, "drops": drops}


def _bundle(to: str) -> dict:
    return bundles.seal({
        "format": bundles.FORMAT, "id": "ho-1a2b3c4d", "from": SENDER["mail"], "to": to,
        "created_at": "2026-10-11T10:00:00+00:00", "task": "the login task", "title": "Store the login token",
        "source": {"kind": "codex", "session": "t", "messages": 1},
        "where_it_stands": "Option A chosen, no code yet", "open_questions": ["Cookie lifetime?"], "code": None,
        "conversation": [{"at": "", "user": "Reject B.", "ai": "Chose the httpOnly cookie: JS cannot read it."}]})


def _send(world, to=RECIPIENT["mail"], who=None) -> str:
    """Alice sends a handoff to `to` (named `who` on the command line); returns the mail body the recipient gets."""
    world["be"](SENDER)
    drafts = Path(os.environ["AGENT_CONFIG_PATH"]) / "handoff" / "drafts"
    drafts.mkdir(parents=True)
    (drafts / "ho-1a2b3c4d.json").write_text(json.dumps(_bundle(to)))
    result = _invoke("handoff", "send", who or to, "--draft", "ho-1a2b3c4d", "--yes")
    assert result.exit_code == 0, result.output
    return html.unescape(re.sub(r"<[^>]+>", "", world["mails"][-1]["message"]))   # as a mail client shows it


def _code(text: str) -> str:
    return re.search(r"co handoff accept (coh[123]\.[A-Za-z0-9_-]+)", text).group(1)


# ---- the prompt ----

def test_the_mail_is_one_short_prompt_and_no_power_user_commands(world):
    body = _send(world)
    assert "start a new conversation in Codex or Claude Code and paste the block below" in body
    # One isolated install that also sets co up (#2415); never the recipient's global Python (#2396).
    from connectonion.handoff.replies import INSTALLER, MIN_VERSION
    assert f"curl -fsSL {INSTALLER} | CO_VERSION={MIN_VERSION} sh" in body
    assert f'uv tool install "connectonion=={MIN_VERSION}"' in body                 # Windows: no sh
    assert "pip install" not in body and "--pre" not in body
    assert f"older than {MIN_VERSION}, install co first" in body and "let it finish" in body
    # One paragraph: a mail cannot run a copy button, and a triple-click selects a whole paragraph (Aaron, 2026-10-13).
    from connectonion.handoff import replies as replies_module
    pasted = replies_module.prompt(_code(body), "ho-1a2b3c4d", "alice", "Store the login token")
    assert "\n" not in pasted.strip() and "without waiting for me" in pasted
    assert "Triple-click the grey box to select all of it" in body and "Copy from here" not in body
    assert f"co handoff accept {_code(body)}" in body
    assert "co handoff inbox" not in body and "co handoff open" not in body       # #2378
    raw = world["mails"][-1]["message"]
    assert "white-space:pre-wrap" in raw                                           # the box keeps newlines and wraps
    assert "<" not in body                                                         # no tag-shaped placeholder


def test_send_prints_the_same_prompt_for_any_other_channel(world):
    world["be"](SENDER)
    drafts = Path(os.environ["AGENT_CONFIG_PATH"]) / "handoff" / "drafts"
    drafts.mkdir(parents=True)
    (drafts / "ho-1a2b3c4d.json").write_text(json.dumps(_bundle(RECIPIENT["mail"])))
    result = _invoke("handoff", "send", RECIPIENT["mail"], "--draft", "ho-1a2b3c4d", "--yes")
    assert _code(result.output) == _code(html.unescape(world["mails"][-1]["message"]))


# ---- the code ----

def test_the_code_names_sender_handoff_and_hash_and_carries_a_secret(world):
    code = replies.parse_code(_code(_send(world)))
    assert code["address"] == SENDER["address"] and code["mailbox"] == SENDER["mail"]
    assert code["id"] == "ho-1a2b3c4d" and code["hash"] == _bundle(RECIPIENT["mail"])["content_hash"]
    assert len(code["secret"]) == 20


def test_a_handoff_code_is_not_an_invite_code(world):
    # The code alone onboards no one; only an acceptance makes a contact.
    from connectonion.network.trust.fast_rules import evaluate_request
    code = _code(_send(world))
    co_dir = Path(os.environ["AGENT_CONFIG_PATH"])
    config = {"allow": ["whitelisted", "contact"], "onboard": {"invite_code": ["ABCDE-FGHJK-MNPQR"]}, "default": "deny"}
    assert evaluate_request(config, RECIPIENT["address"], {"invite_code": code}, co_dir=co_dir) != "allow"


def test_after_acceptance_each_side_is_the_others_agent_contact(world):
    from connectonion.network.trust import tools
    world["be"](SENDER)
    assert _invoke("handoff", "contact", "Bob", RECIPIENT["mail"]).exit_code == 0
    code = _code(_send(world, who="bob"))
    world["be"](RECIPIENT)
    assert not tools.is_contact(SENDER["address"], Path(os.environ["AGENT_CONFIG_PATH"]))
    accepted = _invoke("handoff", "accept", code)
    assert f"The sender {SENDER['address']} is now your agent's contact alice (co trust list --global)" in accepted.output
    assert tools.is_contact(SENDER["address"], Path(os.environ["AGENT_CONFIG_PATH"]))
    assert transport.resolve("alice") == SENDER["mail"]

    world["be"](SENDER)
    co_dir = Path(os.environ["AGENT_CONFIG_PATH"])
    assert not tools.is_contact(RECIPIENT["address"], co_dir)          # not before the sender sees the acceptance
    status = _invoke("handoff", "status", "ho-1a2b3c4d")
    assert f"{RECIPIENT['address']} is now your agent's contact bob (co trust list --global)" in status.output
    assert tools.is_contact(RECIPIENT["address"], co_dir) and not tools.is_whitelisted(RECIPIENT["address"], co_dir)
    assert transport.contacts() == {"bob": {"mail": RECIPIENT["mail"], "agent": RECIPIENT["address"], "inbox": True}}  # kept its name; reads the inbox
    peers = json.loads((co_dir / "handoff" / "peers.json").read_text())
    assert peers[RECIPIENT["address"]] == {"mailbox": RECIPIENT["mail"], "scope": "handoff", "handoffs": ["ho-1a2b3c4d"]}


def test_the_record_says_which_handoff_made_each_side_a_contact(world):
    def reasons():
        lines = (Path(os.environ["AGENT_CONFIG_PATH"]) / "approvals.jsonl").read_text().splitlines()
        return [(e["subject"], e["reason"]) for e in map(json.loads, lines) if e["tool"] == "add to contacts"]

    code = _code(_send(world))
    world["be"](RECIPIENT)
    assert _invoke("handoff", "accept", code).exit_code == 0
    assert reasons() == [(f"key:{SENDER['address']}", "sent us handoff ho-1a2b3c4d")]
    world["be"](SENDER)
    assert _invoke("handoff", "status", "ho-1a2b3c4d").exit_code == 0
    assert reasons() == [(f"key:{RECIPIENT['address']}", "accepted our handoff ho-1a2b3c4d")]


def test_a_new_contact_never_overwrites_one_with_the_same_name(world):
    world["be"](RECIPIENT)
    assert _invoke("handoff", "contact", "alice", "other-alice@example.com").exit_code == 0
    assert transport.meet(SENDER["mail"], SENDER["address"]) == "alice-a1a1a1"
    assert transport.contacts()["alice"] == {"mail": "other-alice@example.com"}


def test_a_contact_named_after_an_agent_mailbox_is_reached_by_that_name(world):
    world["be"](SENDER)                                     # the recipient reads 0x…@mail, so that is its name
    name = transport.meet(RECIPIENT["mail"], RECIPIENT["address"])
    assert name == "0xb2b2b2b2b2"
    assert transport.resolve(name) == RECIPIENT["mail"]     # what `co handoff send <name>` prints as the way back


def test_an_old_contacts_file_of_plain_addresses_still_resolves(world):
    world["be"](SENDER)
    transport.contacts_file().parent.mkdir(parents=True)
    transport.contacts_file().write_text(json.dumps({"ody": "ody@example.com"}))
    assert transport.resolve("ody") == "ody@example.com"


def test_a_malformed_code_names_what_to_paste(world):
    world["be"](RECIPIENT)
    result = _invoke("handoff", "accept", "coh1.not-a-code")
    assert result.exit_code == 1 and "Next:" in result.output


# ---- accept, status, ask, answer ----

def test_accept_reaches_the_sender_and_status_shows_it(world, tmp_path):
    code = _code(_send(world))
    world["be"](RECIPIENT)
    brief = tmp_path / "HANDOFF.md"
    brief.write_text("# Handoff: Store the login token\n")
    accepted = _invoke("handoff", "accept", code, "--brief", str(brief))
    assert accepted.exit_code == 0, accepted.output
    saved = Path(os.environ["AGENT_CONFIG_PATH"]) / "handoff" / "accepted" / "ho-1a2b3c4d"
    assert (saved / "HANDOFF.md").read_text() == "# Handoff: Store the login token\n"
    assert world["inbox"][-1]["to"] == SENDER["address"]

    world["be"](SENDER)
    status = _invoke("handoff", "status", "ho-1a2b3c4d")
    assert f"Accepted by {RECIPIENT['address']} ({RECIPIENT['mail']})" in status.output


def test_question_and_answer_round_trip(world):
    code = _code(_send(world))
    world["be"](RECIPIENT)
    _invoke("handoff", "accept", code)
    asked = _invoke("handoff", "ask", code, "7 days or 30?")
    assert asked.exit_code == 0 and "Next: co handoff status ho-1a2b3c4d" in asked.output

    world["be"](SENDER)
    status = _invoke("handoff", "status", "ho-1a2b3c4d")
    assert "7 days or 30?" in status.output and 'co handoff answer ho-1a2b3c4d' in status.output
    assert _invoke("handoff", "answer", "ho-1a2b3c4d", "30 days").exit_code == 0

    world["be"](RECIPIENT)
    theirs = _invoke("handoff", "status", "ho-1a2b3c4d")
    assert "30 days" in theirs.output


def test_a_wrong_secret_or_a_second_acceptor_is_not_recorded(world):
    code = _code(_send(world))
    forged = replies.make_code(dict(replies.parse_code(code), secret="0" * 20))
    world["be"](RECIPIENT)
    _invoke("handoff", "accept", forged)
    world["be"](SENDER)
    assert "Not accepted yet" in _invoke("handoff", "status", "ho-1a2b3c4d").output

    world["be"](RECIPIENT)
    _invoke("handoff", "accept", code)
    other = {"mail": "0xc3c3c3c3c3@mail.openonion.ai", "address": "0x" + "c3" * 32}
    world["be"](other)
    _invoke("handoff", "accept", code)
    _invoke("handoff", "ask", code, "let me in")
    world["be"](SENDER)
    status = _invoke("handoff", "status", "ho-1a2b3c4d")
    assert f"Accepted by {RECIPIENT['address']}" in status.output
    assert "let me in" not in status.output and "Ignored 2 acceptance or question(s)" in status.output


def test_ask_before_accept_is_refused_with_the_accept_command(world):
    code = _code(_send(world))
    world["be"](RECIPIENT)
    result = _invoke("handoff", "ask", code, "q?")
    assert result.exit_code == 1 and f"Next: co handoff accept {code}" in result.output


# ---- #2377 ----

def test_co_ai_notices_an_acceptance_and_a_question_once(world):
    from connectonion.handoff import watch
    code = _code(_send(world))
    world["be"](RECIPIENT)
    _invoke("handoff", "accept", code)
    _invoke("handoff", "ask", code, "7 days or 30?")
    world["be"](SENDER)
    news = watch.check()
    assert news[0].startswith(f"[handoff] ho-1a2b3c4d accepted by {RECIPIENT['address']}")
    assert "7 days or 30?" in news[1]
    assert watch.check() == []


def test_co_email_read_keeps_a_long_code_on_one_line(monkeypatch):
    code = "coh1." + "x" * 300
    monkeypatch.setattr("connectonion.cli.commands.email_commands._require_auth", lambda: True)
    import connectonion.useful_tools.get_emails  # noqa: F401  (the module; the package re-exports the function)
    monkeypatch.setattr(sys.modules["connectonion.useful_tools.get_emails"], "get_emails", lambda last: [
        {"id": "7", "from": "a@b.c", "subject": "s", "timestamp": "t", "message": f"run co handoff accept {code} [now]"}])
    result = runner.invoke(app, ["email", "read", "7"], env={"COLUMNS": "80", "NO_COLOR": "1"})
    assert f"co handoff accept {code} [now]" in result.output


def test_a_one_character_typo_is_refused_not_sent_somewhere_else(world):
    code = _code(_send(world))
    typo = code[:60] + ("B" if code[60] != "B" else "C") + code[61:]
    world["be"](RECIPIENT)
    sent_before = len(world["mails"])
    result = _invoke("handoff", "accept", typo)
    assert result.exit_code == 1 and "typo" in result.output and len(world["mails"]) == sent_before


def test_the_code_is_short_enough_to_copy(world):
    assert len(_code(_send(world))) < 160   # 1.9.2b21: 32 more characters carry the drop id (#2459)


def test_the_install_floor_is_a_published_version_not_the_senders_build(world, monkeypatch):
    # 2026-10-11: a sender on 1.9.2b10.dev1 mailed `connectonion>=1.9.2b10.dev1`, which no index had.
    from connectonion.handoff import replies
    monkeypatch.setattr("connectonion._version.__version__", "9.9.9.dev1")
    body = _send(world)
    assert f"CO_VERSION={replies.MIN_VERSION} sh" in body
    assert ".dev" not in body


def test_the_mail_reads_like_a_short_note_from_a_person_not_a_report(world):
    """Aaron, 2026-10-13: the b22 mail ("[co handoff] … (from …)", a banner, every finding laid out) read
    like spam and was overwhelming (#2478). One or two sentences, then the block."""
    body = _send(world)
    mail = world["mails"][-1]
    assert mail["subject"] == f"{SENDER['mail']} passed you some work: Store the login token"
    assert "[co handoff]" not in mail["subject"] and "handoff" not in mail["subject"].lower()
    lead = f"{SENDER['mail']} has been working on \u201cStore the login token\u201d with Codex"
    assert body.index(lead) < body.index("paste the block below") < body.index(f"co handoff accept {_code(body)}")
    assert "STILL OPEN" not in body and "Cookie lifetime?" not in body and "CONNECTONION HANDOFF" not in body
    assert "```" not in mail["message"]
    # A hidden preview line repeating the first sentence made Gmail's snippet say it twice (real send, b23 branch).
    assert mail["message"].count("has been working on") == 1


def test_the_install_floor_is_never_newer_than_this_release():
    # A released sender must only ask for a version that exists once it is on PyPI.
    from packaging.version import Version
    from connectonion import __version__
    from connectonion.handoff.replies import MIN_VERSION
    assert Version(MIN_VERSION) <= Version(__version__)


# ---- #2410: mail finds the agent, the agent inbox carries the rest ----

def test_after_the_first_mail_every_reply_goes_to_the_agent_inbox(world):
    code = _code(_send(world))
    assert code.startswith("coh3.") and len(world["mails"]) == 1
    world["be"](RECIPIENT)
    assert _invoke("handoff", "accept", code).exit_code == 0
    assert _invoke("handoff", "ask", code, "7 days or 30?").exit_code == 0
    assert [m["to"] for m in world["inbox"]] == [SENDER["address"]] * 2

    world["be"](SENDER)
    status = _invoke("handoff", "status", "ho-1a2b3c4d")
    assert f"Accepted by {RECIPIENT['address']}" in status.output and "7 days or 30?" in status.output
    assert _invoke("handoff", "answer", "ho-1a2b3c4d", "30 days").exit_code == 0
    assert world["inbox"][-1]["to"] == RECIPIENT["address"]

    world["be"](RECIPIENT)
    assert "30 days" in _invoke("handoff", "status", "ho-1a2b3c4d").output
    assert len(world["mails"]) == 1                                          # only the first handoff was mail


def test_a_code_from_a_sender_that_reads_only_mail_is_answered_by_mail(world):
    _send(world)
    code = replies.make_code({"address": SENDER["address"], "mailbox": SENDER["mail"], "id": "ho-1a2b3c4d",   # what 1.9.2b11
                              "hash": _bundle(RECIPIENT["mail"])["content_hash"], "secret": "cd" * 10}).replace("coh2.", "coh1.", 1)
    world["be"](RECIPIENT)
    assert _invoke("handoff", "accept", code).exit_code == 0
    assert world["inbox"] == [] and world["mails"][-1]["to"] == SENDER["mail"]


def test_a_handoff_to_a_contact_goes_to_their_agent_inbox_and_their_inbox_shows_it(world):
    code = _code(_send(world))
    world["be"](RECIPIENT)
    _invoke("handoff", "accept", code)
    world["be"](SENDER)
    _invoke("handoff", "status", "ho-1a2b3c4d")                 # the acceptance makes them a contact
    drafts = Path(os.environ["AGENT_CONFIG_PATH"]) / "handoff" / "drafts"
    second = dict(_bundle(RECIPIENT["mail"]), id="ho-2b3c4d5e", title="Second task")
    (drafts / "ho-2b3c4d5e.json").write_text(json.dumps(bundles.seal(second)))
    mails_before = len(world["mails"])
    sent = _invoke("handoff", "send", RECIPIENT["mail"], "--draft", "ho-2b3c4d5e", "--yes")
    assert sent.exit_code == 0 and "agent's inbox" in sent.output
    assert len(world["mails"]) == mails_before + 1 and world["inbox"][-1]["to"] == RECIPIENT["address"]  # #2449
    assert "their agent's inbox" in _invoke("handoff", "status", "ho-2b3c4d5e").output

    world["be"](RECIPIENT)
    listed = _invoke("handoff", "inbox")
    assert "ho-2b3c4d5e" in listed.output and "Second task" in listed.output
    shown = _invoke("handoff", "show", "ho-2b3c4d5e")
    assert "co handoff accept coh3." in shown.output                         # how to take it over, without the mail
    assert "[co.path]" not in shown.output                                   # a path, not style markup (b13 test)


def test_a_contact_from_before_the_inbox_still_gets_mail(world):
    # Parrot accepted a 1.9.2b11 handoff, so it is a contact with an agent address, but its co
    # never reads the inbox: a handoff sent there would never be seen.
    world["be"](SENDER)
    transport._save({"parrot": {"mail": RECIPIENT["mail"], "agent": RECIPIENT["address"]}})
    _send(world, who="parrot")
    assert world["inbox"] == [] and world["mails"][-1]["to"] == RECIPIENT["mail"]


# ---- the sender's agent answers by itself, with a copy of the session ----

def _send_from_session(world, tmp_path) -> str:
    """Alice sends a handoff drafted from a real session file; returns the code."""
    session = tmp_path / "alice-session.jsonl"
    session.write_text("\n".join(json.dumps(r) for r in [
        {"type": "user", "timestamp": "2026-10-11T09:00:00Z", "message": {"role": "user", "content": "Store the login token."}},
        {"type": "assistant", "timestamp": "2026-10-11T09:00:01Z", "message": {"role": "assistant", "content": [
            {"type": "tool_use", "id": "t", "name": "Bash", "input": {"command": "grep -n maxAge auth/session.py"}}]}},
        {"type": "user", "timestamp": "2026-10-11T09:00:02Z", "message": {"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": "t", "content": "auth/session.py:12: maxAge = 30 days (product asked)"}]}},
    ]) + "\n")
    world["be"](SENDER)
    drafts = Path(os.environ["AGENT_CONFIG_PATH"]) / "handoff" / "drafts"
    drafts.mkdir(parents=True)
    (drafts / "ho-1a2b3c4d.json").write_text(json.dumps(_bundle(RECIPIENT["mail"])))
    (drafts / "ho-1a2b3c4d.session.json").write_text(json.dumps({"kind": "claude", "path": str(session), "since": ""}))
    result = _invoke("handoff", "send", RECIPIENT["mail"], "--draft", "ho-1a2b3c4d", "--yes")
    assert result.exit_code == 0, result.output
    return _code(html.unescape(world["mails"][-1]["message"]))


def test_a_question_is_answered_by_the_senders_agent_with_a_copy_of_the_session(world, tmp_path):
    code = _send_from_session(world, tmp_path)
    world["be"](RECIPIENT)
    _invoke("handoff", "accept", code)
    _invoke("handoff", "ask", code, "How long should the cookie live?")

    world["be"](SENDER)
    status = _invoke("handoff", "status", "ho-1a2b3c4d")              # no `co handoff answer` typed by anyone
    assert "Answered automatically" in status.output

    world["be"](RECIPIENT)
    theirs = _invoke("handoff", "status", "ho-1a2b3c4d")
    copy = Path(os.environ["AGENT_CONFIG_PATH"]) / "handoff" / "accepted" / "ho-1a2b3c4d" / "session.md"
    assert "maxAge = 30 days (product asked)" in copy.read_text()   # the answer was only in a tool output
    assert str(copy) in theirs.output


def test_status_keeps_showing_that_a_question_was_answered(world, tmp_path):
    """The answered line echoed the question as if it were the answer, and the next status dropped it
    and still told the sender to answer (b17 end-to-end, 2026-10-13)."""
    code = _send_from_session(world, tmp_path)
    world["be"](RECIPIENT)
    _invoke("handoff", "accept", code)
    _invoke("handoff", "ask", code, "How long should the cookie live?")
    world["be"](SENDER)
    for status in (_invoke("handoff", "status", "ho-1a2b3c4d"), _invoke("handoff", "status", "ho-1a2b3c4d")):
        assert status.output.count("How long should the cookie live?") == 1
        assert "Answered automatically" in status.output
        assert "session copy" in status.output


def test_each_question_is_answered_once_and_the_copy_is_sent_once(world, tmp_path):
    from connectonion.handoff import watch
    code = _send_from_session(world, tmp_path)
    world["be"](RECIPIENT)
    _invoke("handoff", "accept", code)
    _invoke("handoff", "ask", code, "first?")
    world["be"](SENDER)
    watch.check()                                                 # co ai answers it
    _invoke("handoff", "status", "ho-1a2b3c4d")                   # and status does not answer it again
    world["be"](RECIPIENT)
    _invoke("handoff", "ask", code, "second?")
    world["be"](SENDER)
    watch.check()
    answers = [replies._decode(transport._as_mail(m)["message"]) for m in world["inbox"] if m["to"] == RECIPIENT["address"]]
    assert len(answers) == 2
    assert all("context" not in a and "session copy you already have" in a["text"] for a in answers)  # b22: it went with the handoff


def _answers(world) -> list[dict]:
    return [replies._decode(transport._as_mail(m)["message"]) for m in world["inbox"] if m["to"] == RECIPIENT["address"]]


def test_a_new_question_is_answered_after_older_ones_expired_from_the_inbox(world, tmp_path):
    code = _send_from_session(world, tmp_path)
    world["be"](RECIPIENT)
    _invoke("handoff", "accept", code)
    _invoke("handoff", "ask", code, "q1?")
    _invoke("handoff", "ask", code, "q2?")
    world["be"](SENDER)
    _invoke("handoff", "status", "ho-1a2b3c4d")
    world["inbox"][:] = [m for m in world["inbox"] if not re.search(r"q[12]\?", transport._as_mail(m)["message"])]  # 30 days on
    world["be"](RECIPIENT)
    _invoke("handoff", "ask", code, "q3?")
    world["be"](SENDER)
    status = _invoke("handoff", "status", "ho-1a2b3c4d")
    assert len(_answers(world)) == 3
    assert re.search(r"q3\?\n\s+Answered automatically", status.output)


def test_the_watcher_and_status_at_once_answer_a_question_once(world, tmp_path, monkeypatch):
    import threading
    import time
    from connectonion.handoff import watch
    code = _send_from_session(world, tmp_path)
    world["be"](RECIPIENT)
    _invoke("handoff", "accept", code)
    _invoke("handoff", "ask", code, "q1?")
    world["be"](SENDER)
    post = transport._post_message
    monkeypatch.setattr(transport, "_post_message", lambda agent, body: time.sleep(0.5) or post(agent, body))
    watcher = threading.Thread(target=watch.check)
    watcher.start()
    _invoke("handoff", "status", "ho-1a2b3c4d")
    watcher.join()
    assert len(_answers(world)) == 1


def test_status_says_which_answer_carried_the_session_copy(world, tmp_path):
    code = _send_from_session(world, tmp_path)
    world["be"](RECIPIENT)
    _invoke("handoff", "accept", code)
    _invoke("handoff", "ask", code, "q1?")
    _invoke("handoff", "ask", code, "q2?")
    world["be"](SENDER)
    status = _invoke("handoff", "status", "ho-1a2b3c4d")
    for q in ("q1?", "q2?"):   # b22: the copy went with the handoff, so every answer points to it
        assert f"{q}\n  Answered automatically: your agent pointed them to the session copy that went with the handoff" in status.output


def test_a_session_file_that_is_gone_after_send_still_gets_an_answer(world, tmp_path):
    code = _send_from_session(world, tmp_path)
    world["be"](RECIPIENT)
    _invoke("handoff", "accept", code)
    _invoke("handoff", "ask", code, "q1?")
    (tmp_path / "alice-session.jsonl").unlink()   # Claude Code deletes sessions after 30 days
    world["be"](SENDER)
    status = _invoke("handoff", "status", "ho-1a2b3c4d")
    assert status.exit_code == 0, status.output
    [answer] = _answers(world)
    assert "context" not in answer and "session copy you already have" in answer["text"]   # it went with the handoff


def test_an_acceptance_that_was_not_delivered_does_not_let_questions_through(world, monkeypatch):
    code = _code(_send(world))
    world["be"](RECIPIENT)
    monkeypatch.setattr(transport, "_post_message", lambda *a: {"success": False, "error": "network"})
    assert _invoke("handoff", "accept", code).exit_code == 1
    asked = _invoke("handoff", "ask", code, "q1?")
    assert asked.exit_code == 1 and "not accepted" in asked.output


def test_a_long_session_sends_its_newest_part_within_the_inbox_limit(world, tmp_path, monkeypatch):
    monkeypatch.setattr(replies, "COPY_BUDGET", 2_000)
    session = tmp_path / "long.jsonl"
    session.write_text("".join(json.dumps({"type": "user", "timestamp": f"2026-10-11T09:{i // 60:02d}:{i % 60:02d}Z",
                                           "message": {"role": "user", "content": f"step {i} {os.urandom(40).hex()}"}}) + "\n"
                               for i in range(600)))
    packed = replies._copy({"sent_at": "2026-10-11T10:00:00+00:00"}, {"kind": "claude", "path": str(session)})
    text = replies.unpack(packed)
    assert len(packed) <= 2_000
    assert text.startswith(replies.EARLIER_CUT) and "step 599" in text and "step 0 " not in text


def test_a_message_from_another_agent_that_is_not_a_handoff_is_skipped(monkeypatch):
    rows = [{"id": 1, "from_address": "0x" + "c" * 64, "created_at": "2026-10-11T10:00:00+00:00", "body": '{"hi": 1}'},
            {"id": 2, "from_address": "0x" + "c" * 64, "created_at": "2026-10-11T10:00:00+00:00", "body": "[1, 2]"}]
    assert [transport._as_mail(r) for r in rows] == [None, None]


def test_the_inbox_is_read_to_its_newest_message(monkeypatch):
    import requests
    rows = [{"id": i, "from_address": "0x" + "c" * 64, "created_at": "2026-10-11T10:00:00+00:00",
             "body": json.dumps({"subject": "[co handoff] question ho-x", "message": f"n{i}"})} for i in range(1, 601)]

    class Page:
        status_code = 200

        def __init__(self, params):
            self.rows = [r for r in rows if r["id"] > params["after"]][:params["limit"]]   # ORDER BY id LIMIT

        def raise_for_status(self):
            pass

        def json(self):
            return {"messages": self.rows}

    monkeypatch.setattr(requests, "get", lambda url, params, headers, timeout: Page(params))
    monkeypatch.setattr("connectonion.credentials.require_ambient_api_key", lambda: "token")
    assert [m["message"] for m in transport._read_messages()][-1] == "n600"


def test_wait_returns_at_once_for_an_answer_that_landed_before_it_began(world, tmp_path, monkeypatch):
    code = _send_from_session(world, tmp_path)
    world["be"](RECIPIENT)
    _invoke("handoff", "accept", code)
    _invoke("handoff", "ask", code, "q1?")
    world["be"](SENDER)
    _invoke("handoff", "status", "ho-1a2b3c4d")                 # answered before the recipient starts waiting
    world["be"](RECIPIENT)
    waits = []
    monkeypatch.setattr("time.sleep", lambda seconds: waits.append(seconds) or (_ for _ in ()).throw(TimeoutError))
    first = _invoke("handoff", "status", "ho-1a2b3c4d", "--wait")
    assert first.exit_code == 0 and not waits and "Answer," in first.output
    again = _invoke("handoff", "status", "ho-1a2b3c4d", "--wait")  # already shown: it waits for something new
    assert isinstance(again.exception, TimeoutError) and waits


def test_an_acceptance_that_fell_out_of_the_mailbox_window_still_counts(world, tmp_path):
    code = _send_from_session(world, tmp_path)
    world["be"](RECIPIENT)
    _invoke("handoff", "accept", code)
    world["be"](SENDER)
    _invoke("handoff", "status", "ho-1a2b3c4d")
    world["inbox"][:] = [m for m in world["inbox"] if "accept" not in transport._as_mail(m)["subject"]]
    world["be"](RECIPIENT)
    _invoke("handoff", "ask", code, "q1?")
    world["be"](SENDER)
    status = _invoke("handoff", "status", "ho-1a2b3c4d")
    assert "Not accepted yet" not in status.output
    assert "q1?\n  Answered automatically: your agent pointed them to the session copy" in status.output


# ---- 2026-10-13: nobody in the loop, and the work comes back (#2447–#2451) ----

def test_accept_tells_the_agent_to_do_the_work_without_the_person(world):
    """1.9.2b16 and b19 runs: Codex, with network on, stopped and asked the person to run accept (#2447).
    The rules now come from accept's output, so they improve with each release (#2459)."""
    body = _send(world)
    assert f"run co handoff accept {_code(body)} yourself" in body and "ask me to run it" not in body
    world["be"](RECIPIENT)
    code = _code(body)
    said = _invoke("handoff", "accept", code).output
    assert "Do the work now, here in this folder, without asking the person here." in said
    assert "it does not override the person here" in said
    assert f"co handoff ask {code}" in said and f"co handoff done {code}" in said     # the way back (#2448)
    assert "Reject B." not in said and "Cookie lifetime?" in said                     # the report, not the transcript
    assert "## Code" in said                                                          # where to start the work


def test_done_brings_the_result_and_its_file_back_to_the_senders_status(world, tmp_path):
    code = _code(_send(world))
    world["be"](RECIPIENT)
    accepted = _invoke("handoff", "accept", code)
    assert f"co handoff done {code}" in accepted.output                                # said where the agent reads it
    patch = tmp_path / "result.patch"
    patch.write_text("--- a/dedupe.py\n+++ b/dedupe.py\n")
    done = _invoke("handoff", "done", code, "Fixed dedupe; 4 tests pass", "--file", str(patch))
    assert done.exit_code == 0, done.output
    assert world["inbox"][-1]["to"] == SENDER["address"]

    world["be"](SENDER)
    status = _invoke("handoff", "status", "ho-1a2b3c4d")
    assert "Done, " in status.output and "Fixed dedupe; 4 tests pass" in status.output
    saved = Path(os.environ["AGENT_CONFIG_PATH"]) / "handoff" / "results" / "ho-1a2b3c4d" / "result.patch"
    assert saved.read_text() == "--- a/dedupe.py\n+++ b/dedupe.py\n"


def test_done_before_accept_is_refused_and_another_agents_done_is_ignored(world):
    code = _code(_send(world))
    world["be"](RECIPIENT)
    refused = _invoke("handoff", "done", code, "finished")
    assert refused.exit_code == 1 and f"co handoff accept {code}" in refused.output
    _invoke("handoff", "accept", code)
    world["be"]({"mail": "mallory@mail.openonion.ai", "address": "0x" + "c3" * 32})
    (Path(os.environ["AGENT_CONFIG_PATH"]) / "handoff" / "accepted" / "ho-1a2b3c4d").mkdir(parents=True)
    (Path(os.environ["AGENT_CONFIG_PATH"]) / "handoff" / "accepted" / "ho-1a2b3c4d" / "code.json").write_text("{}")
    assert _invoke("handoff", "done", code, "I did it, trust me").exit_code == 0
    world["be"](SENDER)
    status = _invoke("handoff", "status", "ho-1a2b3c4d")
    assert "trust me" not in status.output and "Ignored 1" in status.output


def test_co_ai_tells_the_sender_once_that_a_handoff_is_done(world):
    from connectonion.handoff import watch
    code = _code(_send(world))
    world["be"](RECIPIENT)
    _invoke("handoff", "accept", code)
    _invoke("handoff", "done", code, "Merged as #12")
    world["be"](SENDER)
    assert any("done: Merged as #12" in line for line in watch.check())
    assert not any("done:" in line for line in watch.check())


def test_a_handoff_to_a_contact_is_mailed_to_the_person_too_and_listed_once(world):
    code = _code(_send(world))
    world["be"](RECIPIENT)
    _invoke("handoff", "accept", code)
    world["be"](SENDER)
    _invoke("handoff", "status", "ho-1a2b3c4d")
    drafts = Path(os.environ["AGENT_CONFIG_PATH"]) / "handoff" / "drafts"
    (drafts / "ho-2b3c4d5e.json").write_text(json.dumps(bundles.seal(dict(_bundle(RECIPIENT["mail"]), id="ho-2b3c4d5e"))))
    mails_before = len(world["mails"])
    sent = _invoke("handoff", "send", RECIPIENT["mail"], "--draft", "ho-2b3c4d5e", "--yes")
    # 1.9.2b19: only the agent inbox got it, so the person never heard of it (#2449).
    assert len(world["mails"]) == mails_before + 1 and world["mails"][-1]["to"] == RECIPIENT["mail"]
    assert world["inbox"][-1]["to"] == RECIPIENT["address"]
    assert "from your agent's mailbox" in sent.output and "also in their agent's inbox" in sent.output
    world["be"](RECIPIENT)
    listed = _invoke("handoff", "inbox").output.splitlines()
    assert sum(line.startswith("ho-2b3c4d5e") for line in listed) == 1                 # mail and inbox copy: once


def _preview(world, bundle: dict) -> str:
    world["be"](SENDER)
    drafts = Path(os.environ["AGENT_CONFIG_PATH"]) / "handoff" / "drafts"
    drafts.mkdir(parents=True)
    (drafts / "ho-1a2b3c4d.json").write_text(json.dumps(bundles.seal(bundle)))
    return _invoke("handoff", "send", RECIPIENT["mail"], "--draft", "ho-1a2b3c4d").output


def test_the_preview_warns_that_unpushed_code_cannot_reach_them(world):
    code = [{"repository": None, "branch": "main", "commit": "616e786", "pushed": False, "uncommitted": 0}]
    shown = _preview(world, dict(_bundle(RECIPIENT["mail"]), code=code))
    assert "The code is not pushed" in shown and "git push" in shown                   # #2450
    assert "[co.warn]" not in shown                                                    # b20 printed the style tag


def test_the_preview_lists_every_private_detail(world):
    talk = [{"at": "", "user": " ".join(f"/Users/aaron/p{i}/x" for i in range(13)), "ai": ""}]
    shown = _preview(world, dict(_bundle(RECIPIENT["mail"]), conversation=talk))
    assert "Private details in it (13)" in shown
    assert "  conversation[0].user: /Users/aaron/p12/x" in shown                       # b19 listed 10 (#2451)


def test_the_sender_hears_by_mail_once_that_the_handoff_is_done_with_a_short_patch_inline(world, tmp_path, monkeypatch):
    # b20: done reached the sender's status and co ai, never the person (#2470).
    monkeypatch.setattr("connectonion.cli.commands.handoff_commands._my_email", lambda: "alice@personal.example")
    code = _code(_send(world))
    world["be"](RECIPIENT)
    _invoke("handoff", "accept", code)
    patch = tmp_path / "result.patch"
    patch.write_text("+    return slug\n")
    _invoke("handoff", "done", code, "Fixed; 6 tests pass", "--file", str(patch))
    world["be"](SENDER)
    _invoke("handoff", "status", "ho-1a2b3c4d")
    _invoke("handoff", "status", "ho-1a2b3c4d")
    told = [m for m in world["mails"] if m["to"] == "alice@personal.example" and "Done" in m["subject"]]
    assert len(told) == 1 and "Fixed; 6 tests pass" in told[0]["message"]
    assert "+    return slug" in told[0]["message"] and "result.patch" in told[0]["message"]


def test_the_inbox_names_the_sender_by_the_name_their_handoff_carries(world):
    code = _code(_send(world))
    world["be"](RECIPIENT)
    _invoke("handoff", "accept", code)
    world["be"](SENDER)
    _invoke("handoff", "status", "ho-1a2b3c4d")
    drafts = Path(os.environ["AGENT_CONFIG_PATH"]) / "handoff" / "drafts"
    named = dict(_bundle(RECIPIENT["mail"]), id="ho-2b3c4d5e", from_name="Alice Liddell")
    (drafts / "ho-2b3c4d5e.json").write_text(json.dumps(bundles.seal(named)))
    _invoke("handoff", "send", RECIPIENT["mail"], "--draft", "ho-2b3c4d5e", "--yes")
    world["be"](RECIPIENT)
    listed = _invoke("handoff", "inbox").output
    # b21 on Parrot listed "from 0x5fb5bef013 (0x5fb5bef013@mail…)" for a sender whose bundle said Aaron Test.
    assert f"from Alice Liddell ({SENDER['mail']})" in listed


def test_follow_feeds_the_senders_own_answer_back_into_the_opened_session_until_done(world, monkeypatch, tmp_path):
    """b22 on Parrot: the agent asked what only the sender knew, the sender answered by hand, and nothing
    picked it up: the session had ended. follow runs the work turn, then each hand answer, until done."""
    from connectonion.cli.commands import handoff_commands
    from connectonion.handoff import opener
    code = _code(_send(world))
    world["be"](RECIPIENT)
    _invoke("handoff", "accept", code)
    turns = []

    def turn(agent, session, cwd, prompt):
        turns.append(prompt)
        if len(turns) == 1:                                          # the work turn asks, the sender answers
            _invoke("handoff", "ask", code, "Suffix inside the limit?")
            world["be"](SENDER)
            _invoke("handoff", "status", "ho-1a2b3c4d")                 # their agent answers automatically
            _invoke("handoff", "answer", "ho-1a2b3c4d", "No: the suffix may exceed N.")
            world["be"](RECIPIENT)
        else:
            _invoke("handoff", "done", code, "Truncation with suffixes, 6 tests pass")
    monkeypatch.setattr(opener, "turn", turn)
    monkeypatch.setattr(handoff_commands.time, "sleep", lambda s: None)
    monkeypatch.setattr(handoff_commands, "_accept_code", lambda handoff_id: code)
    # The first answer must arrive after the work turn's own snapshot, as it did on Parrot.
    real = handoff_commands._answers_by_hand
    calls = []
    monkeypatch.setattr(handoff_commands, "_answers_by_hand",
                        lambda hid: (calls.append(1), [] if len(calls) == 1 else real(hid))[1])
    handoff_commands.handle_follow("ho-1a2b3c4d", "codex", "thread-1", tmp_path)
    assert len(turns) == 2 and "No: the suffix may exceed N." in turns[1]
    assert not any("Answered automatically" in t for t in turns)                 # only the sender's own words


# ---- #2478: the mail goes from the person's own mailbox ----

class _FakeGmail:
    sent = []

    def send(self, to, subject, body, html=None):
        self.sent.append({"to": to, "subject": subject, "text": body, "html": html})
        return f"Email sent successfully to {to}. Message ID: g-{len(self.sent)}"


def test_with_a_gmail_connected_the_handoff_goes_from_it_not_the_agent_mailbox(world, monkeypatch):
    _FakeGmail.sent = []
    monkeypatch.setattr(transport, "own_mailbox", lambda: ("gmail", "alice.liddell@gmail.com"))
    monkeypatch.setattr(transport, "_own_tool", lambda channel: _FakeGmail())
    world["be"](SENDER)
    drafts = Path(os.environ["AGENT_CONFIG_PATH"]) / "handoff" / "drafts"
    drafts.mkdir(parents=True)
    (drafts / "ho-1a2b3c4d.json").write_text(json.dumps(_bundle(RECIPIENT["mail"])))
    preview = _invoke("handoff", "send", RECIPIENT["mail"], "--draft", "ho-1a2b3c4d").output
    assert "It goes from your Gmail, alice.liddell@gmail.com" in preview
    sent = _invoke("handoff", "send", RECIPIENT["mail"], "--draft", "ho-1a2b3c4d", "--yes")
    assert sent.exit_code == 0, sent.output
    assert world["mails"] == [] and len(_FakeGmail.sent) == 1                    # nothing from the agent mailbox
    mail = _FakeGmail.sent[0]
    assert mail["to"] == RECIPIENT["mail"] and "co handoff accept coh3." in mail["text"]
    assert "<pre" in mail["html"] and "from your Gmail (alice.liddell@gmail.com)" in sent.output
    world["be"](RECIPIENT)                                                         # the prompt in it still works
    assert _invoke("handoff", "accept", _code(mail["text"])).exit_code == 0


def test_without_one_the_preview_says_the_agent_mailbox_may_read_as_spam_and_how_to_avoid_it(world):
    world["be"](SENDER)
    drafts = Path(os.environ["AGENT_CONFIG_PATH"]) / "handoff" / "drafts"
    drafts.mkdir(parents=True)
    (drafts / "ho-1a2b3c4d.json").write_text(json.dumps(_bundle(RECIPIENT["mail"])))
    preview = " ".join(_invoke("handoff", "send", RECIPIENT["mail"], "--draft", "ho-1a2b3c4d").output.split())
    assert "from your agent's mailbox" in preview and "may take for spam" in preview
    assert "co auth google" in preview and "--via" not in preview                   # no flag for the person (Aaron)


def test_via_mcp_mails_nothing_and_hands_the_mail_to_the_agents_own_mail_tool(world):
    world["be"](SENDER)
    drafts = Path(os.environ["AGENT_CONFIG_PATH"]) / "handoff" / "drafts"
    drafts.mkdir(parents=True)
    (drafts / "ho-1a2b3c4d.json").write_text(json.dumps(_bundle(RECIPIENT["mail"])))
    sent = _invoke("handoff", "send", RECIPIENT["mail"], "--draft", "ho-1a2b3c4d", "--yes", "--via", "mcp")
    assert sent.exit_code == 0, sent.output
    assert world["mails"] == [] and "co mailed nothing" in sent.output
    flat = " ".join(sent.output.split())
    assert f"to: {RECIPIENT['mail']}" in flat and "subject: alice@mail.openonion.ai passed you some work" in flat
    text = Path(re.search(r"plain-text body: (\S+)", flat).group(1)).read_text()
    assert "co handoff accept coh3." in text
    assert "went from your mail tool" in _invoke("handoff", "status", "ho-1a2b3c4d").output


def test_the_mail_is_in_the_language_the_sender_wrote_in(world):
    zh = dict(_bundle(RECIPIENT["mail"]), title="保存登录令牌",
              conversation=[{"at": "", "user": "登录令牌用 httpOnly cookie 还是 localStorage？", "ai": "cookie"}])
    mail = bundles.notice(bundles.seal(zh), "PROMPT")
    assert mail["subject"].startswith("alice@mail.openonion.ai 想把一项工作交给你")
    assert "新开一个对话" in mail["text"] and "连点三下即可全选" in mail["text"]
    assert bundles.notice(_bundle(RECIPIENT["mail"]), "PROMPT")["subject"].endswith("passed you some work: Store the login token")


def test_a_first_mail_without_co_in_its_subject_is_still_found_in_the_inbox(world):
    # The person's mail no longer starts "[co handoff]"; an agent mailbox finds it by the bundle in it.
    _send(world)
    world["be"](RECIPIENT)
    listed = _invoke("handoff", "inbox").output
    assert "ho-1a2b3c4d" in listed

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
    monkeypatch.setattr(transport, "sent_status", lambda to, subject: {"status": "sent"})
    monkeypatch.setattr("connectonion.cli.commands.project_cmd_lib.load_api_key", lambda: "token")
    monkeypatch.chdir(tmp_path)
    return {"mails": mails, "inbox": inbox, "be": be}


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
    return re.search(r"co handoff accept (coh[12]\.[A-Za-z0-9_-]+)", text).group(1)


# ---- the prompt ----

def test_the_mail_is_one_prompt_with_the_brief_inline_and_no_power_user_commands(world):
    body = _send(world)
    assert "Copy everything in the box into Codex or Claude Code" in body
    assert "Reject B." in body and "JS cannot read it" in body                      # the handoff, inline
    # Plain `pip install connectonion` gets the last stable release, which has no co handoff accept.
    from connectonion.handoff.replies import MIN_VERSION
    # A pre-release floor admits pre-releases of co by itself (PEP 440); --pre would admit them for dependencies too.
    floor = f'"connectonion>={MIN_VERSION}"'
    # Isolated installs only, in this order; never the recipient's global Python (#2396).
    uv, pipx = body.index(f"uv tool install {floor}"), body.index(f"pipx install --force {floor}")
    venv = body.index(f"python3 -m venv ~/.co-venv && ~/.co-venv/bin/pip install {floor}")
    assert uv < pipx < venv
    assert "pip install --upgrade" not in body and "--pre" not in body
    assert "do not run co init" in body and "co init --yes" in body
    assert f"co handoff accept {_code(body)}" in body and "co handoff ask " in body
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
    assert f"The sender {SENDER['address']} is now your agent's contact alice (co trust list)" in accepted.output
    assert tools.is_contact(SENDER["address"], Path(os.environ["AGENT_CONFIG_PATH"]))
    assert transport.resolve("alice") == SENDER["mail"]

    world["be"](SENDER)
    co_dir = Path(os.environ["AGENT_CONFIG_PATH"])
    assert not tools.is_contact(RECIPIENT["address"], co_dir)          # not before the sender sees the acceptance
    status = _invoke("handoff", "status", "ho-1a2b3c4d")
    assert f"{RECIPIENT['address']} is now your agent's contact bob (co trust list)" in status.output
    assert tools.is_contact(RECIPIENT["address"], co_dir) and not tools.is_whitelisted(RECIPIENT["address"], co_dir)
    assert transport.contacts() == {"bob": {"mail": RECIPIENT["mail"], "agent": RECIPIENT["address"], "inbox": True}}  # kept its name; reads the inbox
    peers = json.loads((co_dir / "handoff" / "peers.json").read_text())
    assert peers[RECIPIENT["address"]] == {"mailbox": RECIPIENT["mail"], "scope": "handoff", "handoffs": ["ho-1a2b3c4d"]}


def test_a_new_contact_never_overwrites_one_with_the_same_name(world):
    world["be"](RECIPIENT)
    assert _invoke("handoff", "contact", "alice", "other-alice@example.com").exit_code == 0
    assert transport.meet(SENDER["mail"], SENDER["address"]) == "alice-a1a1a1"
    assert transport.contacts()["alice"] == {"mail": "other-alice@example.com"}


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
    assert len(_code(_send(world))) < 120


def test_the_install_floor_is_a_published_version_not_the_senders_build(world, monkeypatch):
    # 2026-10-11: a sender on 1.9.2b10.dev1 mailed `connectonion>=1.9.2b10.dev1`, which no index had.
    from connectonion.handoff import replies
    monkeypatch.setattr("connectonion._version.__version__", "9.9.9.dev1")
    body = _send(world)
    assert f'"connectonion>={replies.MIN_VERSION}"' in body
    assert ".dev" not in body


def test_a_person_reads_the_task_before_the_agent_steps_and_sees_no_markdown_fences(world):
    body = _send(world)
    raw = world["mails"][-1]["message"]
    assert "```" not in raw
    assert body.index("handed you a task") < body.index("Copy everything in the box") < body.index("1. Run co --version")
    assert body.index("Where it stands:") < body.index("1. Run co --version")


def test_the_install_floor_is_never_newer_than_this_release():
    # A released sender must only ask for a version that exists once it is on PyPI.
    from packaging.version import Version
    from connectonion import __version__
    from connectonion.handoff.replies import MIN_VERSION
    assert Version(MIN_VERSION) <= Version(__version__)


# ---- #2410: mail finds the agent, the agent inbox carries the rest ----

def test_after_the_first_mail_every_reply_goes_to_the_agent_inbox(world):
    code = _code(_send(world))
    assert code.startswith("coh2.") and len(world["mails"]) == 1
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
    code = _code(_send(world)).replace("coh2.", "coh1.", 1)   # what 1.9.2b11 and earlier generate
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
    assert len(world["mails"]) == mails_before and world["inbox"][-1]["to"] == RECIPIENT["address"]
    assert "their agent's inbox" in _invoke("handoff", "status", "ho-2b3c4d5e").output

    world["be"](RECIPIENT)
    listed = _invoke("handoff", "inbox")
    assert "ho-2b3c4d5e" in listed.output and "Second task" in listed.output
    shown = _invoke("handoff", "show", "ho-2b3c4d5e")
    assert "co handoff accept coh2." in shown.output                         # how to take it over, without the mail


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
    assert "context" in answers[0] and "context" not in answers[1]
    assert "session copy" in answers[1]["text"]


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
    assert "Answered automatically: q3?" in status.output


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
    assert "Answered automatically, with the session copy: q1?" in status.output
    assert "Answered automatically: q2?" in status.output


def test_a_session_file_that_is_gone_still_gets_an_answer_without_the_copy(world, tmp_path):
    code = _send_from_session(world, tmp_path)
    world["be"](RECIPIENT)
    _invoke("handoff", "accept", code)
    _invoke("handoff", "ask", code, "q1?")
    (tmp_path / "alice-session.jsonl").unlink()   # Claude Code deletes sessions after 30 days
    world["be"](SENDER)
    status = _invoke("handoff", "status", "ho-1a2b3c4d")
    assert status.exit_code == 0, status.output
    [answer] = _answers(world)
    assert "context" not in answer and "no longer" in answer["text"]


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

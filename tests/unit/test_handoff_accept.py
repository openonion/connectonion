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
    """One mail service; `be(who)` switches which agent (and which ~/.co) is running."""
    mails, homes = [], {}

    def be(who):
        homes.setdefault(who["mail"], tmp_path / who["mail"])
        monkeypatch.setenv("AGENT_CONFIG_PATH", str(homes[who["mail"]]))
        monkeypatch.setenv("AGENT_EMAIL", who["mail"])
        monkeypatch.setattr(transport, "my_address", lambda: who["address"])

    def deliver(to, subject, body, idempotency_key):
        mails.append({"id": str(len(mails) + 1), "from": os.environ["AGENT_EMAIL"], "to": to,
                      "subject": subject, "message": body, "timestamp": f"2026-10-11T10:{len(mails):02d}:00"})
        return {"success": True, "message_id": f"msg-{len(mails)}", "from": os.environ["AGENT_EMAIL"]}

    monkeypatch.setattr(transport, "deliver", deliver)
    monkeypatch.setattr(transport, "fetch", lambda last=200: [
        m for m in reversed(mails) if m["to"] == os.environ["AGENT_EMAIL"] and m["subject"].startswith(transport.SUBJECT_PREFIX)])
    monkeypatch.setattr(transport, "sent_status", lambda to, subject: {"status": "sent"})
    monkeypatch.setattr("connectonion.cli.commands.project_cmd_lib.load_api_key", lambda: "token")
    monkeypatch.chdir(tmp_path)
    return {"mails": mails, "be": be}


def _bundle(to: str) -> dict:
    return bundles.seal({
        "format": bundles.FORMAT, "id": "ho-1a2b3c4d", "from": SENDER["mail"], "to": to,
        "created_at": "2026-10-11T10:00:00+00:00", "task": "the login task", "title": "Store the login token",
        "source": {"kind": "codex", "session": "t", "turns_included": 1, "compacted": False},
        "may_do": [], "where_it_stands": "Option A chosen, no code yet",
        "decided": [{"decision": "httpOnly cookie", "why": "JS cannot read it"}],
        "rejected": [{"option": "Option B (localStorage)", "why_not": "third-party scripts can read it"}],
        "open_questions": ["Cookie lifetime?"], "references": [],
        "excerpt": [{"role": "user", "text": "Reject B.", "timestamp": ""}]})


def _send(world, to=RECIPIENT["mail"]) -> str:
    """Alice sends a handoff to `to`; returns the mail body the recipient gets."""
    world["be"](SENDER)
    drafts = Path(os.environ["AGENT_CONFIG_PATH"]) / "handoff" / "drafts"
    drafts.mkdir(parents=True)
    (drafts / "ho-1a2b3c4d.json").write_text(json.dumps(_bundle(to)))
    result = _invoke("handoff", "send", to, "--draft", "ho-1a2b3c4d", "--yes")
    assert result.exit_code == 0, result.output
    return html.unescape(re.sub(r"</?(pre|p)>", "", world["mails"][-1]["message"]))   # as a mail client shows it


def _code(text: str) -> str:
    return re.search(r"co handoff accept (coh1\.[A-Za-z0-9_-]+)", text).group(1)


# ---- the prompt ----

def test_the_mail_is_one_prompt_with_the_brief_inline_and_no_power_user_commands(world):
    body = _send(world)
    assert "Paste this into Codex or Claude Code" in body
    assert "Option B (localStorage): third-party scripts can read it" in body      # the brief, inline
    # Plain `pip install connectonion` gets the last stable release, which has no co handoff accept.
    from connectonion import __version__
    assert f'pip install --pre --upgrade "connectonion>={__version__}"' in body and "co init --yes" in body
    assert f"co handoff accept {_code(body)}" in body and "co handoff ask " in body
    assert "co handoff inbox" not in body and "co handoff open" not in body       # #2378
    raw = world["mails"][-1]["message"]
    assert raw.startswith("<pre>Paste this into Codex or Claude Code")              # newlines survive the HTML mail
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


def test_a_handoff_code_is_never_an_invite_and_never_a_contact(world, monkeypatch):
    # Contacts may EXEC on the host; a forwarded handoff mail must never lead there.
    from connectonion.network.host.server import EXEC_REQUIRES
    from connectonion.network.trust import tools
    from connectonion.network.trust.fast_rules import evaluate_request
    assert "contact" in EXEC_REQUIRES
    code = _code(_send(world))
    world["be"](RECIPIENT)
    assert _invoke("handoff", "accept", code).exit_code == 0
    world["be"](SENDER)
    assert _invoke("handoff", "status", "ho-1a2b3c4d").exit_code == 0
    co_dir = Path(os.environ["AGENT_CONFIG_PATH"])
    config = {"allow": ["whitelisted", "contact"], "onboard": {"invite_code": ["ABCDE-FGHJK-MNPQR"]}, "default": "deny"}
    assert evaluate_request(config, RECIPIENT["address"], {"invite_code": code}, co_dir=co_dir) != "allow"
    assert not tools.is_contact(RECIPIENT["address"], co_dir) and not tools.is_whitelisted(RECIPIENT["address"], co_dir)
    peers = json.loads((co_dir / "handoff" / "peers.json").read_text())
    assert peers[RECIPIENT["address"]] == {"mailbox": RECIPIENT["mail"], "scope": "handoff", "handoffs": ["ho-1a2b3c4d"]}


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
    assert world["mails"][-1]["to"] == SENDER["mail"]

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

def test_one_turn_and_no_empty_permission_line():
    text = bundles.brief_markdown(_bundle("x"))
    assert "1 turn of" in text and "1 turns" not in text
    assert "not stated by the sender" not in text
    with_permission = bundles.brief_markdown(bundles.seal(dict(_bundle("x"), may_do=["edit auth/"])))
    assert "Recipient may: edit auth/" in with_permission.split("## Task")[0]


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

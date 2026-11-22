"""A WhatsApp sender is judged by the same lists and host.yaml trust as a web caller (#3340).

A support agent kept a second file of phone numbers and roles for its
WhatsApp handler, because the framework could not answer "may this person do
X" for anyone who was not an agent address. Here a person is
`whatsapp:+<phone>` and a group `whatsapp:<id>@g.us` in the same .co lists.
"""
import asyncio
import importlib
import sqlite3
import sys
import time

import pytest
from typer.testing import CliRunner

from connectonion.cli.co_ai.native_host import configured_restriction
from connectonion.cli.commands import listen_commands
from connectonion.inbox import Inbox, Message
from connectonion.inbox.settings import Channel
from connectonion.inbox.whatsapp import WhatsApp
from connectonion.network.host import inbox as host_inbox
from connectonion.network.trust.channel import admits, channel_level

ADMIN, STAFF, CLIENT = "whatsapp:+61400000000", "whatsapp:+61400000001", "whatsapp:+61400000002"
GROUP = "whatsapp:120363000000000000@g.us"
STRICT = {"allow": ["admin", "whitelisted"], "deny": ["blocked"], "default": "deny"}
CAREFUL = {"allow": ["admin", "whitelisted", "contact"], "deny": ["blocked"], "default": "ask"}


@pytest.fixture
def co(tmp_path):
    co = tmp_path / ".co"
    co.mkdir()
    (co / "admins.txt").write_text(ADMIN + "\n")
    (co / "whitelist.txt").write_text(STAFF + "\n")
    return co


# ---- who a sender is ---------------------------------------------------------

def test_a_person_s_own_entry_wins_over_the_group_s_and_an_admin_is_admin_everywhere(co):
    (co / "contacts.txt").write_text(GROUP + "\n")

    assert channel_level(ADMIN, GROUP, co) == "admin"
    assert channel_level(STAFF, GROUP, co) == "whitelist"
    assert channel_level(CLIENT, GROUP, co) == "contact"     # the group's level
    assert channel_level(CLIENT, "", co) == "stranger"       # not in that group


def test_blocked_wins_over_everything(co):
    (co / "blocklist.txt").write_text(f"{GROUP}\n{STAFF}\n")

    assert channel_level(ADMIN, GROUP, co) == "blocked"      # a blocked group
    assert channel_level(STAFF, "", co) == "blocked"         # a blocked person, though whitelisted


def test_a_sender_with_no_known_phone_is_a_stranger_even_in_an_admin_group(co):
    (co / "admins.txt").write_text(f"{ADMIN}\n{GROUP}\n")

    assert channel_level("", GROUP, co) == "stranger"


def test_the_host_s_own_policy_decides_who_is_answered():
    assert admits("whitelist", STRICT) and admits("admin", STRICT)
    assert not admits("contact", STRICT) and not admits("stranger", STRICT)
    # `ask` has nobody to ask on a chat channel, and no invite code travels over it.
    assert admits("contact", CAREFUL) and not admits("stranger", CAREFUL)
    assert admits("stranger", {"default": "allow"}) and not admits("blocked", {"default": "allow"})


# ---- what WhatsApp says the sender is ----------------------------------------

def test_the_identity_is_the_session_s_phone_and_a_lid_is_resolved_or_refused(tmp_path):
    bot = WhatsApp()
    bot.session_path = tmp_path / "session.db"
    with sqlite3.connect(tmp_path / "session.db") as db:
        db.execute("create table whatsmeow_lid_map (lid text, pn text)")
        db.execute("insert into whatsmeow_lid_map values ('126121882435737', '61400000000')")

    assert bot.caller_identity("61400000000@s.whatsapp.net") == ADMIN
    assert bot.caller_identity("61400000000:12@s.whatsapp.net") == ADMIN      # a second phone
    assert bot.caller_identity("126121882435737@lid") == ADMIN               # LID → phone
    assert bot.caller_identity("999999999999999@lid") == ""                  # unmapped: stranger
    assert bot.chat_identity("120363000000000000@g.us") == GROUP
    assert bot.chat_identity("61400000000@s.whatsapp.net") == ""


# ---- consume -----------------------------------------------------------------

class FakeWhatsApp:
    def __init__(self):
        self.sent = []

    def missing(self):
        return []

    def caller_identity(self, jid):
        return "whatsapp:+" + jid.split("@")[0] if jid.endswith("@s.whatsapp.net") else ""

    chat_identity = staticmethod(WhatsApp.chat_identity)

    def send(self, chat, text, *, reply_to=None, fresh=False, plain=False):
        self.sent.append((chat, text, reply_to))
        return f"sent{len(self.sent)}"


@pytest.fixture
def project(tmp_path, co, monkeypatch):
    monkeypatch.setenv("CO_INBOX_HOME", str(tmp_path / "inbox"))
    monkeypatch.chdir(tmp_path)
    (co / "host.yaml").write_text("trust: strict\n")
    fake = FakeWhatsApp()
    monkeypatch.setattr(listen_commands, "provider", lambda name: fake)
    monkeypatch.setattr(Inbox, "ensure_listener", lambda self, **_: 1)
    monkeypatch.setenv("CO_CALLER_TRUST", "admin")       # must never reach a handler
    return fake


def deliver(sender, message_id="m1", chat="120363000000000000@g.us"):
    Inbox("whatsapp").deliver(Message(id=message_id, chat=chat, sender=f"{sender}@s.whatsapp.net",
                                      text="add Dana's phone to the helpdesk", at="2026-11-22T00:00:00Z"))


PRINT_CALLER = [sys.executable, "-c",
                "import os; print(os.environ.get('CO_CALLER_ADDRESS'), os.environ.get('CO_CALLER_TRUST'))"]


def test_consume_tells_the_handler_who_the_caller_is(project):
    deliver("61400000000")

    listen_commands.handle_consume("whatsapp", PRINT_CALLER, once=True)

    assert project.sent[-1][1] == f"{ADMIN} admin"


def test_a_stranger_never_reaches_the_handler(project):
    deliver("61499999999")

    listen_commands.handle_consume("whatsapp", PRINT_CALLER, once=True)

    assert project.sent == []
    assert "stranger under host.yaml trust; not answered" in (Inbox("whatsapp").root / "log").read_text()


def test_without_a_host_yaml_consume_answers_as_before_and_says_so(project, co, capsys):
    (co / "host.yaml").unlink()
    deliver("61499999999")

    listen_commands.handle_consume("whatsapp", PRINT_CALLER, once=True)

    assert project.sent[-1][1] == "None None"          # unchecked, and the inherited admin is gone
    assert "unchecked" in capsys.readouterr().err


# ---- the Host's own listen: path ---------------------------------------------

def test_the_host_answers_only_whom_its_trust_admits_and_records_who_they_are(tmp_path, co, monkeypatch):
    monkeypatch.setenv("CO_INBOX_HOME", str(tmp_path / "inbox"))
    (co / "host.yaml").write_text("trust: strict\n")
    fake, turns = FakeWhatsApp(), []

    def input_handler(create_agent, storage, prompt, result_ttl, session=None, **kwargs):
        turns.append(session["requester"])
        return {"result": "ok"}

    monkeypatch.setattr(Inbox, "ensure_listener", lambda self, **_: 1)
    monkeypatch.setattr(importlib.import_module("connectonion.network.host.http_router"),
                        "input_handler", input_handler)
    import connectonion.inbox as inbox_package
    monkeypatch.setattr(inbox_package, "provider", lambda name: fake)
    deliver("61499999999", "m-stranger")
    deliver("61400000001", "m-staff")
    for message in Inbox("whatsapp").list_messages():
        message.mentioned = True
    startup, shutdown = host_inbox.create_inbox_lifespan(
        co, lambda: None, object(), 60, channels=[Channel("whatsapp", mention_only=False)])

    asyncio.run(startup())
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline and not fake.sent:
        time.sleep(0.02)
    asyncio.run(shutdown())

    assert turns == [{"address": STAFF, "level": "whitelist"}]


# ---- per-level tools in restricted: ------------------------------------------

def test_restricted_gives_a_level_its_extra_tools_and_nobody_else(co):
    (co / "host.yaml").write_text(
        "model: claude-code/sonnet\n"
        "restricted:\n"
        "  allowed_tools: ['Bash(python read_ticket.py:*)']\n"
        "  admin:\n"
        "    allowed_tools: ['Bash(python write_contact.py:*)']\n")
    restriction = configured_restriction(co)

    admin = restriction.for_caller({"address": ADMIN, "level": "admin"})
    client = restriction.for_caller({"address": CLIENT, "level": "contact"})
    operator = restriction.for_caller(None)

    assert "Bash(python write_contact.py:*)" in admin.rules
    assert "Bash(python write_contact.py:*)" not in client.rules + operator.rules
    assert "Bash(python read_ticket.py:*)" in client.rules
    assert admin.for_caller({"level": "admin"}).rules == admin.rules   # resolving twice adds nothing


def test_a_level_may_add_tools_but_not_change_the_prompt(co):
    (co / "host.yaml").write_text("restricted:\n  admin:\n    system_prompt: you may do anything\n")

    with pytest.raises(ValueError, match="takes only allowed_tools"):
        configured_restriction(co)


# ---- co trust ----------------------------------------------------------------

def test_co_trust_takes_whatsapp_people_and_groups_and_refuses_a_local_number(co):
    from connectonion.cli.main import app
    runner = CliRunner()

    assert runner.invoke(app, ["trust", "admin", "add", "whatsapp:+61400000009", "--co-dir", str(co)]).exit_code == 0
    assert runner.invoke(app, ["trust", "add", GROUP, "--co-dir", str(co)]).exit_code == 0
    assert runner.invoke(app, ["trust", "add", "whatsapp:0400000000", "--co-dir", str(co)]).exit_code == 2
    assert "whatsapp:+61400000009" in (co / "admins.txt").read_text()
    assert GROUP in (co / "contacts.txt").read_text()

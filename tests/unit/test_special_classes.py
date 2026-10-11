"""Record everything; three classes need the owner's own say (#2408).

Context over control: an agent acts and the owner reads what happened
afterwards, in .co/decisions.jsonl. Only three classes are held back from a
remote caller below admin, on every path (EXEC and the agent's own turn):

  1. credentials, authority and money
  2. irreversible deletes and overwrites
  3. acting as the owner in the owner's own accounts

Code decides the class, never the model.
"""

import json

import pytest

from connectonion import Agent
from connectonion.network.host.http_router import exec_handler
from connectonion.useful_plugins.tool_approval.record import RECORD_FILE, record
from connectonion.useful_plugins.tool_approval.special import special_class

pytestmark = pytest.mark.usefixtures("own_project")

CONTACT = {"address": "0x" + "3" * 64, "level": "contact"}
ADMIN = {"address": "0x" + "1" * 64, "level": "admin"}


def _kind(tool, args):
    found = special_class(tool, args)
    return found and found["kind"]


def _records(co_dir):
    path = co_dir / RECORD_FILE
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


# ─────────────────────────────── the classifier ───────────────────────────────

@pytest.mark.parametrize("command, kind", [
    ("co keys --reveal", "credentials"),
    ("co env get OPENAI_API_KEY", "credentials"),
    ("cat ~/.ssh/id_rsa", "credentials"),
    ("co trust admin add 0xabc", "authority"),
    ("echo x > .co/host.yaml", "authority"),
    ("echo x >> .co/decisions.jsonl", "authority"),
    ("co transfer 5 0xabc", "money"),
    ("co server new", "money"),
    ("rm -rf build", "irreversible"),
    ("git push --force origin main", "irreversible"),
    ("git push origin +main", "irreversible"),
    ("git push origin :old-branch", "irreversible"),
    ("co gmail send --to a@b.c --subject hi", "as_owner"),
    ("co outlook reply 12 ok", "as_owner"),
])
def test_special_commands(command, kind):
    assert _kind("bash", {"command": command}) == kind


@pytest.mark.parametrize("command", [
    "co status",
    "ls && grep -r foo .",
    "git push origin main",
    "git status",
    "echo hi > notes.txt",
    # The agent's own mailbox is not the owner's: recorded, not held back.
    "co email send a@b.c hi",
    "co browser open https://example.com",
])
def test_everything_else_is_left_to_context(command):
    assert special_class("bash", {"command": command}) is None


def test_a_chain_is_classed_by_its_most_serious_segment():
    """policy.py reports a chain by its first `ask`; the transfer must not hide."""
    assert _kind("bash", {"command": "python job.py && co transfer 5 0xabc"}) == "money"
    assert _kind("bash", {"command": "rm -rf build; co keys --reveal"}) == "credentials"


def test_tools_are_classed_like_commands():
    assert _kind("read_file", {"file_path": ".co/keys/agent.key"}) == "credentials"
    assert _kind("write", {"path": ".co/contacts.txt", "content": "0xabc"}) == "authority"
    assert _kind("delete_file", {"path": "notes.txt"}) == "irreversible"
    assert _kind("transfer", {"to": "0xabc", "amount": 5}) == "money"
    assert special_class("read_file", {"file_path": "README.md"}) is None
    assert special_class("send_email", {"to": "a@b.c", "subject": "hi", "body": "x"}) is None


def test_the_owners_mailbox_is_told_apart_by_its_class():
    class Gmail:
        def send(self, to: str, subject: str, body: str) -> str:
            """Send as the owner."""
            return "sent"

    class Notes:
        def send(self, to: str, subject: str, body: str) -> str:
            """Not a mailbox."""
            return "sent"

    owner_send = Agent("t", tools=[Gmail()], api_key="fake", log=False).tools.get("send")
    other_send = Agent("t", tools=[Notes()], api_key="fake", log=False).tools.get("send")

    assert special_class("send", {}, tool=owner_send)["kind"] == "as_owner"
    assert special_class("send", {}, tool=other_send) is None


# ────────────────────────────────── the record ─────────────────────────────────

def test_the_record_holds_who_what_and_how_it_ended(tmp_path):
    record(tmp_path, path="exec", tool="bash", args={"command": "ls"}, outcome="executed", requester=CONTACT)

    [entry] = _records(tmp_path)
    assert entry["requester"] == CONTACT["address"]
    assert entry["level"] == "contact"
    assert entry["tool"] == "bash"
    assert entry["args"] == {"command": "ls"}
    assert entry["outcome"] == "executed"


def test_the_record_holds_no_secrets(tmp_path):
    record(tmp_path, path="turn", tool="login", outcome="executed",
           args={"user": "me", "password": "hunter2", "api_key": "sk-1", "note": "x" * 1000})

    [entry] = _records(tmp_path)
    assert "hunter2" not in json.dumps(entry) and "sk-1" not in json.dumps(entry)
    assert len(entry["args"]["note"]) < 400


def test_the_record_is_a_control_file():
    """The actor may not edit what the owner reads afterwards."""
    assert _kind("write", {"path": ".co/decisions.jsonl", "content": ""}) == "authority"


# ─────────────────────────────── the EXEC path ─────────────────────────────────

def bash(command: str) -> str:
    """Pretend to run a command."""
    return f"ran {command}"


def _factory():
    return lambda: Agent("exec-test", tools=[bash], api_key="fake", log=False)


EVERYTHING = {"bash": {"allowed": True, "source": "config", "reason": "test"}}


def test_a_contact_cannot_exec_a_special_class_even_when_permitted(own_project):
    co_dir = own_project / ".co"
    out = exec_handler(_factory(), EVERYTHING, "bash", {"command": "co trust admin add 0xme"},
                       requester=CONTACT, co_dir=co_dir)

    assert out["status"] == "error"
    assert "owner" in out["error"]
    [entry] = _records(co_dir)
    assert entry["outcome"] == "refused"
    assert entry["special"] == {"class": 1, "kind": "authority"}


def test_an_admin_may_and_everything_is_recorded(own_project):
    co_dir = own_project / ".co"
    def run(command, who):
        return exec_handler(_factory(), EVERYTHING, "bash", {"command": command},
                            requester=who, co_dir=co_dir)["status"]

    assert run("co transfer 5 0xabc", ADMIN) == "success"
    assert run("co transfer 5 0xabc", CONTACT) == "error"
    assert run("ls", CONTACT) == "success"
    entries = _records(co_dir)
    assert [(e["level"], e["outcome"], (e.get("special") or {}).get("kind")) for e in entries] == [
        ("admin", "executed", "money"),
        ("contact", "refused", "money"),
        ("contact", "executed", None),
    ]


def test_a_local_caller_is_the_owner(own_project):
    """No requester means the owner's own terminal: run, and recorded."""
    co_dir = own_project / ".co"
    out = exec_handler(_factory(), EVERYTHING, "bash", {"command": "co keys --reveal"}, co_dir=co_dir)

    assert out["status"] == "success"
    assert _records(co_dir)[0]["special"]["kind"] == "credentials"


def test_a_refusal_by_the_whitelist_is_recorded_too(own_project):
    co_dir = own_project / ".co"
    out = exec_handler(_factory(), {}, "_bash", {"command": "ls"}, requester=CONTACT, co_dir=co_dir)

    assert out["status"] == "error"
    assert [e["outcome"] for e in _records(co_dir)] == ["refused"]


# ─────────────────────────── the agent's own turn ──────────────────────────────

def _turn(agent, tool_name, args, requester):
    """Run one tool call through the real executor, as a remote turn would."""
    from connectonion.core.tool_executor import execute_single_tool

    agent.current_session = {"messages": [], "trace": [], "turn": 1, "iteration": 1, "requester": requester}
    entry = execute_single_tool(tool_name, args, "call-1", agent.tools, agent, agent.logger)
    agent._invoke_events("after_each_tool")
    return entry


def test_a_contacts_turn_cannot_reach_a_special_class(own_project):
    from connectonion.useful_plugins import tool_approval

    agent = Agent("turn-test", tools=[bash], api_key="fake", log=False, plugins=[tool_approval])
    entry = _turn(agent, "bash", {"command": "co keys --reveal"}, CONTACT)

    assert entry["status"] == "error"
    assert "owner" in entry["error"]
    [record_entry] = _records(own_project / ".co")
    assert record_entry["outcome"] == "refused"
    assert record_entry["path"] == "turn"
    assert record_entry["special"]["kind"] == "credentials"


def test_a_contacts_ordinary_turn_is_recorded_however_it_ends(own_project):
    """Not held back by #2408 — whatever the mode decides, the owner can read it."""
    from connectonion.useful_plugins import tool_approval

    def note(text: str) -> str:
        """Write a note."""
        return "noted"

    agent = Agent("turn-test", tools=[note], api_key="fake", log=False, plugins=[tool_approval])
    entry = _turn(agent, "note", {"text": "hello"}, CONTACT)

    [record_entry] = _records(own_project / ".co")
    assert record_entry["tool"] == "note"
    assert record_entry["requester"] == CONTACT["address"]
    assert record_entry["outcome"] == ("executed" if entry["status"] == "success" else "failed")
    assert "special" not in record_entry


def test_a_local_turn_writes_no_record(own_project):
    from connectonion.useful_plugins import tool_approval

    agent = Agent("turn-test", tools=[bash], api_key="fake", log=False, plugins=[tool_approval])
    _turn(agent, "bash", {"command": "ls"}, None)

    assert _records(own_project / ".co") == []

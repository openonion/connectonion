"""Three things need the owner; everything else is done and recorded (#2408).

Credentials and authority and money, an irreversible delete or overwrite, and
acting as the owner in the owner's own accounts. Code names the class from the
tool and its arguments, before any plugin can approve the call and in every
mode, so a contact's turn cannot reach them through Full access or a
`Bash(*)` grant, and a whitelisted EXEC cannot either.
"""

import json
from unittest.mock import MagicMock

import pytest

from connectonion import Agent, approvals
from connectonion.core.tool_executor import execute_single_tool
from connectonion.network.host.server import _make_ws_exec
from connectonion.network.trust import TrustAgent
from connectonion.network.trust.tools import add_admin, promote_to_contact
from connectonion.useful_plugins.tool_approval import tool_approval
from connectonion.useful_plugins.tool_approval.approval import is_tool_permitted
from connectonion.useful_plugins.tool_approval.policy import special_class
from tests.utils.mock_helpers import MockLLM

CONTACT = "0x" + "3" * 64
ADMIN = "0x" + "1" * 64


@pytest.mark.parametrize("tool, args, expected", [
    ("bash", {"command": "co keys"}, "credentials"),
    ("bash", {"command": "co env get OPENAI_API_KEY"}, "credentials"),
    ("read_file", {"path": ".co/keys.env"}, "credentials"),
    ("bash", {"command": "ls && co trust add 0xab"}, "authority"),
    ("write", {"path": ".co/host.yaml", "content": "x"}, "authority"),
    ("bash", {"command": "co transfer 0xab 5"}, "money"),
    ("bash", {"command": "co server new prod"}, "money"),
    ("bash", {"command": "rm -rf build"}, "irreversible"),
    ("bash", {"command": "git push --force origin main"}, "irreversible"),
    ("bash", {"command": "git reset --hard"}, "irreversible"),
    ("bash", {"command": "git push origin :old-branch"}, "irreversible"),
    ("bash", {"command": "git push --prune origin"}, "irreversible"),
    ("bash", {"command": "co gmail send --to bob@x.com"}, "as_owner"),
    ("bash", {"command": "co outlook reply 3"}, "as_owner"),
    # The body of a mail is ordinary text, apostrophes included.
    ("bash", {"command": """co gmail send --to bob --body "It's ready" """}, "as_owner"),
    ("bash", {"command": "sudo timeout 60 co server new prod"}, "money"),
    ("bash", {"command": "bash -c 'co env get OPENAI_API_KEY'"}, "credentials"),
    ("bash", {"command": "co server destroy prod"}, "irreversible"),
    ("bash", {"command": "co keys --reveal push"}, "credentials"),
    ("pay", {"amount": 5}, "money"),
    # Everything else: done and recorded, not held for the owner.
    ("bash", {"command": "co email send bob@x.com hi"}, None),   # the agent's own mailbox
    ("send_email", {"to": "bob@x.com"}, None),
    ("bash", {"command": "co server list"}, None),
    ("bash", {"command": "git push origin main"}, None),
    ("bash", {"command": "pytest -q"}, None),
    ("read_file", {"path": "README.md"}, None),
    ("delete", {"id": "row-7"}, None),   # an SDK tool's own records, not files
    ("read_file", {"path": "~nosuchuser/x"}, None),
])
def test_code_names_the_class(tool, args, expected, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert special_class(tool, args) == expected


class Mailbox:
    pass


class Gmail(Mailbox):
    """Stands in for the owner's Gmail tool: what matters is the owning class."""

    def send(self, to: str, subject: str, body: str) -> str:
        """Send as the owner."""
        return "sent"


def send_email(to: str) -> str:
    """Send from the agent's own mailbox."""
    return "sent"


def bash(command: str) -> str:
    """Run a command."""
    return "ran"


@pytest.fixture
def project(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".co").mkdir()
    return tmp_path / ".co"


def _turn(project, tools, requester, *, mode="full_access", permissions=None, plugins=(tool_approval,)):
    agent = Agent("t", tools=tools, plugins=list(plugins), llm=MockLLM(), co_dir=project)
    agent.current_session = {"messages": [], "trace": [], "turn": 1, "iteration": 1,
                             "mode": mode, "permissions": permissions or {}}
    if requester:
        agent.current_session["requester"] = requester
    return agent


def _call(agent, tool, args):
    return execute_single_tool(tool_name=tool, tool_args=args, tool_id="c1",
                               tools=agent.tools, agent=agent, logger=agent.logger)


def test_a_contacts_turn_cannot_reach_a_special_class_even_in_full_access(project):
    agent = _turn(project, [bash], {"address": CONTACT, "level": "contact"},
                  permissions={"Bash(*)": {"allowed": True, "source": "config", "reason": "all"}})

    entry = _call(agent, "bash", {"command": "co env get OPENAI_API_KEY"})

    assert entry["status"] == "error" and "owner" in entry["result"]
    [line] = [json.loads(l) for l in (project / approvals.RECORD).read_text().splitlines()]
    assert (line["class"], line["decision"]) == ("credentials", "declined")


def test_a_chat_sender_cannot_send_as_the_owner(project):
    agent = _turn(project, [Gmail()], {"address": "feishu:ou_1", "level": "open"}, plugins=())

    entry = _call(agent, "send", {"to": "bob@x.com", "subject": "s", "body": "b"})

    assert entry["status"] == "error" and "as_owner" in entry["result"]


def test_the_agents_own_mail_is_not_held(project):
    # No approval plugin, as on a hosted custom agent: only the class gate applies.
    agent = _turn(project, [send_email], {"address": "feishu:ou_1", "level": "open"}, plugins=())

    assert _call(agent, "send_email", {"to": "bob@x.com"})["status"] == "success"


def test_the_owner_at_the_terminal_is_not_declined(project):
    agent = _turn(project, [bash], None, plugins=())

    entry = _call(agent, "bash", {"command": "co server new prod"})

    assert entry["status"] == "success"
    [line] = [json.loads(l) for l in (project / approvals.RECORD).read_text().splitlines()]
    assert (line["class"], line["decision"]) == ("money", "done")


def _exec(project, caller, command):
    trust = TrustAgent("careful", co_dir=project)
    promote_to_contact(CONTACT, project)
    add_admin(ADMIN, project)
    permissions = {"Bash(co *)": {"allowed": True, "source": "config", "reason": "shipped default"}}
    handle = _make_ws_exec(lambda: Agent("t", tools=[bash], llm=MockLLM()), permissions, trust, project)
    return handle("bash", {"command": command}, caller)


def test_a_whitelisted_exec_still_cannot_reach_a_special_class(project):
    result = _exec(project, CONTACT, "co env get OPENAI_API_KEY")

    assert result["status"] == "error" and result["class"] == "credentials"
    exec_line = [json.loads(l) for l in (project / approvals.RECORD).read_text().splitlines()][-1]
    assert (exec_line["path"], exec_line["class"], exec_line["decision"]) == ("exec", "credentials", "declined")


def test_an_admin_exec_is_the_owner(project):
    assert _exec(project, ADMIN, "co env get OPENAI_API_KEY")["status"] == "success"


def test_the_agent_cannot_write_its_trust_lists():
    allowed, _ = is_tool_permitted(
        "write", {"path": ".co/whitelist.txt", "content": "0xattacker\n"},
        {"write": {"allowed": True, "source": "config", "reason": "coding agent"}})
    assert not allowed


class WorkGmail(Gmail):
    pass


def test_a_subclass_of_the_owners_mailbox_still_sends_as_the_owner(project):
    agent = _turn(project, [WorkGmail()], {"address": "feishu:ou_1", "level": "open"}, plugins=())

    assert "as_owner" in _call(agent, "send", {"to": "b", "subject": "s", "body": "b"})["result"]


def test_with_someone_connected_the_approval_flow_still_asks(project):
    """The owner in co ai's web UI is a contact, not an admin: invites promote
    to contact. A hard decline there would refuse the owner; with a client
    connected the call goes on to the existing approval flow, as before."""
    agent = _turn(project, [bash], {"address": CONTACT, "level": "contact"}, plugins=())
    agent.io = MagicMock()  # a connected client

    entry = _call(agent, "bash", {"command": "co server new prod"})

    assert entry["status"] == "success"
    assert entry["class"] == "money"

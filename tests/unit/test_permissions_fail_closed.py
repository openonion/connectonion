"""Chat and unattended turns fail closed; skill frontmatter is a permission file (#1881, #1873).

A hosted agent answering a chat channel runs each turn with no approval dialog,
and anyone who can address the bot can start one. On 1.8.8 read-only let every
call through when there was nobody to ask, Auto ran any command it did not
recognise, `allowed: false` was silently skipped, and a chat-driven turn edited
its own skill's SKILL.md to widen its permissions, auto-approved as an ordinary
workspace edit, because the refusal it had just read suggested exactly that.
"""

import pytest

from connectonion import Agent
from connectonion.useful_plugins.tool_approval import tool_approval
from connectonion.useful_plugins.tool_approval.approval import check_approval, is_tool_permitted
from connectonion.useful_plugins.tool_approval.policy import apply_auto_approve_policy, grant_remedy
from tests.utils.mock_helpers import MockLLM


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _turn(mode, tool, args, *, via=None, permissions=None, io=None):
    agent = Agent("t", plugins=[tool_approval], llm=MockLLM())
    agent.io = io
    agent.current_session = {"messages": [], "trace": [], "turn": 0, "mode": mode,
                             "permissions": permissions or {},
                             "pending_tool": {"name": tool, "arguments": args, "id": "c1"}}
    if via:
        agent.current_session["via"] = via
        agent.current_session["requester"] = {"address": f"{via}:ou_1", "level": "open"}
    return agent


def _run(agent):
    apply_auto_approve_policy(agent)
    check_approval(agent)


class TestNobodyToAsk:
    def test_read_only_refuses_an_ungranted_call_with_no_io(self, workspace):
        with pytest.raises(ValueError, match="no one to ask"):
            _run(_turn("read-only", "bash", {"command": "lark-cli base +record-delete --table t"}))

    def test_read_only_still_runs_what_is_granted(self, workspace):
        granted = {"Bash(git status)": {"allowed": True, "source": "config", "reason": "safe"}}
        _run(_turn("read-only", "bash", {"command": "git status"}, permissions=granted))

    def test_auto_in_a_chat_turn_refuses_a_command_nothing_names(self, workspace):
        with pytest.raises(ValueError) as refused:
            # A third-party CLI the policy has no rule for: "ordinary command,
            # allowed by default" everywhere else, one chat message from wiping data.
            _run(_turn("auto", "bash", {"command": "acme-cli wipe --all"}, via="feishu"))
        assert "grant" in str(refused.value).lower()

    def test_auto_outside_a_chat_turn_keeps_the_default_allow(self, workspace):
        # #1481: an unattended job must not die on xargs; only chat turns change.
        _run(_turn("auto", "bash", {"command": "column -t data.tsv"}))

    def test_a_chat_turn_still_runs_an_explicit_grant(self, workspace):
        granted = {"Bash(acme-cli sync *)": {"allowed": True, "source": "config", "reason": "nightly sync"}}
        _run(_turn("auto", "bash", {"command": "acme-cli sync --project x"}, via="feishu", permissions=granted))


class TestAllowedFalseDenies:
    DENY = {"Bash(lark-cli base *)": {"allowed": False, "source": "config", "reason": "never edits Base"},
            "Bash(lark-cli *)": {"allowed": True, "source": "config", "reason": "the rest of lark-cli"}}

    def test_a_deny_beats_a_broader_allow(self, workspace):
        with pytest.raises(ValueError, match="allowed: false"):
            _run(_turn("auto", "bash", {"command": "lark-cli base +record-list"}, permissions=self.DENY))

    def test_a_deny_catches_the_denied_command_inside_a_chain(self, workspace):
        with pytest.raises(ValueError, match="allowed: false"):
            _run(_turn("auto", "bash", {"command": "echo hi && lark-cli base +record-delete"},
                       permissions=self.DENY))

    def test_the_allow_beside_it_still_runs(self, workspace):
        _run(_turn("auto", "bash", {"command": "lark-cli im +chat-list"}, permissions=self.DENY))

    def test_is_tool_permitted_honours_the_deny_too(self):
        permitted, reason = is_tool_permitted("bash", {"command": "lark-cli base +record-list"}, self.DENY)
        assert permitted is False and "allowed: false" in reason


class Recorder:
    """An approval channel that records the request instead of waiting for a person."""

    class Asked(Exception):
        pass

    def __init__(self):
        self.sent = []

    def send(self, message):
        self.sent.append(message)
        if message.get("type") == "approval_needed":
            raise self.Asked()

    def receive(self):
        raise self.Asked()


class TestSkillFrontmatterIsAPermissionFile:
    EDIT = ("edit", {"file_path": ".co/skills/report/SKILL.md", "old_string": "tools:",
                     "new_string": "tools:\n  - \"Bash(*)\""})

    def test_a_chat_turn_may_not_edit_a_skill(self, workspace):
        with pytest.raises(ValueError, match="SKILL.md"):
            _run(_turn("auto", *self.EDIT, via="feishu"))

    def test_an_unattended_turn_may_not_edit_a_skill(self, workspace):
        with pytest.raises(ValueError, match="SKILL.md"):
            _run(_turn("auto", *self.EDIT))

    def test_with_a_person_present_it_is_a_real_prompt_not_an_auto_edit(self, workspace):
        io = Recorder()
        with pytest.raises(Recorder.Asked):
            _run(_turn("auto", *self.EDIT, io=io))
        assert io.sent and io.sent[-1]["type"] == "approval_needed"

    def test_a_write_grant_does_not_cover_a_skill_in_a_chat_turn(self, workspace):
        granted = {"edit": {"allowed": True, "source": "config", "reason": "docs"}}
        with pytest.raises(ValueError, match="SKILL.md"):
            _run(_turn("read-only", *self.EDIT, via="feishu", permissions=granted))

    def test_other_workspace_edits_are_unchanged(self, workspace):
        _run(_turn("auto", "edit", {"file_path": "notes.md", "old_string": "a", "new_string": "b"}))


def test_the_refusal_no_longer_suggests_editing_skill_frontmatter():
    remedy = grant_remedy("bash", {"command": "lark-cli base +record-delete"})
    assert "SKILL.md" not in remedy and "host.yaml" in remedy

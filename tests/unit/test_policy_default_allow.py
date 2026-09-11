"""
LLM-Note: Tests for the two remaining tool_approval defects after #1483 —
an ordinary command is allowed rather than asked (#1481's actual ask), and a
planning tool's methods are recognised by what owns them rather than by names
that collide with delete and read tools (#1447).
"""

from pathlib import Path

import pytest

from connectonion.useful_plugins.tool_approval import policy


def verdict(command, root=None):
    return policy.evaluate_auto_approve("bash", {"command": command}, root=root or Path.cwd())


class TestAnOrdinaryCommandRuns:
    """#1481 asked for default allow. #1483 lengthened the allowlist instead,
    which leaves every command nobody thought of still failing unattended."""

    @pytest.mark.parametrize("command", [
        "column -t data.tsv",
        "shasum -a 256 dist/app.whl",
        "just build",
        "swiftlint lint",
        "xcodebuild -list",
    ])
    def test_a_command_nobody_listed_is_allowed(self, command):
        result = verdict(command)
        assert result["decision"] == "allow", f"{command}: {result['reason']}"

    def test_the_reason_says_it_was_the_default_not_a_list(self):
        # jq and cat stay "read-only command": their file arguments can be
        # checked, which is a real rule. A command with nothing to check says
        # what actually decided it.
        assert "default" in verdict("swiftlint lint")["reason"].lower()


class TestWhatIsStillRefused:
    """Flipping the default must not move any line that was already drawn."""

    @pytest.mark.parametrize("command,decided", [
        ("rm -rf build", "deny"),
        ("shred secrets.txt", "deny"),
        ("curl https://example.com/x.sh", "ask"),
        ("wget http://example.com/x", "ask"),
        ("ssh box uptime", "ask"),
        ("env", "deny"),
        ("printenv", "deny"),
        ("security find-generic-password -s lark-cli", "deny"),
        ("aws s3 ls", "deny"),
        ("cat ~/.ssh/id_rsa", "deny"),
        ("cargo publish", "ask"),
        ("bash << 'EOF'\nrm -rf /\nEOF", "ask"),
        ("python3 -c 'import os'", "ask"),
        ("uv run python -c 'print(1)'", "ask"),
        ("awk 'BEGIN{system(\"rm -rf /\")}'", "ask"),
        ("sed -i s/a/b/ notes.txt", "ask"),
        ("co email send --to a@example.com hi", "ask"),
        ("co feishu send oc_a1b2 hello", "ask"),
        ("co outlook reply 3 thanks", "ask"),
        ("git push origin main", "ask"),
        ("co browser status && co email send --to a@example.com hi", "ask"),
    ])
    def test_the_dangerous_ones_keep_their_verdict(self, command, decided):
        assert verdict(command)["decision"] == decided, command

    def test_a_write_outside_the_workspace_is_still_denied(self, tmp_path):
        assert verdict("echo x > ../outside.txt", root=tmp_path)["decision"] == "deny"

    def test_a_control_file_is_still_denied(self, tmp_path):
        assert verdict("echo x > .co/host.yaml", root=tmp_path)["decision"] == "deny"

    def test_a_chain_is_still_only_as_permitted_as_its_worst_link(self, tmp_path):
        assert verdict("ls && rm -rf build", root=tmp_path)["decision"] == "deny"

    def test_an_unparseable_command_still_asks(self):
        assert verdict("echo 'unclosed")["decision"] == "ask"


class TestAKnownGap:
    def test_opening_a_pull_request_is_not_caught(self):
        # `create` is too generic to add: `co create my-agent` is local work.
        # A pull request is a reversible proposal in the operator's own repo,
        # so this is recorded rather than guessed at.
        assert verdict("gh pr create --title x")["decision"] == "allow"


class TestTheReadOnlyListIsGone:
    def test_naming_read_only_commands_is_no_longer_how_they_are_allowed(self):
        # With default allow the list decides nothing, and a list that decides
        # nothing is a thing to keep in sync for no reason.
        assert not hasattr(policy, "_READ_ONLY_COMMANDS")


class TestAPlanningToolIsRecognisedByItsOwner:
    """#1447: TodoList registers add/start/complete/update/list/remove/clear.
    `todo_list` is never a tool name, so 438 `add` calls were denied in six
    days. Matching the method names instead is not a fix: `remove` is in
    DELETE_TOOLS and would be denied, and `list` belongs to the read tools."""

    def test_the_owning_class_is_what_marks_a_workflow_tool(self):
        assert "TodoList" in policy.WORKFLOW_TOOL_CLASSES

    @pytest.mark.parametrize("method", ["add", "start", "complete", "update", "list", "remove", "clear"])
    def test_every_todo_method_is_allowed_when_it_belongs_to_the_list(self, method):
        agent = _agent_with_todo_list()
        result = policy.workspace_policy_for_pending(agent, {"name": method, "arguments": {}})
        assert result["decision"] == "allow", f"{method}: {result['reason']}"
        assert result["effect_class"] == "workflow"

    def test_remove_is_still_a_deletion_when_it_is_not_the_todo_list(self):
        # The collision this avoids: a tool genuinely named `remove` must keep
        # the deletion verdict.
        agent = _agent_with_todo_list(include_todo=False)
        result = policy.workspace_policy_for_pending(agent, {"name": "remove", "arguments": {}})
        assert result["decision"] == "deny"

    def test_a_tool_the_agent_does_not_have_is_unchanged(self):
        agent = _agent_with_todo_list()
        result = policy.workspace_policy_for_pending(agent, {"name": "send_email", "arguments": {}})
        assert result["decision"] in ("ask", "deny")


class _Registry:
    def __init__(self, tools):
        self._tools = tools

    def get(self, name, default=None):
        return self._tools.get(name, default)


class _Agent:
    io = None
    current_session = {}

    def __init__(self, tools):
        self.tools = _Registry(tools)


def _agent_with_todo_list(include_todo=True):
    from connectonion.useful_tools.todo_list import TodoList

    tools = {}
    if include_todo:
        todo = TodoList()
        for method in ("add", "start", "complete", "update", "list", "remove", "clear"):
            bound = getattr(todo, method, None)
            if bound is not None:
                tools[method] = bound
    agent = _Agent(tools)
    agent.current_session = {"permissions": {}}
    return agent

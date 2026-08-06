"""An agent with the write tool can rewrite the whitelist it is judged by.

`load_config_permissions()` reads `.co/host.yaml` into `session['permissions']`,
and nothing treats that file as different from any other. With `write` allowed
— the configuration any coding agent has — the agent may write it:

    perms = {'write': {'allowed': True}, 'edit': {'allowed': True}}

    write  notes.md               -> (True, 'allowed')
    write  .co/host.yaml          -> (True, 'allowed')     <- its own whitelist
    write  .co/schedule.yaml      -> (True, 'allowed')
    edit   .co/host.yaml          -> (True, 'allowed')

So a prompt-injected turn writes itself `Bash(*)` and every later turn — and
every later session — is unrestricted. The gate is real, and the thing it gates
decides its own rules.

This is not "the agent can already run bash". An operator who whitelists
`Bash(git status)` has said what they will tolerate. Editing `host.yaml` is not
one of the things they tolerated; it is the ability to change the answer,
permanently.

The line is what a file *decides*, not where it lives. These four decide what
the agent may do and who may command it:

    .co/host.yaml        permissions, trust level, its own configuration
    .co/schedule.yaml    what runs unattended, including exec: (#709)
    .co/admins.txt       who may command it
    .co/keys/            who it is

Everything else under `.co/` stays writable, because agents legitimately write
there — `dashboard.html` *is* the Home page, and the dashboard skill builds it.
A blanket ban would break a feature to fix a hole.
"""

import pytest

from connectonion.useful_plugins.tool_approval.approval import is_tool_permitted


OPEN = {"write": {"allowed": True}, "edit": {"allowed": True},
        "multi_edit": {"allowed": True}}


class TestTheControlFilesAreRefused:

    @pytest.mark.parametrize("path", [
        ".co/host.yaml",
        ".co/schedule.yaml",
        ".co/admins.txt",
        ".co/keys/agent.key",
        ".co/keys/recovery.txt",
    ])
    @pytest.mark.parametrize("tool", ["write", "edit", "multi_edit"])
    def test_it_cannot_be_written(self, tool, path):
        allowed, _reason = is_tool_permitted(tool, {"file_path": path}, OPEN)

        assert allowed is False, f"{tool} was allowed to write {path}"

    def test_the_reason_says_why(self):
        _allowed, reason = is_tool_permitted("write", {"file_path": ".co/host.yaml"}, OPEN)

        assert "host.yaml" in reason or "control" in reason.lower(), reason

    @pytest.mark.parametrize("path", [
        "/abs/project/.co/host.yaml",
        "../.co/host.yaml",
        "./.co/schedule.yaml",
        ".co//host.yaml",
    ])
    def test_the_path_does_not_have_to_be_spelled_one_way(self, path):
        """A check that only matches the tidy spelling is a check with a
        published bypass."""
        allowed, _reason = is_tool_permitted("write", {"file_path": path}, OPEN)

        assert allowed is False, path


class TestContentStaysWritable:
    """Agents write here on purpose. Breaking that to close the hole would be a
    worse trade than the hole."""

    @pytest.mark.parametrize("path", [
        ".co/dashboard.html",
        ".co/logs/agent.log",
        ".co/docs/notes.md",
        ".co/skills/mine/SKILL.md",
        "notes.md",
        "src/main.py",
    ])
    def test_it_is_still_allowed(self, path):
        allowed, _reason = is_tool_permitted("write", {"file_path": path}, OPEN)

        assert allowed is True, f"{path} should still be writable"

    def test_a_file_merely_named_like_one_is_fine(self):
        """`host.yaml` in the project root is not the agent's configuration."""
        allowed, _reason = is_tool_permitted("write", {"file_path": "host.yaml"}, OPEN)

        assert allowed is True


class TestNothingElseChanges:

    def test_no_permissions_still_refuses_everything(self):
        allowed, reason = is_tool_permitted("write", {"file_path": "notes.md"}, {})

        assert allowed is False
        assert "no permissions" in reason

    def test_bash_is_still_checked_per_subcommand(self):
        perms = {"Bash(git status)": {"allowed": True}}

        assert is_tool_permitted("bash", {"command": "git status"}, perms)[0] is True
        assert is_tool_permitted("bash", {"command": "git status && rm -rf /"}, perms)[0] is False

    def test_bash_cannot_write_a_control_file_either(self):
        """The same decision, reached with a different tool."""
        perms = {"Bash(*)": {"allowed": True}}

        allowed, _reason = is_tool_permitted(
            "bash", {"command": "echo 'permissions: {}' > .co/host.yaml"}, perms)

        assert allowed is False


class TestWhatTheBashCheckDoesNotCover:
    """Written down because a partial guard mistaken for a boundary is worse
    than no guard.

    The file-tool check is complete: the path is an argument, so it can be
    normalised and compared. Bash takes a string to be interpreted later, and a
    word-shaped check cannot follow it.
    """

    def test_a_literal_path_is_caught(self):
        perms = {"Bash(*)": {"allowed": True}}

        allowed, reason = is_tool_permitted(
            "bash", {"command": "echo x > .co/host.yaml"}, perms)

        assert allowed is False
        assert "decides what this agent may do" in reason

    def test_changing_directory_first_is_not(self):
        """The known bypass. Reaching it would mean interpreting the shell.

        What bounds bash is the operator's whitelist: this only gets through
        because the operator granted the subcommands it uses. `Bash(*)` has
        already granted everything, and this check does not take it back.
        """
        perms = {"Bash(cd *)": {"allowed": True}, "Bash(echo *)": {"allowed": True}}

        allowed, _reason = is_tool_permitted(
            "bash", {"command": "cd .co && echo x > host.yaml"}, perms)

        assert allowed is True, (
            "if this now fails, the bash check learned to follow a cd — update "
            "the note in approval.py, it is no longer only a speed bump"
        )

    def test_the_narrow_whitelist_is_what_actually_holds(self):
        """An operator who whitelisted one command has not granted the others,
        and that is the real boundary."""
        perms = {"Bash(git status)": {"allowed": True}}

        allowed, _reason = is_tool_permitted(
            "bash", {"command": "cd .co && echo x > host.yaml"}, perms)

        assert allowed is False

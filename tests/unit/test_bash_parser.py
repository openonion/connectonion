"""Unit tests for connectonion/useful_plugins/tool_approval/bash_parser.py"""

import pytest

from connectonion.useful_plugins.tool_approval.bash_parser import (
    _extract_subcommands,
    check_bash_chain_permitted,
    extract_commands_from_bash,
)


# ---------- extract_commands_from_bash ----------

def test_single_command_no_args():
    assert extract_commands_from_bash("ls") == ["ls"]


def test_single_command_with_args():
    assert extract_commands_from_bash("ls -la /tmp") == ["ls"]


def test_and_chain():
    assert extract_commands_from_bash("pwd && ls -F") == ["pwd", "ls"]


def test_or_chain():
    assert extract_commands_from_bash("test -f x || echo missing") == ["test", "echo"]


def test_pipe_chain():
    assert extract_commands_from_bash("cat file | grep test") == ["cat", "grep"]


def test_semicolon_chain():
    assert extract_commands_from_bash("cd /tmp; ls") == ["cd", "ls"]


def test_command_substitution_extracted():
    assert extract_commands_from_bash("echo $(date)") == ["echo", "date"]


def test_backtick_substitution_extracted():
    assert extract_commands_from_bash("echo `whoami`") == ["echo", "whoami"]


def test_nested_substitution_extracted():
    cmds = extract_commands_from_bash("echo $(echo $(date))")
    assert "echo" in cmds and "date" in cmds


def test_substitution_chain_safety_rejects_unauthorized_inner_command():
    """Security regression: `echo $(rm -rf /tmp)` must NOT be approved if rm not allowed."""
    # Only "echo *" is allowed; rm inside $() must trigger rejection.
    perms = _allow("Bash(echo *)")
    ok, _, _ = check_bash_chain_permitted("echo $(rm -rf /tmp)", perms)
    assert ok is False


def test_backtick_chain_safety_rejects_unauthorized_inner_command():
    perms = _allow("Bash(echo *)")
    ok, _, _ = check_bash_chain_permitted("echo `rm -rf /tmp`", perms)
    assert ok is False


def test_three_part_chain():
    assert extract_commands_from_bash("pwd && ls && echo done") == ["pwd", "ls", "echo"]


# ---------- _extract_subcommands (full text per subcommand) ----------

def test_subcommands_keep_args():
    assert _extract_subcommands("pwd && ls -F") == [("pwd", "pwd"), ("ls", "ls -F")]


def test_subcommands_single_with_args():
    assert _extract_subcommands("git status") == [("git", "git status")]


def test_subcommands_pipe_with_args():
    assert _extract_subcommands("cat f | grep foo") == [("cat", "cat f"), ("grep", "grep foo")]


# ---------- check_bash_chain_permitted ----------

def _allow(pattern, source='config', when=None):
    """Build a single permission entry."""
    perm = {'allowed': True, 'source': source}
    if when:
        perm['when'] = when
    return {pattern: perm}


def test_single_command_permitted():
    perms = _allow("Bash(pwd)")
    ok, reason, source = check_bash_chain_permitted("pwd", perms)
    assert ok is True
    assert reason == "permitted"
    assert source == "config"


def test_single_command_unpermitted():
    perms = _allow("Bash(pwd)")
    ok, reason, source = check_bash_chain_permitted("ls", perms)
    assert ok is False
    assert reason is None
    assert source is None


def test_chain_all_permitted():
    perms = {**_allow("Bash(pwd)"), **_allow("Bash(ls *)")}
    ok, reason, _ = check_bash_chain_permitted("pwd && ls -F", perms)
    assert ok is True
    assert "safe chain" in reason
    assert "2 commands" in reason


def test_chain_with_one_unpermitted_command_rejected():
    # Only pwd allowed, but chain includes rm
    perms = _allow("Bash(pwd)")
    ok, _, _ = check_bash_chain_permitted("pwd && rm -rf /tmp/x", perms)
    assert ok is False


def test_wildcard_pattern_matches_args():
    """`ls *` should match `ls -la /tmp`."""
    perms = _allow("Bash(ls *)")
    ok, _, _ = check_bash_chain_permitted("ls -la /tmp", perms)
    assert ok is True


def test_wildcard_pattern_matches_bare_command():
    """`ls *` with zero args should still match bare `ls`."""
    perms = _allow("Bash(ls *)")
    ok, _, _ = check_bash_chain_permitted("ls", perms)
    assert ok is True


def test_when_field_blocks_mismatched_command():
    """Pattern matches Bash, but 'when' restricts to a specific command."""
    perms = _allow("bash", when={'command': 'npm test'})
    ok, _, _ = check_bash_chain_permitted("rm -rf /", perms)
    assert ok is False


def test_when_field_allows_matching_command():
    perms = _allow("bash", when={'command': 'npm test'})
    ok, _, _ = check_bash_chain_permitted("npm test", perms)
    assert ok is True


def test_source_propagated_from_matched_permission():
    perms = _allow("Bash(git *)", source='user')
    _, _, source = check_bash_chain_permitted("git status", perms)
    assert source == "user"


def test_disallowed_permission_skipped():
    """Permission with allowed=False should NOT match even if pattern fits."""
    perms = {
        "Bash(pwd)": {'allowed': False, 'source': 'config'},
    }
    ok, _, _ = check_bash_chain_permitted("pwd", perms)
    assert ok is False

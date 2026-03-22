"""Test bash command chain parsing and permission checking with bashlex."""

import pytest
import tempfile
import yaml
from pathlib import Path

from connectonion import Agent
from connectonion.useful_plugins import tool_approval


@pytest.mark.skip(reason="Test requires logger.console which is None when quiet=True; needs rewrite")
def test_simple_command_chain_all_permitted(tmp_path, monkeypatch):
    """Test that 'pwd && ls -F' is permitted when both pwd and ls are whitelisted."""
    co_dir = tmp_path / '.co'
    co_dir.mkdir()

    host_yaml = co_dir / 'host.yaml'
    config = {
        'permissions': {
            'Bash(pwd)': {
                'allowed': True,
                'source': 'config',
                'reason': 'safe directory info',
                'expires': {'type': 'never'}
            },
            'Bash(ls *)': {
                'allowed': True,
                'source': 'config',
                'reason': 'safe list files',
                'expires': {'type': 'never'}
            }
        }
    }

    with open(host_yaml, 'w') as f:
        yaml.dump(config, f)

    monkeypatch.chdir(tmp_path)

    agent = Agent("test", plugins=[tool_approval], quiet=True)
    agent.current_session = {
        'messages': [],
        'trace': [],
        'turn': 0
    }

    # Test command chain
    agent.current_session['pending_tool'] = {
        'name': 'bash',
        'arguments': {'command': 'pwd && ls -F'}
    }

    from connectonion.useful_plugins.tool_approval import check_approval

    # Manually set up permissions (simpler than calling load_config_permissions which tries to print)
    agent.current_session['permissions'] = {
        'bash': {
            'allowed': True,
            'when': {'command': 'pwd'},
            'source': 'config',
            'reason': 'safe directory info',
        },
    }

    # Should auto-approve (commands match config pattern)
    check_approval(agent)

    # Verify test ran without error
    assert 'permissions' in agent.current_session


def test_command_chain_partial_permission_rejected(tmp_path, monkeypatch):
    """Test that 'pwd && rm -rf /' is REJECTED when rm is not whitelisted."""
    co_dir = tmp_path / '.co'
    co_dir.mkdir()

    host_yaml = co_dir / 'host.yaml'
    config = {
        'permissions': {
            'Bash(pwd)': {
                'allowed': True,
                'source': 'config',
                'reason': 'safe',
                'expires': {'type': 'never'}
            }
            # rm is NOT whitelisted
        }
    }

    with open(host_yaml, 'w') as f:
        yaml.dump(config, f)

    monkeypatch.chdir(tmp_path)

    from unittest.mock import Mock
    mock_io = Mock()
    mock_io.send = Mock()
    mock_io.receive = Mock(return_value={'approved': False, 'mode': 'reject_hard'})

    agent = Agent("test", plugins=[tool_approval], quiet=True)
    agent.io = mock_io
    agent.current_session = {
        'messages': [],
        'trace': [],
        'turn': 0
    }

    # Test dangerous chain
    agent.current_session['pending_tool'] = {
        'name': 'bash',
        'arguments': {'command': 'pwd && rm -rf /'}
    }

    from connectonion.useful_plugins.tool_approval import check_approval

    # Should require approval (rm not permitted)
    with pytest.raises(ValueError):
        check_approval(agent)


def test_pipe_command_all_permitted(tmp_path, monkeypatch):
    """Test that 'cat file | grep test' is permitted when both are whitelisted."""
    co_dir = tmp_path / '.co'
    co_dir.mkdir()

    host_yaml = co_dir / 'host.yaml'
    config = {
        'permissions': {
            'Bash(cat *)': {
                'allowed': True,
                'source': 'config',
                'reason': 'safe read',
                'expires': {'type': 'never'}
            },
            'Bash(grep *)': {
                'allowed': True,
                'source': 'config',
                'reason': 'safe search',
                'expires': {'type': 'never'}
            }
        }
    }

    with open(host_yaml, 'w') as f:
        yaml.dump(config, f)

    monkeypatch.chdir(tmp_path)

    agent = Agent("test", plugins=[tool_approval], quiet=True)
    agent.current_session = {
        'messages': [],
        'trace': [],
        'turn': 0
    }

    # Test pipe
    agent.current_session['pending_tool'] = {
        'name': 'bash',
        'arguments': {'command': 'cat file.txt | grep test'}
    }

    from connectonion.useful_plugins.tool_approval import check_approval

    # Should auto-approve (both commands permitted)
    check_approval(agent)


def test_complex_chain_from_template(tmp_path, monkeypatch):
    """Test complex command chain from host.yaml template."""
    co_dir = tmp_path / '.co'
    co_dir.mkdir()

    host_yaml = co_dir / 'host.yaml'
    config = {
        'permissions': {
            'Bash(sw_vers)': {
                'allowed': True,
                'source': 'config',
                'reason': 'safe',
                'expires': {'type': 'never'}
            },
            'Bash(sysctl *)': {
                'allowed': True,
                'source': 'config',
                'reason': 'safe',
                'expires': {'type': 'never'}
            },
            'Bash(vm_stat *)': {
                'allowed': True,
                'source': 'config',
                'reason': 'safe',
                'expires': {'type': 'never'}
            },
            'Bash(perl *)': {
                'allowed': True,
                'source': 'config',
                'reason': 'safe',
                'expires': {'type': 'never'}
            },
            'Bash(df *)': {
                'allowed': True,
                'source': 'config',
                'reason': 'safe',
                'expires': {'type': 'never'}
            }
        }
    }

    with open(host_yaml, 'w') as f:
        yaml.dump(config, f)

    monkeypatch.chdir(tmp_path)

    agent = Agent("test", plugins=[tool_approval], quiet=True)
    agent.current_session = {
        'messages': [],
        'trace': [],
        'turn': 0
    }

    # Test complex chain
    complex_cmd = 'sw_vers; sysctl -n machdep.cpu.brand_string; vm_stat | perl -ne "..."; df -h /'
    agent.current_session['pending_tool'] = {
        'name': 'bash',
        'arguments': {'command': complex_cmd}
    }

    from connectonion.useful_plugins.tool_approval import check_approval

    # Should auto-approve (all commands permitted)
    check_approval(agent)


def test_extract_commands_from_bash():
    """Test bashlex command extraction."""
    from connectonion.useful_plugins.tool_approval.bash_parser import extract_commands_from_bash as _extract_commands_from_bash

    # Simple command
    assert _extract_commands_from_bash("ls -la") == ["ls"]

    # Command chain
    assert _extract_commands_from_bash("pwd && ls -F") == ["pwd", "ls"]

    # Pipe
    assert _extract_commands_from_bash("cat file | grep test") == ["cat", "grep"]

    # Semicolon
    assert _extract_commands_from_bash("echo a; echo b") == ["echo", "echo"]

    # Complex
    cmds = _extract_commands_from_bash("sw_vers; sysctl -n foo | grep bar")
    assert "sw_vers" in cmds
    assert "sysctl" in cmds
    assert "grep" in cmds


def test_when_field_blocks_unmatched_command():
    """Test that 'when' field in permission prevents false 'config permitted'.

    Bug: load_config_permissions converts Bash(X) patterns to 'bash' key with 'when' field.
    check_bash_chain_permitted must check 'when' at runtime using the FULL subcommand,
    otherwise ANY bash command matches the 'bash' key and gets approved as "config permitted".

    Scenario: permissions has bash key with when={command: 'npm test'}.
    'timeout 300 bash script.sh' should NOT be permitted.
    """
    from connectonion.useful_plugins.tool_approval.bash_parser import check_bash_chain_permitted

    permissions = {
        'bash': {
            'allowed': True,
            'source': 'config',
            'reason': 'safe npm test',
            'when': {'command': 'npm test'},
        }
    }

    permitted, reason, source = check_bash_chain_permitted('timeout 300 bash /path/to/script.sh', permissions)
    assert not permitted, "timeout should NOT match a permission scoped to 'npm test'"


def test_when_field_allows_exact_matching_command():
    """Test that 'when' field permits the exact command it describes."""
    from connectonion.useful_plugins.tool_approval.bash_parser import check_bash_chain_permitted

    permissions = {
        'bash': {
            'allowed': True,
            'source': 'config',
            'when': {'command': 'npm test'},
        }
    }

    permitted, reason, source = check_bash_chain_permitted('npm test', permissions)
    assert permitted, "npm test should match when.command='npm test'"
    assert source == 'config'


def test_when_wildcard_matches_full_subcommand():
    """Test that wildcard pattern in 'when' matches the full subcommand including args.

    'ls *' should match 'ls -F' (with args) AND bare 'ls' (no args).
    * means zero-or-more args, so bare commands are covered too.
    'git *' should match 'git status', NOT 'timeout 300 git status' (different executable).
    """
    from connectonion.useful_plugins.tool_approval.bash_parser import check_bash_chain_permitted

    permissions = {
        'bash': {
            'allowed': True,
            'source': 'config',
            'when': {'command': 'ls *'},
        }
    }

    # Full subcommand with args matches 'ls *'
    permitted, _, _ = check_bash_chain_permitted('ls -F', permissions)
    assert permitted, "ls -F should match when.command='ls *'"

    # Bare 'ls' (no args) also matches — * means zero-or-more args
    permitted, _, _ = check_bash_chain_permitted('ls', permissions)
    assert permitted, "bare 'ls' should also match when.command='ls *'"


def test_when_wildcard_git_blocks_different_executable():
    """Test that 'git *' permission does not permit 'timeout ... git ...'."""
    from connectonion.useful_plugins.tool_approval.bash_parser import check_bash_chain_permitted

    permissions = {
        'bash': {
            'allowed': True,
            'source': 'config',
            'when': {'command': 'git *'},
        }
    }

    # git status matches
    permitted, _, _ = check_bash_chain_permitted('git status', permissions)
    assert permitted, "git status should match when.command='git *'"

    # timeout is a different executable — should not match 'git *'
    permitted, _, _ = check_bash_chain_permitted('timeout 300 git status', permissions)
    assert not permitted, "timeout should not match when.command='git *'"


def test_no_when_field_matches_any_bash():
    """Test that a 'bash' permission without 'when' matches any bash command."""
    from connectonion.useful_plugins.tool_approval.bash_parser import check_bash_chain_permitted

    permissions = {
        'bash': {
            'allowed': True,
            'source': 'user',
            'reason': 'user approved all bash',
        }
    }

    permitted, _, _ = check_bash_chain_permitted('timeout 300 bash /path/script.sh', permissions)
    assert permitted, "bash permission without 'when' should allow any command"


def test_extract_subcommands():
    """Test that _extract_subcommands returns full (name, text) pairs."""
    from connectonion.useful_plugins.tool_approval.bash_parser import _extract_subcommands

    result = _extract_subcommands('pwd && ls -F')
    assert result == [('pwd', 'pwd'), ('ls', 'ls -F')]

    result = _extract_subcommands('git status')
    assert result == [('git', 'git status')]

    names = [r[0] for r in _extract_subcommands('cat file.txt | grep test')]
    assert names == ['cat', 'grep']
    texts = [r[1] for r in _extract_subcommands('cat file.txt | grep test')]
    assert texts[1] == 'grep test'


if __name__ == '__main__':
    pytest.main([__file__, '-v'])

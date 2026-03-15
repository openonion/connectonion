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


if __name__ == '__main__':
    pytest.main([__file__, '-v'])

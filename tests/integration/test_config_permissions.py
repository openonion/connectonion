"""
Test config-based permissions from host.yaml.

Tests:
- Loading permissions from host.yaml
- Pattern matching (simple, bash, wildcards)
- Parameter matching with match field
- Fallback to template
- Integration with tool_approval plugin
"""

import pytest
import tempfile
import yaml
from pathlib import Path
from unittest.mock import Mock

from connectonion import Agent
from connectonion.useful_plugins import tool_approval
from connectonion.useful_plugins.tool_approval import load_config_permissions


def test_load_permissions_from_project_host_yaml(tmp_path, monkeypatch):
    """Test loading permissions from .co/host.yaml in project."""
    # Create .co/host.yaml in temp directory
    co_dir = tmp_path / '.co'
    co_dir.mkdir()

    host_yaml = co_dir / 'host.yaml'
    config = {
        'trust': 'careful',
        'port': 8000,
        'permissions': {
            'read_file': {
                'allowed': True,
                'source': 'config',
                'reason': 'safe read operation',
                'expires': {'type': 'never'}
            },
            'Bash(git status)': {
                'allowed': True,
                'source': 'config',
                'reason': 'safe git read',
                'expires': {'type': 'never'}
            }
        }
    }

    with open(host_yaml, 'w') as f:
        yaml.dump(config, f)

    # Change to temp directory
    monkeypatch.chdir(tmp_path)

    # Create agent with tool_approval plugin
    agent = Agent("test", plugins=[tool_approval], model="gpt-4o-mini")

    # Initialize session by simulating a user input (but don't actually run it)
    agent.current_session = {
        'messages': [{'role': 'user', 'content': 'test'}],
        'trace': [],
        'turn': 1
    }
    # Trigger permission loading
    load_config_permissions(agent)

    # Check that config permissions were loaded into session
    assert 'permissions' in agent.current_session
    assert 'read_file' in agent.current_session['permissions']
    # Bash() patterns converted to 'bash' with 'when' field
    assert 'bash' in agent.current_session['permissions']
    assert agent.current_session['permissions']['bash']['when'] == {'command': 'git status'}
    assert agent.current_session['permissions']['read_file']['allowed'] is True
    assert agent.current_session['permissions']['read_file']['reason'] == 'safe read operation'


def test_no_permissions_when_host_yaml_missing(tmp_path, monkeypatch):
    """Test that agent loads template permissions when .co/host.yaml doesn't exist."""
    # Change to temp directory without .co/host.yaml
    monkeypatch.chdir(tmp_path)

    # Create agent - should not crash
    agent = Agent("test", plugins=[tool_approval], model="gpt-4o-mini")

    # Initialize session
    agent.current_session = {
        'messages': [{'role': 'user', 'content': 'test'}],
        'trace': [],
        'turn': 1
    }
    # Trigger permission loading
    load_config_permissions(agent)

    # Should load from template (which has default permissions)
    assert 'permissions' in agent.current_session
    assert agent.current_session['permissions']
    # Verify bash permission exists (converted from Bash() patterns)
    assert 'bash' in agent.current_session['permissions']
    # Template has multiple Bash() patterns, last one loaded wins
    assert 'when' in agent.current_session['permissions']['bash']


def test_simple_tool_name_pattern_matching(tmp_path, monkeypatch):
    """Test simple tool name pattern matching."""
    co_dir = tmp_path / '.co'
    co_dir.mkdir()

    host_yaml = co_dir / 'host.yaml'
    config = {
        'permissions': {
            'read_file': {
                'allowed': True,
                'source': 'config',
                'reason': 'safe read',
                'expires': {'type': 'never'}
            }
        }
    }

    with open(host_yaml, 'w') as f:
        yaml.dump(config, f)

    monkeypatch.chdir(tmp_path)

    # Create agent
    agent = Agent("test", plugins=[tool_approval])

    # Initialize session
    agent.current_session = {
        'messages': [],
        'trace': [],
        'turn': 0
    }

    # Trigger permission loading
    load_config_permissions(agent)

    # Simulate tool execution
    agent.current_session['pending_tool'] = {
        'name': 'read_file',
        'arguments': {'file_path': 'test.txt'}
    }

    # Import check_approval function
    from connectonion.useful_plugins.tool_approval import check_approval

    # Should not raise (auto-approved)
    check_approval(agent)

    # Check that permissions were applied to session
    assert 'permissions' in agent.current_session
    assert 'read_file' in agent.current_session['permissions']


def test_bash_exact_command_pattern(tmp_path, monkeypatch):
    """Test exact bash command pattern matching."""
    co_dir = tmp_path / '.co'
    co_dir.mkdir()

    host_yaml = co_dir / 'host.yaml'
    config = {
        'permissions': {
            'Bash(git status)': {
                'allowed': True,
                'source': 'config',
                'reason': 'safe git read',
                'expires': {'type': 'never'}
            }
        }
    }

    with open(host_yaml, 'w') as f:
        yaml.dump(config, f)

    monkeypatch.chdir(tmp_path)

    agent = Agent("test", plugins=[tool_approval])
    agent.current_session = {
        'messages': [],
        'trace': [],
        'turn': 0
    }

    # Trigger permission loading
    load_config_permissions(agent)

    # Test exact match
    agent.current_session['pending_tool'] = {
        'name': 'bash',
        'arguments': {'command': 'git status'}
    }

    from connectonion.useful_plugins.tool_approval import check_approval

    # Should not raise
    check_approval(agent)

    # Check permissions applied - converted to 'when' format
    assert 'bash' in agent.current_session['permissions']
    assert agent.current_session['permissions']['bash']['when'] == {'command': 'git status'}


def test_bash_wildcard_pattern(tmp_path, monkeypatch):
    """Test bash wildcard pattern matching."""
    co_dir = tmp_path / '.co'
    co_dir.mkdir()

    host_yaml = co_dir / 'host.yaml'
    config = {
        'permissions': {
            'Bash(git diff *)': {
                'allowed': True,
                'source': 'config',
                'reason': 'safe git diff',
                'expires': {'type': 'never'}
            }
        }
    }

    with open(host_yaml, 'w') as f:
        yaml.dump(config, f)

    monkeypatch.chdir(tmp_path)

    agent = Agent("test", plugins=[tool_approval])
    agent.current_session = {
        'messages': [],
        'trace': [],
        'turn': 0
    }

    # Trigger permission loading
    load_config_permissions(agent)

    # Test wildcard match - should match "git diff --staged"
    agent.current_session['pending_tool'] = {
        'name': 'bash',
        'arguments': {'command': 'git diff --staged'}
    }

    from connectonion.useful_plugins.tool_approval import check_approval

    # Should not raise
    check_approval(agent)

    # Converted to 'when' format
    assert 'bash' in agent.current_session['permissions']
    assert agent.current_session['permissions']['bash']['when'] == {'command': 'git diff *'}


def test_parameter_matching_with_match_field(tmp_path, monkeypatch):
    """Test parameter matching using match field."""
    co_dir = tmp_path / '.co'
    co_dir.mkdir()

    host_yaml = co_dir / 'host.yaml'
    config = {
        'permissions': {
            'write': {
                'allowed': True,
                'source': 'config',
                'reason': 'safe doc edits',
                'when': {
                    'file_path': '*.md'
                },
                'expires': {'type': 'never'}
            }
        }
    }

    with open(host_yaml, 'w') as f:
        yaml.dump(config, f)

    monkeypatch.chdir(tmp_path)

    agent = Agent("test", plugins=[tool_approval])
    agent.current_session = {
        'messages': [],
        'trace': [],
        'turn': 0
    }

    # Trigger permission loading
    load_config_permissions(agent)

    # Test match - should auto-approve write to .md file
    agent.current_session['pending_tool'] = {
        'name': 'write',
        'arguments': {'file_path': 'README.md', 'content': 'test'}
    }

    from connectonion.useful_plugins.tool_approval import check_approval

    # Should not raise (auto-approved)
    check_approval(agent)

    assert 'write' in agent.current_session['permissions']


def test_parameter_matching_rejects_non_matching(tmp_path, monkeypatch):
    """Test that parameter matching rejects non-matching patterns."""
    co_dir = tmp_path / '.co'
    co_dir.mkdir()

    host_yaml = co_dir / 'host.yaml'
    config = {
        'permissions': {
            'write': {
                'allowed': True,
                'source': 'config',
                'reason': 'safe doc edits',
                'when': {
                    'file_path': '*.md'
                },
                'expires': {'type': 'never'}
            }
        }
    }

    with open(host_yaml, 'w') as f:
        yaml.dump(config, f)

    monkeypatch.chdir(tmp_path)

    # Mock IO to avoid actual approval prompt
    mock_io = Mock()
    mock_io.send = Mock()
    mock_io.receive = Mock(return_value={'approved': False, 'mode': 'reject_hard'})

    agent = Agent("test", plugins=[tool_approval])
    agent.io = mock_io
    agent.current_session = {
        'messages': [],
        'trace': [],
        'turn': 0
    }

    # Test non-matching - should NOT auto-approve write to .py file
    agent.current_session['pending_tool'] = {
        'name': 'write',
        'arguments': {'file_path': 'test.py', 'content': 'test'}
    }

    from connectonion.useful_plugins.tool_approval import check_approval

    # Should ask for approval (not auto-approved)
    with pytest.raises(ValueError):
        check_approval(agent)


def test_glob_pattern_matching_in_match_field(tmp_path, monkeypatch):
    """Test glob patterns in match field."""
    co_dir = tmp_path / '.co'
    co_dir.mkdir()

    host_yaml = co_dir / 'host.yaml'
    config = {
        'permissions': {
            'write': {
                'allowed': True,
                'source': 'config',
                'reason': 'safe doc edits',
                'when': {
                    'file_path': 'docs/**/*.md'
                },
                'expires': {'type': 'never'}
            }
        }
    }

    with open(host_yaml, 'w') as f:
        yaml.dump(config, f)

    monkeypatch.chdir(tmp_path)

    agent = Agent("test", plugins=[tool_approval])
    agent.current_session = {
        'messages': [],
        'trace': [],
        'turn': 0
    }

    # Trigger permission loading
    load_config_permissions(agent)

    # Test glob match
    agent.current_session['pending_tool'] = {
        'name': 'write',
        'arguments': {'file_path': 'docs/guide/intro.md', 'content': 'test'}
    }

    from connectonion.useful_plugins.tool_approval import check_approval

    # Should auto-approve
    check_approval(agent)

    assert 'write' in agent.current_session['permissions']


def test_priority_config_permissions_with_safe_tools(tmp_path, monkeypatch):
    """Test that config permissions work alongside safe tools."""
    co_dir = tmp_path / '.co'
    co_dir.mkdir()

    host_yaml = co_dir / 'host.yaml'
    config = {
        'permissions': {
            'Bash(git status)': {
                'allowed': True,
                'source': 'config',
                'reason': 'safe git',
                'expires': {'type': 'never'}
            }
        }
    }

    with open(host_yaml, 'w') as f:
        yaml.dump(config, f)

    monkeypatch.chdir(tmp_path)

    agent = Agent("test", plugins=[tool_approval])
    agent.current_session = {
        'messages': [],
        'trace': [],
        'turn': 0
    }

    # Trigger permission loading
    load_config_permissions(agent)

    # Test safe tool (should auto-approve from SAFE_TOOLS)
    agent.current_session['pending_tool'] = {
        'name': 'read_file',
        'arguments': {'file_path': 'test.txt'}
    }

    from connectonion.useful_plugins.tool_approval import check_approval

    check_approval(agent)

    # Should have both safe tool and config permission
    assert 'read_file' in agent.current_session['permissions']
    assert agent.current_session['permissions']['read_file']['source'] == 'safe'

    # Now test config permission
    agent.current_session['pending_tool'] = {
        'name': 'bash',
        'arguments': {'command': 'git status'}
    }

    check_approval(agent)

    # Converted to 'when' format
    assert 'bash' in agent.current_session['permissions']
    assert agent.current_session['permissions']['bash']['source'] == 'config'
    assert agent.current_session['permissions']['bash']['when'] == {'command': 'git status'}


if __name__ == '__main__':
    pytest.main([__file__, '-v'])

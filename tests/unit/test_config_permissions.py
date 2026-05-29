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
from tests.utils.mock_helpers import MockLLM


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
    agent = Agent("test", plugins=[tool_approval], llm=MockLLM())

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
    # Bash() patterns keep original key, 'when' added for runtime fnmatch check
    assert 'Bash(git status)' in agent.current_session['permissions']
    assert agent.current_session['permissions']['Bash(git status)']['when'] == {'command': 'git status'}
    assert agent.current_session['permissions']['read_file']['allowed'] is True
    assert agent.current_session['permissions']['read_file']['reason'] == 'safe read operation'


def test_no_permissions_when_host_yaml_missing(tmp_path, monkeypatch):
    """Test that agent loads template permissions when .co/host.yaml doesn't exist."""
    # Change to temp directory without .co/host.yaml
    monkeypatch.chdir(tmp_path)

    # Create agent - should not crash
    agent = Agent("test", plugins=[tool_approval], llm=MockLLM())

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
    # Template Bash() patterns keep Bash(X) as keys — multiple patterns coexist
    bash_keys = [k for k in agent.current_session['permissions'] if k.startswith('Bash(')]
    assert len(bash_keys) > 1, "Template should load multiple Bash() patterns"
    # Each Bash() key has 'when' field for runtime matching
    for key in bash_keys:
        assert 'when' in agent.current_session['permissions'][key]


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

    # Key kept as Bash(X), 'when' added for runtime matching
    assert 'Bash(git status)' in agent.current_session['permissions']
    assert agent.current_session['permissions']['Bash(git status)']['when'] == {'command': 'git status'}


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

    # Key kept as Bash(X), 'when' added for runtime matching
    assert 'Bash(git diff *)' in agent.current_session['permissions']
    assert agent.current_session['permissions']['Bash(git diff *)']['when'] == {'command': 'git diff *'}


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

    # Key kept as Bash(X), 'when' added for runtime matching
    assert 'Bash(git status)' in agent.current_session['permissions']
    assert agent.current_session['permissions']['Bash(git status)']['source'] == 'config'
    assert agent.current_session['permissions']['Bash(git status)']['when'] == {'command': 'git status'}


def _make_agent_with_permissions(tmp_path, monkeypatch, bash_patterns):
    """Helper: create agent with given Bash() patterns in host.yaml."""
    co_dir = tmp_path / '.co'
    co_dir.mkdir()
    config = {'permissions': {
        p: {'allowed': True, 'source': 'config', 'reason': 'test', 'expires': {'type': 'never'}}
        for p in bash_patterns
    }}
    (co_dir / 'host.yaml').write_text(yaml.dump(config))
    monkeypatch.chdir(tmp_path)
    agent = Agent("test", plugins=[tool_approval], quiet=True)
    agent.current_session = {'messages': [], 'trace': [], 'turn': 0}
    load_config_permissions(agent)
    return agent


def _runs_without_approval(agent, command):
    """Return True if command passes check_approval without needing io."""
    from connectonion.useful_plugins.tool_approval import check_approval
    agent.current_session['pending_tool'] = {'name': 'bash', 'arguments': {'command': command}}
    agent.io = None  # no io = CLI mode: unpermitted commands silently pass too
    # Use a flag: patch console so we can detect "config permitted" log
    granted = []
    orig = agent.logger.console.log_permission_granted if agent.logger.console else None
    if orig:
        agent.logger.console.log_permission_granted = lambda *a, **kw: granted.append(a)
    check_approval(agent)
    if orig:
        agent.logger.console.log_permission_granted = orig
    return bool(granted)


def test_ls_wildcard_permits_ls_with_args():
    """Bash(ls *) should permit 'ls -F', 'ls -la', and bare 'ls' (no args).

    Uses explicit permissions dict so template defaults don't interfere.
    The * wildcard means zero-or-more args, so bare 'ls' is also covered.
    """
    from connectonion.useful_plugins.tool_approval.bash_parser import check_bash_chain_permitted

    perms = {
        'Bash(ls *)': {
            'allowed': True, 'source': 'config',
            'when': {'command': 'ls *'},
        }
    }

    permitted, _, _ = check_bash_chain_permitted('ls -F', perms)
    assert permitted, "ls -F should be permitted by Bash(ls *)"

    permitted, _, _ = check_bash_chain_permitted('ls -la /tmp', perms)
    assert permitted, "ls -la /tmp should be permitted by Bash(ls *)"

    permitted, _, _ = check_bash_chain_permitted('ls', perms)
    assert permitted, "bare 'ls' should also be permitted by Bash(ls *)"


def test_multiple_bash_patterns_all_coexist(tmp_path, monkeypatch):
    """Multiple Bash() patterns must all be stored — no collapse onto single key."""
    agent = _make_agent_with_permissions(tmp_path, monkeypatch, [
        'Bash(ls *)', 'Bash(grep *)', 'Bash(git status)', 'Bash(git diff *)',
    ])
    perms = agent.current_session['permissions']

    # All four keys present
    assert 'Bash(ls *)' in perms
    assert 'Bash(grep *)' in perms
    assert 'Bash(git status)' in perms
    assert 'Bash(git diff *)' in perms

    from connectonion.useful_plugins.tool_approval.bash_parser import check_bash_chain_permitted

    assert check_bash_chain_permitted('ls -F', perms)[0], "ls -F permitted"
    assert check_bash_chain_permitted('grep foo bar', perms)[0], "grep permitted"
    assert check_bash_chain_permitted('git status', perms)[0], "git status permitted"
    assert check_bash_chain_permitted('git diff --staged', perms)[0], "git diff --staged permitted"
    assert not check_bash_chain_permitted('rm -rf /', perms)[0], "rm -rf / NOT permitted"
    assert not check_bash_chain_permitted('timeout 300 bash script.sh', perms)[0], "timeout NOT permitted"


def test_chain_requires_all_commands_permitted(tmp_path, monkeypatch):
    """A chain like 'ls -F && rm -rf /' is rejected if rm is not permitted."""
    agent = _make_agent_with_permissions(tmp_path, monkeypatch, ['Bash(ls *)'])
    perms = agent.current_session['permissions']

    from connectonion.useful_plugins.tool_approval.bash_parser import check_bash_chain_permitted

    # ls alone is permitted, but rm is not
    ok, _, _ = check_bash_chain_permitted('ls -F && rm -rf /', perms)
    assert not ok, "chain rejected because rm is unpermitted"

    # Both ls commands permitted
    ok, _, _ = check_bash_chain_permitted('ls -F && ls -la /tmp', perms)
    assert ok, "chain of two permitted commands should pass"


def test_exact_pattern_does_not_match_variants():
    """Bash(git status) exact match — 'git status -s' or 'git log' should not match.

    Uses explicit permissions dict so template defaults don't interfere.
    """
    from connectonion.useful_plugins.tool_approval.bash_parser import check_bash_chain_permitted

    perms = {
        'Bash(git status)': {
            'allowed': True, 'source': 'config',
            'when': {'command': 'git status'},
        }
    }

    assert check_bash_chain_permitted('git status', perms)[0], "exact match permitted"
    assert not check_bash_chain_permitted('git status -s', perms)[0], "git status -s not permitted by exact pattern"
    assert not check_bash_chain_permitted('git log', perms)[0], "git log not permitted"


def test_wildcard_git_diff_star():
    """Bash(git diff *) matches 'git diff --staged', 'git diff HEAD', but not 'git status'.

    Uses explicit permissions dict (not load_config_permissions) so the template's
    Bash(git status) doesn't interfere with what we're testing.
    """
    from connectonion.useful_plugins.tool_approval.bash_parser import check_bash_chain_permitted

    perms = {
        'Bash(git diff *)': {
            'allowed': True, 'source': 'config',
            'when': {'command': 'git diff *'},
        }
    }

    assert check_bash_chain_permitted('git diff --staged', perms)[0]
    assert check_bash_chain_permitted('git diff HEAD', perms)[0]
    assert not check_bash_chain_permitted('git status', perms)[0], "git status must not match git diff *"
    assert not check_bash_chain_permitted('git log', perms)[0]


if __name__ == '__main__':
    pytest.main([__file__, '-v'])

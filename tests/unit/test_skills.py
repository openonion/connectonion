"""Unit tests for connectonion/useful_plugins/skills.py

Tests cover:
- Skill discovery and loading
- Permission granting with snapshot/restore
- Pattern matching
- Integration with tool_approval
- Cleanup on turn end
"""

import pytest
import importlib
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path
from copy import deepcopy

# Import the module
skills_module = importlib.import_module('connectonion.useful_plugins.skills')
_grant_skill_permissions = skills_module._grant_skill_permissions
_restore_permissions = skills_module._restore_permissions
matches_permission_pattern = skills_module.matches_permission_pattern
handle_skill_invocation = skills_module.handle_skill_invocation
cleanup_scope = skills_module.cleanup_scope
skills = skills_module.skills


class FakeAgent:
    """Fake agent for testing plugins."""

    def __init__(self):
        self.current_session = {
            'messages': [],
            'trace': [],
            'turn': 5,
            'permissions': {}
        }
        self.logger = Mock()


class TestPermissionGranting:
    """Tests for permission granting with snapshot/restore."""

    def test_grant_skill_permissions_takes_snapshot(self):
        """Test that granting permissions takes a snapshot first."""
        agent = FakeAgent()
        agent.current_session['permissions'] = {
            'bash:pytest': {
                'allowed': True,
                'source': 'user',
                'reason': 'approved for session',
                'expires': {'type': 'session_end'}
            }
        }

        _grant_skill_permissions(agent, 'commit', ['Bash(git status)', 'read_file'])

        # Snapshot should exist
        assert '_permission_snapshot' in agent.current_session
        # Snapshot should contain user approval
        assert 'bash:pytest' in agent.current_session['_permission_snapshot']
        assert agent.current_session['_permission_snapshot']['bash:pytest']['source'] == 'user'

    def test_grant_skill_permissions_adds_patterns(self):
        """Test that skill permissions are added to permissions dict."""
        agent = FakeAgent()
        agent.current_session['turn'] = 5

        _grant_skill_permissions(agent, 'commit', ['Bash(git status)', 'Bash(git diff *)', 'read_file'])

        # Skill permissions should be added
        assert 'Bash(git status)' in agent.current_session['permissions']
        assert 'Bash(git diff *)' in agent.current_session['permissions']
        assert 'read_file' in agent.current_session['permissions']

        # Check permission structure
        git_status_perm = agent.current_session['permissions']['Bash(git status)']
        assert git_status_perm['allowed'] == True
        assert git_status_perm['source'] == 'skill'
        assert git_status_perm['reason'] == 'commit skill (turn 5)'
        assert git_status_perm['expires'] == {'type': 'turn_end'}

    def test_grant_preserves_user_approvals(self):
        """Test that user approvals are preserved when skill grants permissions."""
        agent = FakeAgent()
        agent.current_session['permissions'] = {
            'bash:pytest': {
                'allowed': True,
                'source': 'user',
                'reason': 'approved for session',
                'expires': {'type': 'session_end'}
            }
        }

        _grant_skill_permissions(agent, 'commit', ['Bash(git status)'])

        # User approval should still be in permissions
        assert 'bash:pytest' in agent.current_session['permissions']
        # Skill permission should also be there
        assert 'Bash(git status)' in agent.current_session['permissions']

    def test_restore_permissions_restores_snapshot(self):
        """Test that restore removes skill permissions and keeps user approvals."""
        agent = FakeAgent()
        # Setup: user approval exists
        agent.current_session['permissions'] = {
            'bash:pytest': {
                'allowed': True,
                'source': 'user',
                'reason': 'approved for session',
                'expires': {'type': 'session_end'}
            }
        }
        agent.current_session['_permission_snapshot'] = deepcopy(agent.current_session['permissions'])

        # Add skill permission
        agent.current_session['permissions']['Bash(git status)'] = {
            'allowed': True,
            'source': 'skill',
            'reason': 'commit skill (turn 5)',
            'expires': {'type': 'turn_end'}
        }

        # Restore
        _restore_permissions(agent)

        # User approval should remain
        assert 'bash:pytest' in agent.current_session['permissions']
        # Skill permission should be gone
        assert 'Bash(git status)' not in agent.current_session['permissions']
        # Snapshot should be removed
        assert '_permission_snapshot' not in agent.current_session


class TestPatternMatching:
    """Tests for pattern matching logic."""

    def test_exact_tool_name_match(self):
        """Test exact tool name matching."""
        assert matches_permission_pattern('read_file', {}, ['read_file']) == True
        assert matches_permission_pattern('read_file', {}, ['write']) == False

    def test_exact_bash_command_match(self):
        """Test exact bash command matching."""
        assert matches_permission_pattern(
            'bash',
            {'command': 'git status'},
            ['Bash(git status)']
        ) == True

        assert matches_permission_pattern(
            'bash',
            {'command': 'git diff'},
            ['Bash(git status)']
        ) == False

    def test_bash_wildcard_match(self):
        """Test bash command wildcard matching."""
        # "git diff *" should match "git diff --staged"
        assert matches_permission_pattern(
            'bash',
            {'command': 'git diff --staged'},
            ['Bash(git diff *)']
        ) == True

        # "git diff *" should match "git diff HEAD"
        assert matches_permission_pattern(
            'bash',
            {'command': 'git diff HEAD'},
            ['Bash(git diff *)']
        ) == True

        # "git diff *" should NOT match "git status"
        assert matches_permission_pattern(
            'bash',
            {'command': 'git status'},
            ['Bash(git diff *)']
        ) == False

    def test_bash_command_prefix_wildcard(self):
        """Test bash command prefix wildcard (git *)."""
        # "git *" should match any git command
        assert matches_permission_pattern(
            'bash',
            {'command': 'git status'},
            ['Bash(git *)']
        ) == True

        assert matches_permission_pattern(
            'bash',
            {'command': 'git diff --staged'},
            ['Bash(git *)']
        ) == True

        assert matches_permission_pattern(
            'bash',
            {'command': 'git commit -m "msg"'},
            ['Bash(git *)']
        ) == True

        # "git *" should NOT match non-git commands
        assert matches_permission_pattern(
            'bash',
            {'command': 'pytest'},
            ['Bash(git *)']
        ) == False

    def test_multiple_patterns(self):
        """Test matching against multiple patterns."""
        patterns = ['read_file', 'Bash(git status)', 'Bash(git diff *)']

        assert matches_permission_pattern('read_file', {}, patterns) == True
        assert matches_permission_pattern('bash', {'command': 'git status'}, patterns) == True
        assert matches_permission_pattern('bash', {'command': 'git diff HEAD'}, patterns) == True
        assert matches_permission_pattern('bash', {'command': 'pytest'}, patterns) == False


class TestSkillInvocation:
    """Tests for skill invocation via /command."""

    @patch.object(skills_module, '_load_skill')
    def test_handle_skill_invocation_detects_slash_command(self, mock_load):
        """Test that /command is detected and skill is loaded."""
        agent = FakeAgent()
        agent.current_session['messages'] = [
            {'role': 'user', 'content': '/commit'}
        ]

        mock_load.return_value = {
            'frontmatter': {
                'tools': ['Bash(git status)', 'read_file']
            },
            'instructions': 'Create a git commit'
        }

        handle_skill_invocation(agent)

        # Skill should be loaded
        mock_load.assert_called_once_with('commit')

        # Message should be replaced with instructions
        assert agent.current_session['messages'][-1]['content'] == 'Create a git commit'

        # Permissions should be granted
        assert 'Bash(git status)' in agent.current_session['permissions']
        assert 'read_file' in agent.current_session['permissions']

        # Snapshot should exist
        assert '_permission_snapshot' in agent.current_session

    @patch.object(skills_module, '_load_skill')
    def test_handle_skill_invocation_ignores_non_slash(self, mock_load):
        """Test that non-slash messages are ignored."""
        agent = FakeAgent()
        agent.current_session['messages'] = [
            {'role': 'user', 'content': 'regular message'}
        ]

        handle_skill_invocation(agent)

        # Skill should not be loaded
        mock_load.assert_not_called()

    @patch.object(skills_module, '_load_skill')
    def test_handle_skill_invocation_skill_not_found(self, mock_load):
        """Test that missing skills are handled gracefully."""
        agent = FakeAgent()
        agent.current_session['messages'] = [
            {'role': 'user', 'content': '/nonexistent'}
        ]

        mock_load.return_value = None

        handle_skill_invocation(agent)

        # Should not crash, just return
        # Message should not be replaced
        assert agent.current_session['messages'][-1]['content'] == '/nonexistent'


class TestCleanup:
    """Tests for cleanup on turn end."""

    def test_cleanup_scope_restores_permissions(self):
        """Test that cleanup_scope restores permissions."""
        agent = FakeAgent()
        agent.current_session['permissions'] = {
            'bash:pytest': {'source': 'user'},
            'Bash(git status)': {'source': 'skill'}
        }
        agent.current_session['_permission_snapshot'] = {
            'bash:pytest': {'source': 'user'}
        }

        cleanup_scope(agent)

        # Snapshot should be restored
        assert 'bash:pytest' in agent.current_session['permissions']
        assert 'Bash(git status)' not in agent.current_session['permissions']
        assert '_permission_snapshot' not in agent.current_session

    def test_cleanup_scope_no_snapshot(self):
        """Test that cleanup handles missing snapshot gracefully."""
        agent = FakeAgent()
        agent.current_session['permissions'] = {
            'bash:pytest': {'source': 'user'}
        }

        # No snapshot
        cleanup_scope(agent)

        # Should not crash
        # Permissions should remain unchanged
        assert 'bash:pytest' in agent.current_session['permissions']


class TestPluginStructure:
    """Tests for plugin structure."""

    def test_skills_plugin_has_correct_handlers(self):
        """Test that skills plugin exports correct event handlers."""
        assert isinstance(skills, list)
        assert len(skills) == 2

        # Should have after_user_input and on_complete handlers
        handler_names = [h.__name__ for h in skills]
        assert 'handle_skill_invocation' in handler_names
        assert 'cleanup_scope' in handler_names


class TestIntegrationScenarios:
    """Tests for complete integration scenarios."""

    @patch.object(skills_module, '_load_skill')
    def test_full_skill_lifecycle(self, mock_load):
        """Test complete skill lifecycle: grant → execute → restore."""
        agent = FakeAgent()
        agent.current_session['turn'] = 5

        # User has existing approval
        agent.current_session['permissions'] = {
            'bash:pytest': {
                'allowed': True,
                'source': 'user',
                'reason': 'approved for session',
                'expires': {'type': 'session_end'}
            }
        }

        # User invokes /commit
        agent.current_session['messages'] = [
            {'role': 'user', 'content': '/commit'}
        ]

        mock_load.return_value = {
            'frontmatter': {
                'tools': ['Bash(git status)', 'Bash(git diff *)']
            },
            'instructions': 'Create commit'
        }

        # Invoke skill
        handle_skill_invocation(agent)

        # During turn 5: both user and skill permissions should exist
        assert 'bash:pytest' in agent.current_session['permissions']
        assert 'Bash(git status)' in agent.current_session['permissions']
        assert 'Bash(git diff *)' in agent.current_session['permissions']

        # User approval should have correct metadata
        assert agent.current_session['permissions']['bash:pytest']['source'] == 'user'

        # Skill permissions should have correct metadata
        assert agent.current_session['permissions']['Bash(git status)']['source'] == 'skill'
        assert 'turn 5' in agent.current_session['permissions']['Bash(git status)']['reason']

        # Turn ends
        cleanup_scope(agent)

        # After turn: only user approval remains
        assert 'bash:pytest' in agent.current_session['permissions']
        assert 'Bash(git status)' not in agent.current_session['permissions']
        assert 'Bash(git diff *)' not in agent.current_session['permissions']

    def test_snapshot_restore_preserves_multiple_user_approvals(self):
        """Test that snapshot/restore preserves multiple user approvals."""
        agent = FakeAgent()

        # User has multiple approvals
        agent.current_session['permissions'] = {
            'bash:pytest': {'source': 'user', 'expires': {'type': 'session_end'}},
            'bash:npm': {'source': 'user', 'expires': {'type': 'session_end'}},
            'write': {'source': 'user', 'expires': {'type': 'session_end'}}
        }

        # Grant skill permissions
        _grant_skill_permissions(agent, 'commit', ['Bash(git status)'])

        # All approvals should exist during skill
        assert len(agent.current_session['permissions']) == 4

        # Restore
        _restore_permissions(agent)

        # All user approvals should be preserved
        assert 'bash:pytest' in agent.current_session['permissions']
        assert 'bash:npm' in agent.current_session['permissions']
        assert 'write' in agent.current_session['permissions']
        # Skill permission should be gone
        assert 'Bash(git status)' not in agent.current_session['permissions']

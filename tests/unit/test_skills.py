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

# Import the modules
skills_module = importlib.import_module('connectonion.useful_plugins.skills')
_grant_skill_permissions = skills_module._grant_skill_permissions
_restore_permissions = skills_module._restore_permissions
handle_skill_invocation = skills_module.handle_skill_invocation
cleanup_scope = skills_module.cleanup_scope
skills = skills_module.skills

# Import pattern matching from tool_approval
approval_module = importlib.import_module('connectonion.useful_plugins.tool_approval.approval')
matches_permission_pattern = approval_module.matches_permission_pattern


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
            'write': {
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
        assert 'write' in agent.current_session['_permission_snapshot']
        assert agent.current_session['_permission_snapshot']['write']['source'] == 'user'

    def test_grant_skill_permissions_adds_patterns(self):
        """Test that skill permissions are added to permissions dict."""
        agent = FakeAgent()
        agent.current_session['turn'] = 5

        _grant_skill_permissions(agent, 'commit', ['Bash(git status)', 'Bash(git diff *)', 'read_file'])

        # Skill permissions should be added (unified format: bash patterns→'bash' key)
        assert 'bash' in agent.current_session['permissions']
        assert 'read_file' in agent.current_session['permissions']

        # Check permission structure (unified format has 'when' field)
        bash_perm = agent.current_session['permissions']['bash']
        assert bash_perm['allowed'] == True
        assert bash_perm['source'] == 'skill'
        assert bash_perm['reason'] == 'commit skill (turn 5)'
        assert bash_perm['expires'] == {'type': 'turn_end'}

    def test_grant_preserves_user_approvals(self):
        """Test that user approvals are preserved when skill grants permissions."""
        agent = FakeAgent()
        agent.current_session['permissions'] = {
            'write': {
                'allowed': True,
                'source': 'user',
                'reason': 'approved for session',
                'expires': {'type': 'session_end'}
            }
        }

        _grant_skill_permissions(agent, 'commit', ['Bash(git status)'])

        # User approval for different tool should still be in permissions
        assert 'write' in agent.current_session['permissions']
        assert agent.current_session['permissions']['write']['source'] == 'user'
        # Skill permission should also be there (unified format: key='bash')
        assert 'bash' in agent.current_session['permissions']
        assert agent.current_session['permissions']['bash']['source'] == 'skill'

    def test_restore_permissions_restores_snapshot(self):
        """Test that restore removes skill permissions and keeps user approvals."""
        agent = FakeAgent()
        # Setup: user approval exists
        agent.current_session['permissions'] = {
            'write': {
                'allowed': True,
                'source': 'user',
                'reason': 'approved for session',
                'expires': {'type': 'session_end'}
            }
        }
        agent.current_session['_permission_snapshot'] = deepcopy(agent.current_session['permissions'])

        # Add skill permission (unified format)
        agent.current_session['permissions']['bash'] = {
            'allowed': True,
            'source': 'skill',
            'reason': 'commit skill (turn 5)',
            'when': {'command': 'git status'},
            'expires': {'type': 'turn_end'}
        }

        # Restore
        _restore_permissions(agent)

        # User approval should remain
        assert 'write' in agent.current_session['permissions']
        assert agent.current_session['permissions']['write']['source'] == 'user'
        # Skill permission should be gone
        assert 'bash' not in agent.current_session['permissions']
        # Snapshot should be removed
        assert '_permission_snapshot' not in agent.current_session


class TestPatternMatching:
    """Tests for pattern matching logic."""

    def test_exact_tool_name_match(self):
        """Test exact tool name matching."""
        assert matches_permission_pattern('read_file', {}, 'read_file') == True
        assert matches_permission_pattern('read_file', {}, 'write') == False

    def test_exact_bash_command_match(self):
        """Test exact bash command matching."""
        assert matches_permission_pattern(
            'bash',
            {'command': 'git status'},
            'Bash(git status)'
        ) == True

        assert matches_permission_pattern(
            'bash',
            {'command': 'git diff'},
            'Bash(git status)'
        ) == False

    def test_bash_wildcard_match(self):
        """Test bash command wildcard matching."""
        # "git diff *" should match "git diff --staged"
        assert matches_permission_pattern(
            'bash',
            {'command': 'git diff --staged'},
            'Bash(git diff *)'
        ) == True

        # "git diff *" should match "git diff HEAD"
        assert matches_permission_pattern(
            'bash',
            {'command': 'git diff HEAD'},
            'Bash(git diff *)'
        ) == True

        # "git diff *" should NOT match "git status"
        assert matches_permission_pattern(
            'bash',
            {'command': 'git status'},
            'Bash(git diff *)'
        ) == False

    def test_bash_command_prefix_wildcard(self):
        """Test bash command prefix wildcard (git *)."""
        # "git *" should match any git command
        assert matches_permission_pattern(
            'bash',
            {'command': 'git status'},
            'Bash(git *)'
        ) == True

        assert matches_permission_pattern(
            'bash',
            {'command': 'git diff --staged'},
            'Bash(git *)'
        ) == True

        assert matches_permission_pattern(
            'bash',
            {'command': 'git commit -m "msg"'},
            'Bash(git *)'
        ) == True

        # "git *" should NOT match non-git commands
        assert matches_permission_pattern(
            'bash',
            {'command': 'pytest'},
            'Bash(git *)'
        ) == False

    def test_single_pattern_string(self):
        """Test that function now takes single pattern string instead of list."""
        # Simple tool name
        assert matches_permission_pattern('read_file', {}, 'read_file') == True
        assert matches_permission_pattern('write', {}, 'read_file') == False

        # Bash patterns
        assert matches_permission_pattern('bash', {'command': 'git status'}, 'Bash(git status)') == True
        assert matches_permission_pattern('bash', {'command': 'git diff HEAD'}, 'Bash(git diff *)') == True
        assert matches_permission_pattern('bash', {'command': 'pytest'}, 'Bash(git *)') == False


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

        # Permissions should be granted (unified format)
        assert 'bash' in agent.current_session['permissions']
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
            'write': {'source': 'user'},
            'bash': {'source': 'skill', 'when': {'command': 'git status'}}
        }
        agent.current_session['_permission_snapshot'] = {
            'write': {'source': 'user'}
        }

        cleanup_scope(agent)

        # Snapshot should be restored
        assert 'write' in agent.current_session['permissions']
        assert 'bash' not in agent.current_session['permissions']
        assert '_permission_snapshot' not in agent.current_session

    def test_cleanup_scope_no_snapshot(self):
        """Test that cleanup handles missing snapshot gracefully."""
        agent = FakeAgent()
        agent.current_session['permissions'] = {
            'write': {'source': 'user'}
        }

        # No snapshot
        cleanup_scope(agent)

        # Should not crash
        # Permissions should remain unchanged
        assert 'write' in agent.current_session['permissions']


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
            'write': {
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
        assert 'write' in agent.current_session['permissions']
        # Skill permissions use unified format (key='bash')
        assert 'bash' in agent.current_session['permissions']

        # User approval should have correct metadata
        assert agent.current_session['permissions']['write']['source'] == 'user'

        # Skill permissions should have correct metadata (unified format)
        assert agent.current_session['permissions']['bash']['source'] == 'skill'
        assert 'turn 5' in agent.current_session['permissions']['bash']['reason']

        # Turn ends
        cleanup_scope(agent)

        # After turn: only user approval remains
        assert 'write' in agent.current_session['permissions']
        # Skill permission gone
        bash_perm = agent.current_session['permissions'].get('bash', {})
        assert bash_perm.get('source') != 'skill'

    def test_snapshot_restore_preserves_multiple_user_approvals(self):
        """Test that snapshot/restore preserves multiple user approvals."""
        agent = FakeAgent()

        # User has multiple approvals (different tools)
        agent.current_session['permissions'] = {
            'bash': {'source': 'user', 'expires': {'type': 'session_end'}},
            'write': {'source': 'user', 'expires': {'type': 'session_end'}},
            'edit': {'source': 'user', 'expires': {'type': 'session_end'}}
        }

        # Grant skill permissions (will overwrite bash temporarily)
        _grant_skill_permissions(agent, 'commit', ['Bash(git status)', 'read_file'])

        # All approvals should exist during skill (bash overwritten, +read_file added)
        assert len(agent.current_session['permissions']) == 4

        # Restore
        _restore_permissions(agent)

        # All user approvals should be preserved
        assert 'bash' in agent.current_session['permissions']
        assert agent.current_session['permissions']['bash']['source'] == 'user'
        assert 'write' in agent.current_session['permissions']
        assert 'edit' in agent.current_session['permissions']
        # Skill permission should be gone
        assert 'read_file' not in agent.current_session['permissions']

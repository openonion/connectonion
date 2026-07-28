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

        # Skill permissions should be added (each Bash pattern as separate key)
        assert 'Bash(git status)' in agent.current_session['permissions']
        assert 'Bash(git diff *)' in agent.current_session['permissions']
        assert 'read_file' in agent.current_session['permissions']

        # Check permission structure (has 'when' field for bash patterns)
        bash_perm = agent.current_session['permissions']['Bash(git status)']
        assert bash_perm['allowed'] == True
        assert bash_perm['source'] == 'skill'
        assert bash_perm['reason'] == 'commit skill (turn 5)'
        assert bash_perm['when'] == {'command': 'git status'}
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
        # Skill permission should also be there (key='Bash(git status)')
        assert 'Bash(git status)' in agent.current_session['permissions']
        assert agent.current_session['permissions']['Bash(git status)']['source'] == 'skill'

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

        # Add skill permission
        agent.current_session['permissions']['Bash(git status)'] = {
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
        assert 'Bash(git status)' not in agent.current_session['permissions']
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

        # Permissions should be granted (each Bash pattern as separate key)
        assert 'Bash(git status)' in agent.current_session['permissions']
        assert 'read_file' in agent.current_session['permissions']

        # Snapshot should exist
        assert '_permission_snapshot' in agent.current_session

    @patch.object(skills_module, '_load_skill')
    def test_handle_skill_invocation_preserves_slash_arguments(self, mock_load):
        """Test that /command arguments are appended to skill instructions."""
        agent = FakeAgent()
        agent.current_session['messages'] = [
            {'role': 'user', 'content': '/linkedin-comment-writer Post: Hello world'}
        ]

        mock_load.return_value = {
            'frontmatter': {},
            'instructions': 'Write a LinkedIn comment'
        }

        handle_skill_invocation(agent)

        assert agent.current_session['messages'][-1]['content'] == (
            'Write a LinkedIn comment\n\n---\n## Arguments\nPost: Hello world'
        )

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

    def test_claude_project_skill_composes_with_yolo(self, tmp_path, monkeypatch):
        """co ai --yolo can invoke a project skill from .claude/skills."""
        from connectonion.useful_plugins.ulw import enable_yolo, yolo

        skill_dir = tmp_path / ".claude" / "skills" / "deploy-oo-chat"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(
            "---\n"
            "name: deploy-oo-chat\n"
            "description: Deploy oo-chat\n"
            "---\n\n"
            "Run the production release workflow.",
            encoding="utf-8",
        )
        monkeypatch.chdir(tmp_path)

        agent = FakeAgent()
        agent.io = None
        agent.current_session['messages'] = [
            {'role': 'user', 'content': '/deploy-oo-chat'}
        ]

        handle_skill_invocation(agent)
        enable_yolo(agent, turns=7)

        assert agent.current_session['messages'][-1]['content'] == (
            "Run the production release workflow."
        )
        assert agent.current_session['mode'] == 'ulw'
        assert agent.current_session['ulw_turns'] == 7

    def test_real_agent_runs_claude_skill_and_bypasses_first_approval_in_yolo(
        self, tmp_path, monkeypatch
    ):
        """The real plugin order loads /skill before YOLO's first tool call."""
        from connectonion import Agent
        from connectonion.core.llm import LLMResponse, ToolCall
        from connectonion.core.usage import TokenUsage
        from connectonion.useful_plugins import tool_approval, yolo
        from connectonion.useful_plugins.ulw import enable_yolo
        from tests.utils.mock_helpers import MockLLM

        skill_dir = tmp_path / ".claude" / "skills" / "deploy-oo-chat"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(
            "---\n"
            "name: deploy-oo-chat\n"
            "description: Deploy oo-chat\n"
            "---\n\n"
            "Run the production release workflow.",
            encoding="utf-8",
        )
        monkeypatch.chdir(tmp_path)
        executed = []

        def bash(command: str) -> str:
            """Record a harmless stand-in for a dangerous shell call."""
            executed.append(command)
            return "ok"

        class CheckpointIO:
            def __init__(self):
                self.sent = []

            def receive_all(self, msg_type=None):
                return []

            def send(self, event):
                self.sent.append(event)

            def receive(self):
                assert self.sent[-1]['type'] == 'ulw_turns_reached'
                return {'action': 'stop'}

        llm = MockLLM(responses=[
            LLMResponse(
                content="",
                tool_calls=[ToolCall(
                    name="bash",
                    arguments={"command": "printf safe"},
                    id="shell-1",
                )],
                raw_response={},
                usage=TokenUsage(),
            ),
            LLMResponse(
                content="deployed",
                tool_calls=[],
                raw_response={},
                usage=TokenUsage(),
            ),
        ])
        agent = Agent(
            "skill-yolo",
            llm=llm,
            tools=[bash],
            plugins=[skills, tool_approval, yolo],
            log=False,
            quiet=True,
        )
        agent.io = CheckpointIO()
        # main's `yolo` plugin list only wires the handlers; enable_yolo arms it.
        enable_yolo(agent, turns=1)

        result = agent.input("/deploy-oo-chat")

        assert result == "deployed"
        assert executed == ["printf safe"]
        assert llm.calls[0]["messages"][1]["content"] == (
            "Run the production release workflow."
        )
        assert not any(event.get('type') == 'approval_needed' for event in agent.io.sent)


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
        assert len(skills) == 3

        # Should have setup, after_user_input and on_complete handlers
        handler_names = [h.__name__ for h in skills]
        assert 'setup_skills' in handler_names
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
        # Skill permissions use separate keys per Bash pattern
        assert 'Bash(git status)' in agent.current_session['permissions']
        assert 'Bash(git diff *)' in agent.current_session['permissions']

        # User approval should have correct metadata
        assert agent.current_session['permissions']['write']['source'] == 'user'

        # Skill permissions should have correct metadata
        assert agent.current_session['permissions']['Bash(git status)']['source'] == 'skill'
        assert 'turn 5' in agent.current_session['permissions']['Bash(git status)']['reason']

        # Turn ends
        cleanup_scope(agent)

        # After turn: only user approval remains
        assert 'write' in agent.current_session['permissions']
        # Skill permissions gone
        assert 'Bash(git status)' not in agent.current_session['permissions']
        assert 'Bash(git diff *)' not in agent.current_session['permissions']

    def test_snapshot_restore_preserves_multiple_user_approvals(self):
        """Test that snapshot/restore preserves multiple user approvals."""
        agent = FakeAgent()

        # User has multiple approvals (different tools)
        agent.current_session['permissions'] = {
            'bash': {'source': 'user', 'expires': {'type': 'session_end'}},
            'write': {'source': 'user', 'expires': {'type': 'session_end'}},
            'edit': {'source': 'user', 'expires': {'type': 'session_end'}}
        }

        # Grant skill permissions (adds Bash(git status) and read_file)
        _grant_skill_permissions(agent, 'commit', ['Bash(git status)', 'read_file'])

        # All approvals should exist during skill (3 user + 2 skill = 5)
        assert len(agent.current_session['permissions']) == 5

        # Restore
        _restore_permissions(agent)

        # All user approvals should be preserved
        assert 'bash' in agent.current_session['permissions']
        assert agent.current_session['permissions']['bash']['source'] == 'user'
        assert 'write' in agent.current_session['permissions']
        assert 'edit' in agent.current_session['permissions']
        # Skill permission should be gone
        assert 'read_file' not in agent.current_session['permissions']

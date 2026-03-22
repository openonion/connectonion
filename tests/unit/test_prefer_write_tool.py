"""Test prefer_write_tool plugin - block bash file creation, soft-remind for reading."""

import pytest
from connectonion import Agent
from connectonion.useful_plugins import prefer_write_tool
from connectonion.useful_plugins.prefer_write_tool import (
    _is_file_creation_command,
    _is_file_reading_command,
    block_bash_file_creation,
    remind_read_file,
)


# ── File creation detection ──────────────────────────────────────────

class TestFileCreationDetection:

    def test_heredoc(self):
        assert _is_file_creation_command("cat <<EOF > file.py")
        assert _is_file_creation_command("cat <<'EOF' > file.txt")
        assert _is_file_creation_command("cat << 'EOF' > file.sh")

    def test_echo_redirect(self):
        assert _is_file_creation_command("echo hello > file.txt")
        assert _is_file_creation_command("echo hello >> file.txt")

    def test_printf_redirect(self):
        assert _is_file_creation_command("printf 'test' > file.txt")

    def test_tee(self):
        assert _is_file_creation_command("echo hello | tee file.txt")
        assert _is_file_creation_command("ls -la | tee output.txt")

    def test_path_redirect(self):
        assert _is_file_creation_command("echo test > ./file.txt")
        assert _is_file_creation_command("echo test > ~/notes.txt")
        assert _is_file_creation_command("echo test >> ./log.txt")

    def test_not_stderr_redirect(self):
        """2>/dev/null should NOT be flagged as file creation."""
        assert not _is_file_creation_command("command 2>/dev/null")
        assert not _is_file_creation_command("ls 2>/dev/null")

    def test_safe_commands_not_flagged(self):
        assert not _is_file_creation_command("ls -la")
        assert not _is_file_creation_command("git status")
        assert not _is_file_creation_command("echo hello")
        assert not _is_file_creation_command("pwd")
        assert not _is_file_creation_command("date")
        assert not _is_file_creation_command("npm run build")
        assert not _is_file_creation_command("python script.py")


# ── File reading detection ───────────────────────────────────────────

class TestFileReadingDetection:

    def test_standalone_cat(self):
        assert _is_file_reading_command("cat file.txt")
        assert _is_file_reading_command("cat /etc/config")

    def test_cat_after_semicolon(self):
        assert _is_file_reading_command("ls && cat file.txt")
        assert _is_file_reading_command("pwd && cat notes.md")

    def test_head_tail(self):
        assert _is_file_reading_command("head file.txt")
        assert _is_file_reading_command("head -n 10 README.md")
        assert _is_file_reading_command("tail file.log")
        assert _is_file_reading_command("tail -f /var/log/app.log")

    def test_pagers(self):
        assert _is_file_reading_command("less file.txt")
        assert _is_file_reading_command("more README.md")

    def test_cat_in_pipeline_not_flagged(self):
        """cat piped to other commands is legitimate bash usage."""
        assert not _is_file_reading_command("cat file.txt | grep pattern")
        assert not _is_file_reading_command("cat data.json | jq '.key'")

    def test_cat_without_args_not_flagged(self):
        assert not _is_file_reading_command("cat")
        assert not _is_file_reading_command("ls -la")

    def test_head_in_pipeline_flagged(self):
        """head/tail after pipe are legitimate, but still detected by current patterns."""
        # These are detected because the pattern matches head/tail after pipe chars
        assert _is_file_reading_command("cat file | head -5")
        assert _is_file_reading_command("cat file | tail -5")


# ── File creation blocking (hard block) ─────────────────────────────

class TestFileCreationBlocking:

    def _make_agent(self, command):
        agent = Agent("test", plugins=[prefer_write_tool])
        agent.current_session = {
            'messages': [],
            'trace': [],
            'turn': 0,
            'pending_tool': {
                'name': 'bash',
                'arguments': {'command': command},
            },
        }
        return agent

    def test_blocks_echo_redirect(self):
        agent = self._make_agent("echo hello > file.txt")
        with pytest.raises(ValueError, match="Bash file creation blocked"):
            block_bash_file_creation(agent)

    def test_blocks_heredoc(self):
        agent = self._make_agent("cat <<EOF > file.py\nprint('hi')\nEOF")
        with pytest.raises(ValueError, match="Bash file creation blocked"):
            block_bash_file_creation(agent)

    def test_error_message_mentions_write_tool(self):
        agent = self._make_agent("echo test > file.txt")
        with pytest.raises(ValueError) as exc_info:
            block_bash_file_creation(agent)
        error_msg = str(exc_info.value)
        assert "Write" in error_msg
        assert "<system-reminder>" in error_msg

    def test_allows_safe_commands(self):
        agent = self._make_agent("git status")
        block_bash_file_creation(agent)  # Should not raise

    def test_allows_non_bash_tools(self):
        agent = Agent("test", plugins=[prefer_write_tool])
        agent.current_session = {
            'messages': [],
            'trace': [],
            'turn': 0,
            'pending_tool': {
                'name': 'read_file',
                'arguments': {'file_path': '/tmp/file.txt'},
            },
        }
        block_bash_file_creation(agent)  # Should not raise


# ── File reading soft reminder (not blocked) ─────────────────────────

class TestFileReadingSoftReminder:

    def _make_agent(self, command):
        agent = Agent("test", plugins=[prefer_write_tool])
        agent.current_session = {
            'messages': [],
            'trace': [],
            'turn': 0,
            'pending_tool': {
                'name': 'bash',
                'arguments': {'command': command},
            },
        }
        return agent

    def test_does_not_block_file_reading(self):
        """File reading should NOT raise ValueError — it's a soft reminder."""
        agent = self._make_agent("cat file.txt")
        block_bash_file_creation(agent)  # Should NOT raise

    def test_sets_reminder_flag(self):
        """File reading should set the _prefer_read_file_reminder flag."""
        agent = self._make_agent("cat config.json")
        block_bash_file_creation(agent)
        assert agent.current_session.get('_prefer_read_file_reminder') is True

    def test_does_not_set_flag_for_safe_commands(self):
        agent = self._make_agent("git status")
        block_bash_file_creation(agent)
        assert '_prefer_read_file_reminder' not in agent.current_session

    def test_remind_appends_to_tool_result(self):
        """after_each_tool handler should append reminder to last tool message."""
        agent = self._make_agent("cat file.txt")
        agent.current_session['_prefer_read_file_reminder'] = True
        agent.current_session['messages'] = [
            {'role': 'user', 'content': 'read the file'},
            {'role': 'tool', 'content': 'file contents here'},
        ]
        remind_read_file(agent)
        last_tool = agent.current_session['messages'][-1]
        assert '<system-reminder>' in last_tool['content']
        assert 'read_file' in last_tool['content']
        assert 'file contents here' in last_tool['content']

    def test_remind_clears_flag(self):
        """Flag should be cleared after reminder is appended."""
        agent = self._make_agent("cat file.txt")
        agent.current_session['_prefer_read_file_reminder'] = True
        agent.current_session['messages'] = [
            {'role': 'tool', 'content': 'output'},
        ]
        remind_read_file(agent)
        assert '_prefer_read_file_reminder' not in agent.current_session

    def test_remind_noop_without_flag(self):
        """No reminder appended if flag is not set."""
        agent = self._make_agent("git status")
        agent.current_session['messages'] = [
            {'role': 'tool', 'content': 'clean'},
        ]
        remind_read_file(agent)
        assert '<system-reminder>' not in agent.current_session['messages'][-1]['content']

    def test_head_standalone_sets_flag(self):
        agent = self._make_agent("head -n 20 README.md")
        block_bash_file_creation(agent)
        assert agent.current_session.get('_prefer_read_file_reminder') is True

    def test_tail_standalone_sets_flag(self):
        agent = self._make_agent("tail -f app.log")
        block_bash_file_creation(agent)
        assert agent.current_session.get('_prefer_read_file_reminder') is True


# ── Edge cases ───────────────────────────────────────────────────────

class TestEdgeCases:

    def test_no_pending_tool(self):
        agent = Agent("test", plugins=[prefer_write_tool])
        agent.current_session = {
            'messages': [],
            'trace': [],
            'turn': 0,
        }
        block_bash_file_creation(agent)  # Should not raise

    def test_empty_command(self):
        agent = Agent("test", plugins=[prefer_write_tool])
        agent.current_session = {
            'messages': [],
            'trace': [],
            'turn': 0,
            'pending_tool': {
                'name': 'bash',
                'arguments': {'command': ''},
            },
        }
        block_bash_file_creation(agent)  # Should not raise

    def test_plugin_list_contains_both_handlers(self):
        """prefer_write_tool should export both handlers."""
        assert len(prefer_write_tool) == 2
        assert block_bash_file_creation in prefer_write_tool
        assert remind_read_file in prefer_write_tool


if __name__ == '__main__':
    pytest.main([__file__, '-v'])

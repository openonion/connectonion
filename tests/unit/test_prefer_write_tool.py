"""Test prefer_write_tool plugin - block bash file operations."""

import pytest
from connectonion import Agent
from connectonion.useful_plugins import prefer_write_tool
from connectonion.useful_plugins.prefer_write_tool import (
    _is_file_creation_command,
    _is_file_reading_command,
)


def test_detect_file_creation_heredoc():
    """Test detection of heredoc file creation patterns."""
    assert _is_file_creation_command("cat <<EOF > file.py")
    assert _is_file_creation_command("cat <<'EOF' > file.txt")
    assert _is_file_creation_command("cat << 'EOF' > file.sh")


def test_detect_file_creation_redirection():
    """Test detection of output redirection patterns."""
    assert _is_file_creation_command("echo hello > file.txt")
    assert _is_file_creation_command("echo hello >> file.txt")
    assert _is_file_creation_command("printf 'test' > file.txt")
    assert _is_file_creation_command("ls -la > output.txt")
    assert _is_file_creation_command("date >> log.txt")
    assert _is_file_creation_command("git status > status.txt")


def test_detect_file_creation_paths():
    """Test detection with various path formats."""
    assert _is_file_creation_command("echo test > ./file.txt")
    assert _is_file_creation_command("echo test > ~/notes.txt")
    assert _is_file_creation_command("echo test > /tmp/file.txt")
    assert _is_file_creation_command("echo test >> /var/log/app.log")


def test_detect_file_creation_tee():
    """Test detection of tee command."""
    assert _is_file_creation_command("echo hello | tee file.txt")
    assert _is_file_creation_command("ls -la | tee output.txt")


def test_not_detect_safe_commands():
    """Test that safe commands are not flagged as file creation."""
    assert not _is_file_creation_command("ls -la")
    assert not _is_file_creation_command("git status")
    assert not _is_file_creation_command("echo hello")
    assert not _is_file_creation_command("pwd")
    assert not _is_file_creation_command("date")


def test_detect_file_reading_cat():
    """Test detection of cat for reading files."""
    assert _is_file_reading_command("cat file.txt")
    assert _is_file_reading_command("cat /etc/config")
    assert _is_file_reading_command("ls && cat file.txt")
    assert _is_file_reading_command("pwd && cat notes.md")


def test_detect_file_reading_head_tail():
    """Test detection of head/tail commands."""
    assert _is_file_reading_command("head file.txt")
    assert _is_file_reading_command("head -n 10 README.md")
    assert _is_file_reading_command("tail file.log")
    assert _is_file_reading_command("tail -f /var/log/app.log")


def test_detect_file_reading_pagers():
    """Test detection of less/more pagers."""
    assert _is_file_reading_command("less file.txt")
    assert _is_file_reading_command("more README.md")


def test_not_detect_cat_without_args():
    """Test that cat without file args is not flagged."""
    assert not _is_file_reading_command("cat")
    assert not _is_file_reading_command("ls -la")


def test_block_file_creation_with_agent():
    """Test that agent blocks file creation attempts."""
    agent = Agent("test", plugins=[prefer_write_tool])
    agent.current_session = {
        'messages': [],
        'trace': [],
        'turn': 0,
        'pending_tool': {
            'name': 'bash',
            'arguments': {'command': 'echo hello > file.txt'}
        }
    }

    from connectonion.useful_plugins.prefer_write_tool import block_bash_file_creation

    with pytest.raises(ValueError, match="Bash file creation blocked"):
        block_bash_file_creation(agent)


def test_block_file_reading_with_agent():
    """Test that agent blocks file reading attempts."""
    agent = Agent("test", plugins=[prefer_write_tool])
    agent.current_session = {
        'messages': [],
        'trace': [],
        'turn': 0,
        'pending_tool': {
            'name': 'bash',
            'arguments': {'command': 'cat file.txt'}
        }
    }

    from connectonion.useful_plugins.prefer_write_tool import block_bash_file_creation

    with pytest.raises(ValueError, match="Bash file reading blocked"):
        block_bash_file_creation(agent)


def test_allow_safe_bash_commands():
    """Test that safe bash commands are not blocked."""
    agent = Agent("test", plugins=[prefer_write_tool])
    agent.current_session = {
        'messages': [],
        'trace': [],
        'turn': 0,
        'pending_tool': {
            'name': 'bash',
            'arguments': {'command': 'git status'}
        }
    }

    from connectonion.useful_plugins.prefer_write_tool import block_bash_file_creation

    # Should not raise
    block_bash_file_creation(agent)


def test_system_reminder_includes_proper_tools():
    """Test that rejection messages recommend proper tools."""
    agent = Agent("test", plugins=[prefer_write_tool])
    agent.current_session = {
        'messages': [],
        'trace': [],
        'turn': 0,
        'pending_tool': {
            'name': 'bash',
            'arguments': {'command': 'echo test > file.txt'}
        }
    }

    from connectonion.useful_plugins.prefer_write_tool import block_bash_file_creation

    with pytest.raises(ValueError) as exc_info:
        block_bash_file_creation(agent)

    error_msg = str(exc_info.value)
    assert "Write" in error_msg
    assert "<system-reminder>" in error_msg


def test_reading_reminder_mentions_read_file():
    """Test that reading rejection mentions read_file tool."""
    agent = Agent("test", plugins=[prefer_write_tool])
    agent.current_session = {
        'messages': [],
        'trace': [],
        'turn': 0,
        'pending_tool': {
            'name': 'bash',
            'arguments': {'command': 'cat config.json'}
        }
    }

    from connectonion.useful_plugins.prefer_write_tool import block_bash_file_creation

    with pytest.raises(ValueError) as exc_info:
        block_bash_file_creation(agent)

    error_msg = str(exc_info.value)
    assert "read_file" in error_msg
    assert "<system-reminder>" in error_msg


if __name__ == '__main__':
    pytest.main([__file__, '-v'])

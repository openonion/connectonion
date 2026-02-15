"""
Purpose: Inject contextual reminders into tool results based on tool name and argument patterns
LLM-Note:
  Dependencies: imports from [pathlib, fnmatch, typing, yaml, core.events] | imported by [useful_plugins/__init__.py, cli/co_ai/agent.py, cli/co_ai/plugins/__init__.py, cli/co_ai/plugins/system_reminder.py] | tested via after_each_tool event firing
  Data flow: after_each_tool event fires → inject_reminder() checks last trace entry → _find_reminder() matches tool_name/args against triggers from .md files → if match: appends reminder content to last tool message → modifies agent.current_session['messages'][-1]['content']
  State/Effects: modifies last tool result message in agent.current_session['messages'] by appending reminder text | reads .md files from useful_prompts/system-reminders/ at import time (cached in _REMINDERS) | no writes
  Integration: exposes system_reminder=[inject_reminder] plugin | fires on after_each_tool event | REMINDERS_DIR=useful_prompts/system-reminders/ | uses _parse_frontmatter(), _load_reminders(), _matches_pattern(), _find_reminder() helpers | reminders loaded once at module import
  Performance: reminders loaded once at import (not per-call) | fnmatch glob pattern matching for path/command triggers | iterates through all reminders until first match | appends to existing tool message (in-place modification)
  Errors: returns None if no match found (no-op) | gracefully handles missing reminders directory | YAML parsing errors bubble up (fail fast)
  ⚠️ Reminder files use YAML frontmatter: name, triggers (tool, path_pattern, command_pattern)

System Reminder Plugin - Injects contextual guidance into tool results.

Usage:
    from connectonion.useful_plugins import system_reminder
    agent = Agent("assistant", plugins=[system_reminder])

To customize, use `co copy system_reminder` which copies both the plugin
and the prompt files to your project.
"""

from pathlib import Path
import fnmatch
from typing import TYPE_CHECKING

from ..core.events import after_each_tool

if TYPE_CHECKING:
    from ..core.agent import Agent

# Default reminders directory
REMINDERS_DIR = Path(__file__).parent.parent / "useful_prompts" / "system-reminders"


def _parse_frontmatter(text):
    """Parse YAML frontmatter from markdown."""
    if not text.startswith('---'):
        return {}, text
    parts = text.split('---', 2)
    if len(parts) < 3:
        return {}, text
    import yaml
    return yaml.safe_load(parts[1]) or {}, parts[2].strip()


def _load_reminders(reminders_dir):
    """Load all .md reminder files from directory."""
    reminders_dir = Path(reminders_dir)
    if not reminders_dir.exists():
        return {}
    reminders = {}
    for f in reminders_dir.glob("*.md"):
        meta, body = _parse_frontmatter(f.read_text())
        if meta.get('name'):
            reminders[meta['name']] = {'content': body, 'triggers': meta.get('triggers', [])}
    return reminders


def _matches_pattern(pattern, value):
    """Check if value matches glob pattern(s)."""
    if not pattern or not value:
        return False
    patterns = [pattern] if isinstance(pattern, str) else pattern
    return any(fnmatch.fnmatch(value, p) for p in patterns)


def _find_reminder(reminders, tool_name, args):
    """Find matching reminder content."""
    for reminder in reminders.values():
        for trigger in reminder['triggers']:
            if trigger.get('tool') and trigger['tool'] != tool_name:
                continue
            if trigger.get('path_pattern'):
                path = args.get('path') or args.get('file_path', '')
                if not _matches_pattern(trigger['path_pattern'], path):
                    continue
            if trigger.get('command_pattern'):
                cmd = args.get('command') or args.get('cmd', '')
                if not _matches_pattern(trigger['command_pattern'], cmd):
                    continue
            # All conditions matched
            content = reminder['content']
            path = args.get('path') or args.get('file_path', '')
            return content.replace('${file_path}', path).replace('${tool_name}', tool_name)
    return None


# Load reminders once at import
_REMINDERS = _load_reminders(REMINDERS_DIR)


@after_each_tool
def inject_reminder(agent: 'Agent') -> None:
    """Inject matching system reminder into tool result."""
    trace = agent.current_session.get('trace', [])
    messages = agent.current_session.get('messages', [])
    if not trace or not messages:
        return

    last = trace[-1]
    if last.get('type') != 'tool_result':
        return

    content = _find_reminder(_REMINDERS, last.get('name', ''), last.get('args', {}))
    if content:
        for msg in reversed(messages):
            if msg.get('role') == 'tool':
                msg['content'] = msg.get('content', '') + '\n\n' + content
                break


# Export plugin
system_reminder = [inject_reminder]

"""
System Reminder Plugin - Injects contextual guidance based on intent and tool usage.

Two triggers:
1. after_user_input: Detect intent (coding, agent creation) and inject relevant reminder
2. after_each_tool: Inject reminder based on tool usage

Usage:
    from connectonion.cli.co_ai.plugins.system_reminder import system_reminder

    agent = Agent("coder", plugins=[system_reminder])
"""

from pathlib import Path
import fnmatch
from typing import TYPE_CHECKING

from pydantic import BaseModel
from connectonion.core.events import after_each_tool, after_user_input
from connectonion.llm_do import llm_do

if TYPE_CHECKING:
    from connectonion.core.agent import Agent

# Default reminders directory
REMINDERS_DIR = Path(__file__).parent.parent / "prompts" / "system-reminders"


class IntentAnalysis(BaseModel):
    """Structured output for intent detection."""
    ack: str  # Acknowledgment ~10 words showing understanding
    is_build: bool  # True if creating/modifying software, code, agents


# Intent detection prompt with examples
INTENT_PROMPT = """Analyze the user's request.

User request: {user_prompt}

Return:
- ack: Friendly, proactive acknowledgment (~10 words). Start with "understood" or "got it", use "I'll" to show you're taking action. Be warm and helpful.
- is_build: true if creating/modifying code, software, agents, or automation; false for queries, questions, simple tasks

Examples:
- "list files" → ack: "understood, I'll list the files in this directory for you", is_build: false
- "what is this project" → ack: "got it, I'll explore the project structure and explain", is_build: false
- "create a login page" → ack: "understood, I'll build a login page for you", is_build: true
- "fix the bug in auth" → ack: "got it, I'll investigate and fix the auth bug", is_build: true
- "help me write a script" → ack: "understood, I'll write that script for you", is_build: true
- "run the tests" → ack: "got it, I'll run the tests and show you results", is_build: false
- "explain how this works" → ack: "understood, I'll explain how this code works", is_build: false
- "deploy to production" → ack: "got it, I'll deploy your app to production", is_build: false
- "add a new feature" → ack: "understood, I'll add that feature for you", is_build: true"""


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
            reminders[meta['name']] = {
                'content': body,
                'triggers': meta.get('triggers', []),
                'intent': meta.get('intent'),  # New: intent-based trigger
            }
    return reminders


def _matches_pattern(pattern, value):
    """Check if value matches glob pattern(s)."""
    if not pattern or not value:
        return False
    patterns = [pattern] if isinstance(pattern, str) else pattern
    return any(fnmatch.fnmatch(value, p) for p in patterns)


def _find_tool_reminder(reminders, tool_name, args):
    """Find matching reminder for tool usage."""
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


def _find_intent_reminder(reminders, intent):
    """Find matching reminder for detected intent."""
    for reminder in reminders.values():
        if reminder.get('intent') == intent:
            return reminder['content']
    return None


# Load reminders once at import
_REMINDERS = _load_reminders(REMINDERS_DIR)


@after_user_input
def detect_intent(agent: 'Agent') -> None:
    """Detect user intent and inject relevant system reminder."""
    import uuid

    user_prompt = agent.current_session.get('user_prompt', '')
    if not user_prompt:
        return

    # Generate ID for correlation
    intent_id = str(uuid.uuid4())[:8]

    # Show "analyzing" state (user feels seen)
    if agent.io:
        agent.io.send({
            'type': 'intent',
            'id': intent_id,
            'status': 'analyzing',
        })

    # Log to terminal
    if agent.logger.console:
        agent.logger.console.print("[dim]▸ understanding request...[/dim]")

    # Use llm_do with structured output
    analysis = llm_do(
        INTENT_PROMPT.format(user_prompt=user_prompt),
        model="co/gemini-2.5-flash",
        output=IntentAnalysis,
        temperature=0,
    )

    # Log acknowledgment to terminal
    if agent.logger.console:
        agent.logger.console.print(f"[dim]✓ {analysis.ack}[/dim]")

    # Send acknowledgment to frontend (user feels heard)
    if agent.io:
        agent.io.send({
            'type': 'intent',
            'id': intent_id,
            'status': 'understood',
            'ack': analysis.ack,
            'is_build': analysis.is_build,
        })

    # Store in session
    agent.current_session['intent'] = {
        'ack': analysis.ack,
        'is_build': analysis.is_build,
    }

    # Only inject system reminder for build tasks
    if analysis.is_build:
        content = _find_intent_reminder(_REMINDERS, 'build')
        if content:
            agent.current_session['messages'].append({
                'role': 'user',
                'content': f"\n\n{content}"
            })


@after_each_tool
def inject_tool_reminder(agent: 'Agent') -> None:
    """Inject matching system reminder into tool result."""
    trace = agent.current_session.get('trace', [])
    messages = agent.current_session.get('messages', [])
    if not trace or not messages:
        return

    last = trace[-1]
    if last.get('type') != 'tool_result':
        return

    content = _find_tool_reminder(_REMINDERS, last.get('name', ''), last.get('args', {}))
    if content:
        for msg in reversed(messages):
            if msg.get('role') == 'tool':
                msg['content'] = msg.get('content', '') + '\n\n' + content
                break


# Export plugin
system_reminder = [detect_intent, inject_tool_reminder]

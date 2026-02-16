"""
LLM-Note: /export command - export conversation to markdown format.

This command exports the current conversation history to a markdown file
and optionally opens it in the user's preferred text editor.

Key function:
- cmd_export(): Exports messages to timestamped markdown file
- set_agent(): Injects agent reference for message access

Export format:
- Markdown file with conversation metadata header
- Date and timestamp
- Model name (e.g., co/gemini-2.5-pro)
- Formatted message history (user/assistant/tool)
- Tool calls displayed with formatting
- Tool results in code blocks

File handling:
- Creates temporary file or saves to specified path
- Opens in $EDITOR if environment variable set
- Falls back to displaying file path if no editor
- Filename format: conversation_YYYYMMDD_HHMMSS.md

Architecture:
- Module-level _agent reference (set by CLI)
- subprocess for launching editor
- tempfile for temporary file creation
- Rich formatting for tool calls/results

Used by:
- CLI: `oo /export` or `/export` in interactive mode
- Conversation backup and sharing
- Debugging conversation flow
"""

import os
import subprocess
import tempfile
from datetime import datetime

_agent = None


def set_agent(agent):
    global _agent
    _agent = agent


def cmd_export(args: str = "") -> str:
    if not _agent:
        return "No active conversation to export."
    
    messages = getattr(_agent, 'messages', [])
    if not messages:
        return "No messages to export."
    
    lines = [
        f"# Conversation Export",
        f"",
        f"**Date:** {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"**Model:** {_agent.llm.model if hasattr(_agent, 'llm') else 'unknown'}",
        f"",
        "---",
        "",
    ]
    
    for msg in messages:
        role = msg.get('role', 'unknown')
        content = msg.get('content', '')
        
        if role == 'user':
            lines.append(f"## User\n\n{content}\n")
        elif role == 'assistant':
            lines.append(f"## Assistant\n\n{content}\n")
        elif role == 'tool':
            tool_name = msg.get('name', 'tool')
            lines.append(f"### Tool: {tool_name}\n\n```\n{content}\n```\n")
    
    markdown = "\n".join(lines)
    
    editor = os.environ.get("EDITOR", "vim")
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
        f.write(markdown)
        f.flush()
        temp_path = f.name
    
    editor_parts = editor.split()
    cmd = editor_parts + [temp_path]
    
    subprocess.run(cmd)
    
    return f"Exported to `{temp_path}`"

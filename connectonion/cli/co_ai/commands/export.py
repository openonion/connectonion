"""Export command - export conversation to markdown."""

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

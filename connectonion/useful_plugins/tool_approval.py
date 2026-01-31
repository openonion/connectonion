"""
Purpose: Web-based tool approval plugin - request user approval before dangerous tools
LLM-Note:
  Dependencies: imports from [core/events.py] | imported by [useful_plugins/__init__.py] | tested by [tests/unit/test_tool_approval.py]
  Data flow: before_each_tool fires → check if dangerous tool → io.send(approval_needed) → io.receive() blocks → approved: continue, rejected: raise ValueError
  State/Effects: stores approved_tools in session for "session" scope approvals | blocks on io.receive() until client responds | logs all approval decisions via agent.logger
  Integration: exposes tool_approval plugin list | uses agent.io for WebSocket communication | requires client to handle "approval_needed" events
  Errors: raises ValueError on rejection (stops batch, feedback sent to LLM)

Tool Approval Plugin - Request client approval before executing dangerous tools.

WebSocket-only. Uses io.send/receive pattern:
1. Sends {type: "approval_needed", tool, arguments} to client
2. Blocks until client responds with {approved: bool, scope?, feedback?}
3. If approved: execute tool (optionally save to session memory)
4. If rejected: raise ValueError, stopping batch, LLM sees feedback

Tool Classification:
- SAFE_TOOLS: Read-only operations (read, glob, grep, etc.) - never need approval
- DANGEROUS_TOOLS: Write/execute operations (bash, write, edit, etc.) - always need approval
- Unknown tools: Treated as safe (no approval needed)

Session Memory:
- scope="once": Approve for this call only
- scope="session": Approve for rest of session (no re-prompting)

Rejection Behavior:
- Raises ValueError with user feedback
- Stops entire tool batch (remaining tools skipped)
- LLM receives error message and can adjust approach

Usage:
    from connectonion import Agent
    from connectonion.useful_plugins import tool_approval

    agent = Agent("assistant", tools=[bash, write], plugins=[tool_approval])

Client Protocol:
    # Receive from server:
    {"type": "approval_needed", "tool": "bash", "arguments": {"command": "npm install"}}

    # Send response:
    {"approved": true, "scope": "session"}  # Approve for session
    {"approved": true, "scope": "once"}     # Approve once
    {"approved": false, "feedback": "Use yarn instead"}  # Reject with feedback
"""

from typing import TYPE_CHECKING

from ..core.events import before_each_tool

if TYPE_CHECKING:
    from ..core.agent import Agent


# Tools that NEVER need approval (read-only, safe)
# These tools cannot modify system state or have external side effects.
# Add new read-only tools here to skip approval prompts.
SAFE_TOOLS = {
    # File reading - read contents without modification
    'read', 'read_file',
    # Search operations - find files/content without modification
    'glob', 'grep', 'search',
    # Info operations - query metadata only
    'list_files', 'get_file_info',
    # Agent operations - sub-agents handle their own approval
    'task',
    # Documentation - load reference materials
    'load_guide',
    # Planning - state management without side effects
    'enter_plan_mode', 'exit_plan_mode', 'write_plan',
    # Task management - read-only task status
    'task_output',
    # User interaction - prompts user, not system modification
    'ask_user',
}

# Tools that ALWAYS need approval (destructive/side-effects)
# These tools can modify files, execute code, or have external effects.
# User approval required before execution in web mode.
DANGEROUS_TOOLS = {
    # Shell execution - arbitrary command execution
    'bash', 'shell', 'run', 'run_in_dir',
    # File modification - write/edit file contents
    'write', 'edit', 'multi_edit',
    # Background tasks - long-running command execution
    'run_background',
    # Task control - terminate running processes
    'kill_task',
    # External communication - send data outside system
    'send_email', 'post',
    # Deletion - remove files/resources
    'delete', 'remove',
}


# Session state helpers for approval memory
# These functions manage the session['approval'] dict which tracks
# which tools have been approved for the current session.

def _init_approval_state(session: dict) -> None:
    """Initialize approval state in session if not present.

    Creates session['approval']['approved_tools'] dict for storing
    tool approvals with scope='session'.
    """
    if 'approval' not in session:
        session['approval'] = {
            'approved_tools': {},  # tool_name -> 'session'
        }


def _is_approved_for_session(session: dict, tool_name: str) -> bool:
    """Check if tool was approved for this session.

    Returns True if user previously approved this tool with scope='session'.
    """
    approval = session.get('approval', {})
    return approval.get('approved_tools', {}).get(tool_name) == 'session'


def _save_session_approval(session: dict, tool_name: str) -> None:
    """Save tool as approved for this session.

    Future calls to the same tool will skip approval prompts.
    """
    _init_approval_state(session)
    session['approval']['approved_tools'][tool_name] = 'session'


def _log(agent: 'Agent', message: str, style: str = None) -> None:
    """Log message via agent's logger if available.

    Args:
        agent: Agent instance
        message: Message to log
        style: Rich style string (e.g., "[green]", "[red]")
    """
    if hasattr(agent, 'logger') and agent.logger:
        agent.logger.print(message, style)


@before_each_tool
def check_approval(agent: 'Agent') -> None:
    """Check if tool needs approval and request from client.

    Flow:
    1. Skip if no IO (not web mode)
    2. Skip if safe tool
    3. Skip if unknown tool (default: safe)
    4. Skip if already approved for session
    5. Send approval_needed, wait for response
    6. If approved: optionally save to session, continue
    7. If rejected: raise ValueError (stops batch)

    Logging:
    - Logs approval requests, approvals, and rejections
    - Uses agent.logger.print() for terminal output

    Raises:
        ValueError: If user rejects the tool (includes feedback if provided)
    """
    # No IO = not web mode, skip
    if not agent.io:
        return

    # Get pending tool info
    pending = agent.current_session.get('pending_tool')
    if not pending:
        return

    tool_name = pending['name']
    tool_args = pending['arguments']

    # Safe tools don't need approval
    if tool_name in SAFE_TOOLS:
        return

    # Unknown tools (not in SAFE or DANGEROUS) are treated as safe
    if tool_name not in DANGEROUS_TOOLS:
        return

    # Already approved for this session
    if _is_approved_for_session(agent.current_session, tool_name):
        _log(agent, f"[dim]⏭ {tool_name} (session-approved)[/dim]")
        return

    # Send approval request to client
    agent.io.send({
        'type': 'approval_needed',
        'tool': tool_name,
        'arguments': tool_args,
    })

    # Wait for client response (BLOCKS)
    response = agent.io.receive()

    # Handle connection closed
    if response.get('type') == 'io_closed':
        _log(agent, f"[red]✗ {tool_name} - connection closed[/red]")
        raise ValueError(f"Connection closed while waiting for approval of '{tool_name}'")

    # Check approval
    approved = response.get('approved', False)

    if approved:
        # Save to session if scope is "session"
        scope = response.get('scope', 'once')
        if scope == 'session':
            _save_session_approval(agent.current_session, tool_name)
            _log(agent, f"[green]✓ {tool_name} approved (session)[/green]")
        else:
            _log(agent, f"[green]✓ {tool_name} approved (once)[/green]")
        # Continue to execute tool
        return

    # Rejected - raise ValueError to stop batch
    feedback = response.get('feedback', '')
    if feedback:
        _log(agent, f"[red]✗ {tool_name} rejected: {feedback}[/red]")
    else:
        _log(agent, f"[red]✗ {tool_name} rejected[/red]")

    error_msg = f"User rejected tool '{tool_name}'."
    if feedback:
        error_msg += f" Feedback: {feedback}"
    raise ValueError(error_msg)


# Export as plugin (list of event handlers)
# Usage: Agent("name", plugins=[tool_approval])
# The plugin registers check_approval as a before_each_tool handler
tool_approval = [check_approval]

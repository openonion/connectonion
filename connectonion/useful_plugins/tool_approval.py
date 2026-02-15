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
2. Blocks until client responds with {approved: bool, scope?, feedback?, mode?}
3. If approved: execute tool (optionally save to session memory)
4. If rejected: raise ValueError, LLM sees rejection message

Rejection Modes (client sends mode field):
- "reject_soft": Skip this tool, loop continues. LLM gets hint to use ask_user.
- "reject_hard" (default): Skip remaining batch, stop loop, wait for user input.

Tool Classification:
- SAFE_TOOLS: Read-only operations (read, glob, grep, etc.) - never need approval
- DANGEROUS_TOOLS: Write/execute operations (bash, write, edit, etc.) - always need approval
- Unknown tools: Treated as safe (no approval needed)

Session Memory:
- scope="once": Approve for this call only
- scope="session": Approve for rest of session (no re-prompting)

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
    {"approved": false, "feedback": "Use yarn instead", "mode": "reject_soft"}   # Skip, agent continues
    {"approved": false, "feedback": "Wrong approach", "mode": "reject_hard"}     # Stop, wait for user
"""

from typing import TYPE_CHECKING

from ..core.events import before_each_tool

if TYPE_CHECKING:
    from ..core.agent import Agent


# =============================================================================
# MODE SYSTEM
# =============================================================================
# Three modes control approval behavior:
#   - 'safe' (default): Dangerous tools need approval
#   - 'plan': Read-only tools only, exit_plan_mode shows plan for approval
#   - 'accept_edits': No approvals, agent runs freely
#
# Mode can be changed by:
#   - User: via WebSocket { type: 'mode_change', mode: '...' }
#   - Agent: via enter_plan_mode() tool (safe/accept_edits → plan)
# =============================================================================

VALID_MODES = {'safe', 'plan', 'accept_edits'}
DEFAULT_MODE = 'safe'


# Tools that NEVER need approval (read-only, safe)
# These tools cannot modify system state or have external side effects.
SAFE_TOOLS = {
    # File reading
    'read', 'read_file',
    # Search operations
    'glob', 'grep', 'search',
    # Info operations
    'list_files', 'get_file_info',
    # Agent operations - sub-agents handle their own approval
    'task',
    # Documentation
    'load_guide',
    # Planning - enter freely, write plan freely
    'enter_plan_mode', 'write_plan',
    # Task management
    'task_output',
    # User interaction
    'ask_user',
}

# Tools that need approval in 'safe' mode
# These tools can modify files, execute code, or have external effects.
DANGEROUS_TOOLS = {
    # Shell execution
    'bash', 'shell', 'run', 'run_in_dir',
    # File modification
    'write', 'edit', 'multi_edit',
    # Background tasks
    'run_background',
    # Task control
    'kill_task',
    # External communication
    'send_email', 'post',
    # Deletion
    'delete', 'remove',
    # Plan approval - exit_plan_mode shows plan for user review
    'exit_plan_mode',
}


# Command-based tools — approval is per command name, not per tool type.
# e.g., approving `ls` doesn't approve `rm`. Approval key: "bash:ls"
COMMAND_TOOLS = {'bash', 'shell', 'run', 'run_in_dir', 'run_background'}


def _get_approval_key(tool_name: str, tool_args: dict) -> str:
    """Get the approval key for session memory.

    Command tools (bash, shell, etc.): "bash:ls", "bash:npm"
    Other tools: "write", "edit" (tool name only)
    """
    if tool_name in COMMAND_TOOLS:
        command = tool_args.get('command', '')
        cmd_name = command.split()[0] if command.strip() else ''
        if cmd_name:
            return f"{tool_name}:{cmd_name}"
    return tool_name


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


def _resolve_display_name(tool_name: str, args_str: str) -> str:
    """Resolve display name from tool name and JSON arguments string.

    Command tools (bash, etc.): "bash:ls", "bash:npm"
    Other tools: "write", "edit" (unchanged)
    """
    if tool_name in COMMAND_TOOLS:
        import json
        try:
            args = json.loads(args_str)
        except (json.JSONDecodeError, TypeError):
            args = {}
        return _get_approval_key(tool_name, args)
    return tool_name


def _get_batch_remaining(agent: 'Agent', current_tool_id: str) -> list:
    """Extract remaining tools in the batch from the assistant message.

    The assistant message with all tool_calls is already in messages
    (added by tool_executor before the loop). We find the current tool
    by ID and return everything after it.

    Tool names are resolved to display names (e.g., bash → ls).
    """
    messages = agent.current_session.get('messages', [])
    # Walk backwards to find the last assistant message with tool_calls
    for msg in reversed(messages):
        if msg.get('role') == 'assistant' and msg.get('tool_calls'):
            tool_calls = msg['tool_calls']
            # Find current tool's position
            for i, tc in enumerate(tool_calls):
                if tc.get('id') == current_tool_id:
                    # Return tools after current one with resolved display names
                    remaining = []
                    for t in tool_calls[i + 1:]:
                        name = t['function']['name']
                        args = t['function'].get('arguments', '{}')
                        remaining.append({
                            'tool': _resolve_display_name(name, args),
                            'arguments': args,
                        })
                    return remaining
            break
    return []


def _log(agent: 'Agent', message: str, style: str = None) -> None:
    """Log message via agent's logger if available.

    Args:
        agent: Agent instance
        message: Message to log
        style: Rich style string (e.g., "[green]", "[red]")
    """
    if hasattr(agent, 'logger') and agent.logger:
        agent.logger.print(message, style)


def _get_mode(agent: 'Agent') -> str:
    """Get current approval mode from session.

    Modes:
        'safe': Dangerous tools need approval (default)
        'plan': Read-only tools only, exit_plan_mode needs approval
        'accept_edits': No approvals, agent runs freely
    """
    return agent.current_session.get('mode', DEFAULT_MODE)


def _set_mode(agent: 'Agent', mode: str) -> None:
    """Set approval mode in session and notify frontend."""
    if mode not in VALID_MODES:
        mode = DEFAULT_MODE
    agent.current_session['mode'] = mode
    # Notify frontend of mode change
    if agent.io:
        agent.io.send({'type': 'mode_changed', 'mode': mode, 'triggered_by': 'agent'})


@before_each_tool
def check_approval(agent: 'Agent') -> None:
    """Check if tool needs approval based on current mode.

    Mode behavior:
        'safe': Dangerous tools need approval
        'plan': Only read-only tools allowed, exit_plan_mode needs approval
        'accept_edits': No approvals needed

    Raises:
        ValueError: If tool rejected or blocked by mode
    """
    # reject_hard was set by a previous tool in this batch — reject remaining
    if 'tool_rejected_hard' in agent.current_session:
        raise ValueError("User rejected this batch of tools. They want to provide input for the correct direction.")

    # No IO = not web mode, skip
    if not agent.io:
        return

    # Get pending tool info
    pending = agent.current_session.get('pending_tool')
    if not pending:
        return

    tool_name = pending['name']
    tool_args = pending['arguments']
    mode = _get_mode(agent)

    # =================================================================
    # MODE: accept_edits - No approvals needed
    # =================================================================
    if mode == 'accept_edits':
        _log(agent, f"[dim]⚡ {tool_name} (accept_edits mode)[/dim]")
        return

    # =================================================================
    # MODE: plan - Read-only tools only, exit_plan_mode needs approval
    # =================================================================
    if mode == 'plan':
        # exit_plan_mode is the only dangerous tool allowed - needs approval to show plan
        if tool_name == 'exit_plan_mode':
            pass  # Fall through to approval logic below
        # Block other dangerous tools in plan mode
        elif tool_name in DANGEROUS_TOOLS:
            raise ValueError(
                f"Tool '{tool_name}' is blocked in Plan Mode. "
                "Use read-only tools to explore, write your plan with write_plan(), "
                "then call exit_plan_mode() when ready for approval."
            )
        # Safe tools are allowed
        else:
            return

    # =================================================================
    # MODE: safe - Dangerous tools need approval
    # =================================================================
    # Safe tools don't need approval
    if tool_name in SAFE_TOOLS:
        return

    # Unknown tools (not in SAFE or DANGEROUS) are treated as safe
    if tool_name not in DANGEROUS_TOOLS:
        return

    # Already approved for this session
    approval_key = _get_approval_key(tool_name, tool_args)
    if _is_approved_for_session(agent.current_session, approval_key):
        _log(agent, f"[dim]⏭ {approval_key} (session-approved)[/dim]")
        return

    # Get remaining tools in this batch for client context
    pending = agent.current_session.get('pending_tool')
    tool_id = pending.get('id', '') if pending else ''
    batch_remaining = _get_batch_remaining(agent, tool_id)

    # Send approval request to client
    # Tool name uses approval key format: "bash:ls" for commands, "write" for others
    approval_msg = {
        'type': 'approval_needed',
        'tool': approval_key,
        'arguments': tool_args,
        'description': tool_args.get('description', ''),
    }
    if batch_remaining:
        approval_msg['batch_remaining'] = batch_remaining
    agent.io.send(approval_msg)

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
            _save_session_approval(agent.current_session, approval_key)
            _log(agent, f"[green]✓ {approval_key} approved (session)[/green]")
        else:
            _log(agent, f"[green]✓ {tool_name} approved (once)[/green]")
        return

    # Rejected
    feedback = response.get('feedback', '')
    mode = response.get('mode', 'reject_hard')

    if feedback:
        _log(agent, f"[red]✗ {tool_name} rejected: {feedback}[/red]")
    else:
        _log(agent, f"[red]✗ {tool_name} rejected[/red]")

    if mode == 'reject_hard':
        # Set flag — remaining tools in batch will be rejected, loop will stop
        agent.current_session['tool_rejected_hard'] = feedback or f"User rejected tool '{tool_name}'."
        raise ValueError(
            f"User rejected tool '{tool_name}'."
            + (f" Feedback: {feedback}" if feedback else "")
        )

    if mode == 'reject_explain':
        # Like reject_soft: skip tool, loop continues
        # But ask for explanation - user may not understand tech concepts at all
        raise ValueError(
            f"User wants explanation for tool '{tool_name}'."
            + (f" Context: {feedback}" if feedback else "")
            + "\n\n<system-reminder>"
            "User clicked 'Explain' - they don't understand what you're doing.\n\n"
            "IMPORTANT: The user may have NO technical background. Explain like teaching a 15-year-old:\n\n"
            "1. CONTEXT: What are you trying to accomplish overall? (the big picture)\n"
            "2. CONCEPT: What is this type of action? (e.g., 'A bash command is like giving instructions to your computer through text')\n"
            "3. THIS STEP: What specifically will this do? Use simple analogies.\n"
            "4. WHY NEEDED: Why is this step necessary to complete the task?\n"
            "5. CONSEQUENCE: What happens after this runs? Is it reversible?\n\n"
            "Keep it simple, avoid jargon, use everyday analogies.\n"
            "After explaining, ask if they want to proceed or have more questions.\n"
            "Do NOT retry the tool until the user explicitly approves.\n"
            "</system-reminder>"
        )

    # reject_soft — skip this tool, loop continues, hint LLM to use ask_user tool
    raise ValueError(
        f"User rejected tool '{tool_name}'."
        + (f" Feedback: {feedback}" if feedback else "")
        + "\n\n<system-reminder>"
        f"User skipped '{tool_name}'. Do not retry it.\n\n"
        "Call ask_user to let the user choose direction:\n"
        "- Think about what the rejected tool was trying to accomplish\n"
        "- Offer 2-4 specific alternatives as options (not vague)\n"
        "- Always include a 'Skip this entirely' option\n\n"
        "ask_user(question=\"...contextual question...\", options=[\"alt 1\", \"alt 2\", \"Skip this entirely\"])\n\n"
        "Do not respond with text instead of calling ask_user."
        "</system-reminder>"
    )


# Export as plugin (list of event handlers)
# Usage: Agent("name", plugins=[tool_approval])
# The plugin registers check_approval as a before_each_tool handler
tool_approval = [check_approval]

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
from pathlib import Path

from ..core.events import before_each_tool, before_iteration, after_user_input

if TYPE_CHECKING:
    from ..core.agent import Agent


# =============================================================================
# MODE SYSTEM
# =============================================================================
# Three modes control approval behavior:
#   - 'safe' (default): Dangerous tools need approval
#   - 'plan': Read-only tools only, exit_plan_mode shows plan for approval
#   - 'accept_edits': File edit tools auto-approved, other dangerous tools need approval
#
# Other modes (handled by separate plugins via skip_tool_approval flag):
#   - 'ulw': Handled by ulw plugin - sets skip_tool_approval=True
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
    # Planning - enter freely (write_plan needs approval for user feedback)
    'enter_plan_mode',
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

# File edit tools - auto-approved in 'accept_edits' mode
# These tools only modify files, no external side effects.
FILE_EDIT_TOOLS = {'write', 'edit', 'multi_edit'}


# Command-based tools — approval is per command name, not per tool type.
# e.g., approving `ls` doesn't approve `rm`. Approval key: "bash:ls"
COMMAND_TOOLS = {'bash', 'shell', 'run', 'run_in_dir', 'run_background'}


def _extract_commands_from_bash(command: str) -> list[str]:
    """Parse bash command chain into individual command names.

    Uses bashlex AST to handle: pipes, &&, ||, ;, command substitution, etc.

    Examples:
        "pwd && ls -F" → ["pwd", "ls"]
        "cat file | grep test" → ["cat", "grep"]

    Args:
        command: Bash command string

    Returns:
        List of command names (just names, no args)
    """
    try:
        import bashlex

        parts = bashlex.parse(command)
        commands = []

        def extract_from_node(node):
            """Recursively extract commands from AST node."""
            if node.kind == 'command':
                # Get first word (command name)
                for part in node.parts:
                    if part.kind == 'word':
                        commands.append(part.word)
                        break
            elif hasattr(node, 'parts'):
                # Recurse into child nodes
                for part in node.parts:
                    extract_from_node(part)

        for tree in parts:
            extract_from_node(tree)

        return commands if commands else [command.split()[0] if command.split() else command]

    except Exception:
        parts = command.split()
        return [parts[0]] if parts else [command]


def _check_bash_chain_permitted(command: str, permissions: dict) -> tuple[bool, str]:
    """Check if ALL commands in bash chain are permitted.

    For "pwd && ls -F", checks if BOTH pwd AND ls are allowed.
    If ANY command lacks permission, whole chain is rejected.

    Args:
        command: Bash command (may be chain)
        permissions: Session permissions dict

    Returns:
        (permitted, reason) tuple
    """
    from .skills import matches_permission_pattern

    commands = _extract_commands_from_bash(command)
    unpermitted = []

    for cmd_name in commands:
        found = False
        for pattern, perm in permissions.items():
            if perm.get('allowed') and matches_permission_pattern('bash', {'command': cmd_name}, [pattern]):
                found = True
                break
        if not found:
            unpermitted.append(cmd_name)

    if unpermitted:
        return False, None

    reason = f"safe chain ({len(commands)} commands)" if len(commands) > 1 else "permitted"
    return True, reason


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
    """Save tool as approved for this session using unified permissions.

    Future calls to the same tool will skip approval prompts.
    """
    if 'permissions' not in session:
        session['permissions'] = {}

    session['permissions'][tool_name] = {
        'allowed': True,
        'source': 'user',
        'reason': 'approved for session',
        'expires': {'type': 'session_end'}
    }


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
        'accept_edits': File edit tools auto-approved, other dangerous tools need approval

    Other plugins can set session['skip_tool_approval'] = True to bypass all checks.

    Raises:
        ValueError: If tool rejected or blocked by mode
    """
    # =================================================================
    # Check unified permissions from session
    # =================================================================
    pending = agent.current_session.get('pending_tool')
    if pending:
        tool_name = pending['name']
        tool_args = pending['arguments']

        # Get permissions from session (includes safe tools from template)
        permissions = agent.current_session.get('permissions', {})

        if permissions:
            # Import pattern matcher from skills plugin
            from .skills import matches_permission_pattern
            import fnmatch

            # Special handling for bash command chains
            if tool_name == 'bash' and 'command' in tool_args:
                permitted, reason = _check_bash_chain_permitted(tool_args['command'], permissions)
                if permitted:
                    # Find source from first matching permission
                    source = 'config'
                    commands = _extract_commands_from_bash(tool_args['command'])
                    if commands:
                        for pattern, perm in permissions.items():
                            if perm.get('allowed') and matches_permission_pattern('bash', {'command': commands[0]}, [pattern]):
                                source = perm.get('source', 'config')
                                break
                    if hasattr(agent, 'logger') and agent.logger and hasattr(agent.logger, 'console'):
                        agent.logger.console.log_permission_granted('bash', tool_args, source, reason)
                    return

            # Check each permission in the dict
            for pattern, perm in permissions.items():
                if not perm.get('allowed'):
                    continue

                # First check basic pattern match (tool name or Bash command)
                if matches_permission_pattern(tool_name, tool_args, [pattern]):
                    # Check if there's a match field for parameter-level matching
                    match_config = perm.get('match')
                    if match_config:
                        # Parameter matching - all conditions must match
                        all_match = True
                        for param_name, param_pattern in match_config.items():
                            actual_value = tool_args.get(param_name, '')
                            # Use fnmatch for glob pattern matching
                            if not fnmatch.fnmatch(str(actual_value), str(param_pattern)):
                                all_match = False
                                break

                        if not all_match:
                            continue  # This permission doesn't match, try next

                    # Pattern matched (and params matched if match field exists)
                    reason = perm.get('reason', 'unknown')
                    source = perm.get('source', 'config')
                    if hasattr(agent, 'logger') and agent.logger and hasattr(agent.logger, 'console'):
                        agent.logger.console.log_permission_granted(tool_name, tool_args, source, reason)
                    return

    # =================================================================
    # Check if another plugin requested to skip approvals (e.g., ulw)
    # =================================================================
    if agent.current_session.get('mode') == 'ulw':
        pending = agent.current_session.get('pending_tool')
        tool_name = pending['name'] if pending else 'unknown'
        tool_args = pending.get('arguments', {}) if pending else {}
        if hasattr(agent, 'logger') and agent.logger and hasattr(agent.logger, 'console'):
            agent.logger.console.log_permission_granted(tool_name, tool_args, 'mode', 'ulw mode')
        return

    # reject_hard was set by a previous tool in this batch — reject remaining
    if 'stop_signal' in agent.current_session:
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
    # MODE: accept_edits - File edits auto-approved, others need approval
    # =================================================================
    if mode == 'accept_edits':
        if tool_name in FILE_EDIT_TOOLS:
            if hasattr(agent, 'logger') and agent.logger and hasattr(agent.logger, 'console'):
                agent.logger.console.log_permission_granted(tool_name, tool_args, 'mode', 'accept_edits mode')
            return
        # Other dangerous tools fall through to approval logic

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
    # Unknown tools (not in SAFE or DANGEROUS) are treated as safe
    if tool_name not in DANGEROUS_TOOLS:
        return

    # Get approval key for this tool
    approval_key = _get_approval_key(tool_name, tool_args)

    # Get remaining tools in this batch for client context
    pending = agent.current_session.get('pending_tool')
    tool_id = pending.get('id', '') if pending else ''
    batch_remaining = _get_batch_remaining(agent, tool_id)

    # Send approval request to client
    approval_msg = {
        'type': 'approval_needed',
        'tool': approval_key,
        'arguments': tool_args,
        'description': tool_args.get('description', ''),
    }
    if batch_remaining:
        approval_msg['batch_remaining'] = batch_remaining

    # For exit_plan_mode, include plan content for display
    if tool_name == 'exit_plan_mode':
        approval_msg['plan_content'] = agent.current_session.get('pending_plan_content', '')

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
        # For exit_plan_mode, restore previous mode
        if tool_name == 'exit_plan_mode':
            previous_mode = agent.current_session.get('previous_mode', 'safe')
            _set_mode(agent, previous_mode)
            _log(agent, f"[green]✓ Plan approved, returning to {previous_mode} mode[/green]")
            # Clean up
            agent.current_session.pop('pending_plan_content', None)
            agent.current_session.pop('previous_mode', None)
            return

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
        agent.current_session['stop_signal'] = feedback or f"User rejected tool '{tool_name}'."
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


def handle_mode_change(agent: 'Agent', mode: str) -> None:
    """Handle mode change request from frontend.

    Called when frontend sends { type: 'mode_change', mode: '...' }
    Only handles modes known to this plugin (safe, plan, accept_edits).
    Other modes (e.g., ulw) should be handled by their respective plugins.

    Args:
        agent: Agent instance
        mode: New mode ('safe', 'plan', 'accept_edits')
    """
    if mode not in VALID_MODES:
        # Unknown mode - might be handled by another plugin (e.g., ulw)
        return

    old_mode = _get_mode(agent)
    if old_mode == mode:
        return  # No change

    # Clear skip_tool_approval when switching to a mode we handle
    agent.current_session.pop('skip_tool_approval', None)

    _set_mode(agent, mode)
    _log(agent, f"[cyan]Mode changed: {old_mode} → {mode}[/cyan]")


def get_current_mode(agent: 'Agent') -> str:
    """Get the current approval mode."""
    return _get_mode(agent)


@after_user_input
def load_config_permissions(agent: 'Agent') -> None:
    """Load permissions from host.yaml into session after user input.

    Reads permissions from .co/host.yaml (project) or falls back to
    the template in the package if project config doesn't exist.

    Uses unified permission structure with source='config'.
    Runs after user input so session is guaranteed to exist.
    Only loads once per session (first input).
    """
    import yaml

    # Only load once per session
    if 'permissions' in agent.current_session and 'permissions_source' in agent.current_session:
        return

    # Try project-specific config first
    co_dir = Path.cwd() / '.co'
    host_yaml = co_dir / 'host.yaml'

    # Fall back to template if project config doesn't exist
    if not host_yaml.exists():
        # Load from package template
        template_path = Path(__file__).parent.parent / 'network' / 'host' / 'host.yaml'
        if template_path.exists():
            host_yaml = template_path
        else:
            return

    # Load YAML config
    with open(host_yaml, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f) or {}

    # Get permissions from config
    permissions_config = config.get('permissions')
    if not permissions_config:
        return

    # Validate permissions structure
    if not isinstance(permissions_config, dict):
        return

    # Store config permissions in session (session already exists after user input)
    if 'permissions' not in agent.current_session:
        agent.current_session['permissions'] = {}

    # Merge config permissions into session permissions
    agent.current_session['permissions'].update(permissions_config)

    # Store config file path in session for reference
    agent.current_session['permissions_source'] = str(host_yaml.name)

    # Log where permissions were loaded from (once, at startup)
    if hasattr(agent, 'logger') and agent.logger and hasattr(agent.logger, 'console'):
        count = len(permissions_config)
        agent.logger.console.print(
            f"[dim]Loaded {count} permission(s) from {host_yaml.name}[/dim]"
        )


@before_iteration
def poll_mode_changes(agent: 'Agent') -> None:
    """Poll for mode_change signals at iteration start.

    Checks if client sent mode_change while agent was working.
    Handles all modes: safe, plan, accept_edits, ulw.
    """
    if not agent.io:
        return

    for msg in agent.io.receive_all('mode_change'):
        new_mode = msg.get('mode')
        if new_mode in VALID_MODES:
            handle_mode_change(agent, new_mode)
        elif new_mode == 'ulw':
            from .ulw import handle_ulw_mode_change
            handle_ulw_mode_change(agent, msg.get('turns'))


# Export as plugin (list of event handlers)
# Usage: Agent("name", plugins=[tool_approval])
tool_approval = [load_config_permissions, poll_mode_changes, check_approval]

# Export mode functions for external use
__all__ = [
    'tool_approval',
    'handle_mode_change',
    'get_current_mode',
    'VALID_MODES',
    'DEFAULT_MODE',
]

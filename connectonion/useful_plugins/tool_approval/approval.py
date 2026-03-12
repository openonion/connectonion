"""
Purpose: Orchestrate WebSocket-based tool approval with mode system and permission validation
LLM-Note:
  Dependencies: imports from [../../core/events.py (before_each_tool, before_iteration, after_user_input), ./constants.py (VALID_MODES, DEFAULT_MODE, DANGEROUS_TOOLS, FILE_EDIT_TOOLS, COMMAND_TOOLS), ./bash_parser.py (extract_commands_from_bash, check_bash_chain_permitted), ../skills.py (matches_permission_pattern), pathlib.Path, typing.TYPE_CHECKING] | imported by [tool_approval/__init__.py] | tested by [tests/unit/test_tool_approval.py, tests/integration/test_config_permissions.py, tests/integration/test_bash_chain_permissions.py]
  Data flow: after_user_input → load_config_permissions() loads .co/host.yaml permissions into session['permissions'] | before_iteration → poll_mode_changes() checks for mode_change messages | before_each_tool → check_approval() validates tool against mode+permissions → if dangerous: agent.io.send(approval_needed) → agent.io.receive() blocks for client response → if approved: return (execute tool) | if rejected: raise ValueError (LLM sees rejection message)
  State/Effects: modifies session['permissions'] (permission cache), session['approval']['approved_tools'] (session-scoped approvals), session['mode'] (safe/plan/accept_edits) | reads .co/host.yaml file | writes to agent.logger for approval logs | sends WebSocket messages via agent.io | blocks execution waiting for user approval
  Integration: exposes check_approval (before_each_tool hook), load_config_permissions (after_user_input hook), poll_mode_changes (before_iteration hook), handle_mode_change(agent, mode), get_current_mode(agent) | uses agent.io.send/receive for client communication | integrates with skills plugin for permission pattern matching | integrates with ulw plugin for ulw mode handling
  Performance: yaml file loaded once per session (cached) | permission checks are O(n) where n=number of permission patterns | WebSocket receive() blocks until user responds (can be seconds/minutes)
  Errors: ValueError raised when tool rejected → LLM sees error message with feedback | raises ValueError if connection closed during approval | bubbles up bashlex.ParsingError from bash_parser

Architecture:
    ┌─────────────────────────────────────────────────────────────────┐
    │  Session Lifecycle                                              │
    │                                                                 │
    │  1. after_user_input → load_config_permissions()                │
    │     Load .co/host.yaml → session['permissions']                 │
    │     Merge template safe tools + project config                  │
    │                                                                 │
    │  2. before_iteration → poll_mode_changes()                      │
    │     Check for mode_change messages from client                  │
    │     Update session['mode'] if changed                           │
    │                                                                 │
    │  3. before_each_tool → check_approval()                         │
    │     Check tool against unified permissions                      │
    │     If bash: validate ALL commands in chain                     │
    │     If not permitted: send approval_needed → block → handle     │
    └─────────────────────────────────────────────────────────────────┘

Mode System (session['mode']):
    safe (default):
        - Safe tools: auto-approved (read, glob, grep)
        - Dangerous tools: need approval (bash, write, delete)
        - Used for: normal coding assistance

    plan:
        - Read-only tools: auto-approved
        - Dangerous tools: BLOCKED (except exit_plan_mode)
        - exit_plan_mode: needs approval (shows plan to user)
        - Used for: planning phase before execution

    accept_edits:
        - File edit tools: auto-approved (write, edit, multi_edit)
        - Other dangerous tools: need approval (bash, send_email)
        - Used for: rapid editing with approval only for risky ops

    ulw (handled by ulw plugin):
        - Sets skip_tool_approval=True → bypasses all checks
        - Used for: unlimited write access (trusted scenarios)

Unified Permissions (session['permissions']):
    All permissions use unified format with single key per tool:

    {
        "bash": {
            "allowed": True,
            "source": "config",  # or "skill" or "user"
            "reason": "Pre-approved git commands",
            "when": {"command": "git status"},  # Optional granular matching
            "expires": {"type": "never"}  # or "turn_end" or "session_end"
        },
        "read": {
            "allowed": True,
            "source": "safe",
            "reason": "read-only",
            "expires": {"type": "never"}
        },
        "write": {
            "allowed": True,
            "source": "user",
            "reason": "approved for session",
            "expires": {"type": "session_end"}
        }
    }

    Permission overwrites:
        - Config loads first (source='config')
        - Skills grant turn-scoped (source='skill', may overwrite config)
        - User approvals are tool-level (source='user', overwrites everything)
        - When user approves "bash npm", they approve ALL bash commands

    Sources:
        - "safe": Template safe tools (always loaded first)
        - "config": Project .co/host.yaml using Bash() patterns
        - "skill": Skill-granted using Bash() patterns (turn-scoped)
        - "user": Runtime approvals (tool-level, session-scoped)
        - "mode": Mode-specific auto-approvals (accept_edits mode)

    Pattern Matching (matches_permission_pattern):
        - Simple: "read" → matches tool_name
        - Bash key: "bash" → matches bash tool, then checks 'when' field
        - Bash pattern: "Bash(git status)" → parses and validates command
        - Wildcards: "Bash(git *)" → matches any git command

    'when' Field (granular parameter matching):
        when: {command: "git status"} → exact command match
        when: {command: "git *"} → wildcard command match
        when: {path: "*.md"} → fnmatch on path parameter

Approval Protocol (WebSocket):
    1. Server → Client:
        {
            "type": "approval_needed",
            "tool": "bash",
            "arguments": {"command": "npm install"},
            "description": "Install npm packages",
            "batch_remaining": [{"tool": "write", "arguments": {...}}]
        }

    2. Client → Server (approved):
        {
            "approved": true,
            "scope": "session"  # or "once"
        }

    3. Client → Server (rejected soft - skip tool, continue):
        {
            "approved": false,
            "feedback": "Use yarn instead",
            "mode": "reject_soft"
        }

    4. Client → Server (rejected hard - stop batch, wait for input):
        {
            "approved": false,
            "feedback": "Wrong approach",
            "mode": "reject_hard"
        }

    5. Client → Server (explain - user doesn't understand):
        {
            "approved": false,
            "feedback": "What is npm?",
            "mode": "reject_explain"
        }

Session Memory (approved_tools):
    scope="once": Approve this call only (default)
    scope="session": Save to session['permissions'] → no re-prompting
        - Stored as: session['permissions'][tool_name] = {...}
        - Tool-level approval: approving "bash" approves ALL bash commands
        - Examples: "bash", "write", "edit"

Bash Chain Validation:
    ⚠️ CRITICAL: Prevents security bypass via command chaining
    Example: "ls && rm -rf /" requires BOTH ls AND rm permissions
    Implementation:
        1. extract_commands_from_bash("ls && rm") → ["ls", "rm"]
        2. check_bash_chain_permitted() validates EACH command
        3. If ANY unpermitted → reject whole chain
        4. Logs: "safe chain (2 commands)" if all permitted

Rejection Modes:
    reject_soft:
        - Raises ValueError with hint to use ask_user tool
        - LLM should offer alternatives via ask_user
        - Batch continues (remaining tools still execute)

    reject_hard (default):
        - Sets session['stop_signal'] → remaining tools rejected
        - Breaks iteration loop → waits for user input
        - Used when user wants to redirect approach

    reject_explain:
        - Like reject_soft but includes system-reminder
        - Instructs LLM to explain in simple terms (15-year-old level)
        - Used when user doesn't understand technical concepts

Helper Functions:
    _get_approval_key(tool_name, args) → tool_name (always tool-level)
    _init_approval_state(session) → creates session['approval'] structure
    _is_approved_for_session(session, tool_name) → bool
    _save_session_approval(session, tool_name) → saves to session['permissions']
    _resolve_display_name(tool_name, args_str) → "bash" or "write" for UI
    _get_batch_remaining(agent, current_tool_id) → List[tool calls after current]
    _log(agent, message, style) → logs via agent.logger
    _get_mode(agent) → current mode string
    _set_mode(agent, mode) → updates mode, notifies frontend
    matches_permission_pattern(tool_name, tool_args, pattern) → bool (pattern matching)

Event Handlers:
    @after_user_input: load_config_permissions
    @before_iteration: poll_mode_changes
    @before_each_tool: check_approval

Public Functions:
    handle_mode_change(agent, mode) → changes mode, logs transition
    get_current_mode(agent) → returns current mode string

File Relationships:
    tool_approval/
    ├── approval.py          # THIS FILE - orchestration + event handlers
    ├── constants.py         # Tool classification + mode constants
    ├── bash_parser.py       # Bash chain parsing + validation
    └── __init__.py          # Plugin export

    Flow: agent → check_approval() → bash_parser (if bash tool)
                                    → skills.matches_permission_pattern()
                                    → agent.io.send/receive
                                    → raise ValueError or return
"""

from typing import TYPE_CHECKING
from pathlib import Path

from ...core.events import before_each_tool, before_iteration, after_user_input
from .constants import VALID_MODES, DEFAULT_MODE, DANGEROUS_TOOLS, FILE_EDIT_TOOLS, COMMAND_TOOLS
from .bash_parser import extract_commands_from_bash, check_bash_chain_permitted

if TYPE_CHECKING:
    from ...core.agent import Agent


# =============================================================================
# Helper Functions
# =============================================================================

def _get_approval_key(tool_name: str, tool_args: dict) -> str:
    """Get the approval key for session memory.

    Always returns just the tool name.
    Command-specific logic handled in _save_session_approval via 'when' field.
    """
    return tool_name


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


def _save_session_approval(session: dict, tool_name: str, tool_args: dict = None) -> None:
    """Save tool as approved for this session.

    User approvals are tool-level, not command-specific.
    If user approves "bash npm", they approve ALL bash commands.

    Examples:
        tool_name="bash" → saves: {'bash': {allowed: True, source: 'user'}}
        tool_name="write" → saves: {'write': {allowed: True, source: 'user'}}
    """
    if 'permissions' not in session:
        session['permissions'] = {}

    permission = {
        'allowed': True,
        'source': 'user',
        'reason': 'approved for session',
        'expires': {'type': 'session_end'}
    }

    session['permissions'][tool_name] = permission


def _resolve_display_name(tool_name: str, args_str: str) -> str:
    """Resolve display name from tool name and JSON arguments string.

    Returns just the tool name. Command-specific details shown in arguments.
    Examples: "bash", "write", "edit"
    """
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


def matches_permission_pattern(tool_name: str, tool_args: dict, pattern: str) -> bool:
    """Check if tool call matches allowed pattern.

    Pattern types:
    - "read_file" - Tool name only (matches any args)
    - "Bash(git status)" - Exact command match
    - "Bash(git diff *)" - Command with wildcard
    - "Bash(git *)" - All commands starting with "git"

    Args:
        tool_name: Tool name (e.g., "bash")
        tool_args: Tool arguments dict
        pattern: Allowed pattern

    Returns:
        True if tool matches pattern
    """
    # Pattern: "tool_name" - matches tool name only
    if pattern == tool_name:
        return True

    # Pattern: "Bash(command pattern)" - matches bash commands
    if pattern.startswith('Bash(') and pattern.endswith(')'):
        if tool_name.lower() != 'bash':
            return False

        cmd_pattern = pattern[5:-1]  # Extract "git status" from "Bash(git status)"
        actual_cmd = tool_args.get('command', '')

        # Exact match: "git status" == "git status"
        if cmd_pattern == actual_cmd:
            return True

        # Wildcard match: "git diff *" matches "git diff --staged"
        if cmd_pattern.endswith(' *'):
            prefix = cmd_pattern[:-2]  # Remove " *"
            if actual_cmd.startswith(prefix):
                return True

        # Wildcard match: "git *" matches "git status"
        if cmd_pattern == actual_cmd.split()[0] + ' *':
            return True

    return False


# =============================================================================
# Event Handlers
# =============================================================================

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
            # matches_permission_pattern is from skills plugin - handles pattern matching
            # for both simple tools ("read") and bash patterns ("Bash(git status)")
            # Pattern matching moved here from skills plugin
            import fnmatch

            # =============================================================
            # Bash command chains need special handling
            # =============================================================
            # Example: "git status && ls -la" contains TWO commands
            # We must check that BOTH git AND ls are permitted
            # This prevents sneaking in dangerous commands via chaining
            if tool_name == 'bash' and 'command' in tool_args:
                # Check if ALL commands in chain are permitted
                permitted, reason, source = check_bash_chain_permitted(tool_args['command'], permissions)
                if permitted:
                    if hasattr(agent, 'logger') and agent.logger and hasattr(agent.logger, 'console'):
                        agent.logger.console.log_permission_granted('bash', tool_args, source, reason)
                    return

            # Check each permission in the dict
            for pattern, perm in permissions.items():
                if not perm.get('allowed'):
                    continue

                # First check basic pattern match (tool name or Bash command)
                if matches_permission_pattern(tool_name, tool_args, pattern):
                    # Check if there's a 'when' field for parameter-level matching
                    when_config = perm.get('when')
                    if when_config:
                        # Parameter matching - all conditions must match
                        all_match = True
                        for param_name, param_pattern in when_config.items():
                            actual_value = tool_args.get(param_name, '')
                            # Use fnmatch for glob pattern matching
                            if not fnmatch.fnmatch(str(actual_value), str(param_pattern)):
                                all_match = False
                                break

                        if not all_match:
                            continue  # This permission doesn't match, try next

                    # Pattern matched (and params matched if 'when' field exists)
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
            _save_session_approval(agent.current_session, approval_key, tool_args)
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


@after_user_input
def load_config_permissions(agent: 'Agent') -> None:
    """Load permissions from host.yaml into session after user input.

    Always loads template permissions first (safe tools), then merges
    project-specific config on top. This ensures safe tools are always
    available even with custom configs.

    Uses unified permission structure with source='config' or source='safe'.
    Runs after user input so session is guaranteed to exist.
    Only loads once per session (first input).
    """
    import yaml

    # Only load once per session
    if 'permissions' in agent.current_session and 'permissions_source' in agent.current_session:
        return

    # Initialize permissions dict
    if 'permissions' not in agent.current_session:
        agent.current_session['permissions'] = {}

    # Always load template permissions first (safe tools)
    template_path = Path(__file__).parent.parent.parent / 'network' / 'host' / 'host.yaml'
    if template_path.exists():
        with open(template_path, 'r', encoding='utf-8') as f:
            template_config = yaml.safe_load(f) or {}
        template_permissions = template_config.get('permissions')
        if template_permissions and isinstance(template_permissions, dict):
            # Convert Bash() patterns in template too
            converted_template = {}
            for pattern, perm in template_permissions.items():
                if pattern.startswith('Bash(') and pattern.endswith(')'):
                    command_pattern = pattern[5:-1]
                    converted_template['bash'] = {
                        **perm,
                        'when': {'command': command_pattern}
                    }
                else:
                    converted_template[pattern] = perm
            agent.current_session['permissions'].update(converted_template)

    # Then load project-specific config (if exists) and merge on top
    co_dir = Path.cwd() / '.co'
    host_yaml = co_dir / 'host.yaml'

    if host_yaml.exists():
        with open(host_yaml, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f) or {}

        permissions_config = config.get('permissions')
        if permissions_config and isinstance(permissions_config, dict):
            # Convert Bash() patterns to 'when' format for runtime consistency
            converted_permissions = {}
            for pattern, perm in permissions_config.items():
                # Convert "Bash(git status)" → "bash" with when: {command: "git status"}
                if pattern.startswith('Bash(') and pattern.endswith(')'):
                    command_pattern = pattern[5:-1]  # Extract "git status" from "Bash(git status)"
                    converted_permissions['bash'] = {
                        **perm,
                        'when': {'command': command_pattern}
                    }
                else:
                    # Keep as-is for non-Bash patterns
                    converted_permissions[pattern] = perm

            # Merge converted permissions (overrides template, but preserve user approvals)
            for key, perm in converted_permissions.items():
                # Don't overwrite user approvals
                existing = agent.current_session['permissions'].get(key, {})
                if existing.get('source') != 'user':
                    agent.current_session['permissions'][key] = perm
            agent.current_session['permissions_source'] = str(host_yaml.name)

            # Log where permissions were loaded from (once, at startup)
            if hasattr(agent, 'logger') and agent.logger and hasattr(agent.logger, 'console'):
                count = len(permissions_config)
                agent.logger.console.print(
                    f"[dim]Loaded {count} permission(s) from {host_yaml.name}[/dim]"
                )
    else:
        # No project config, using template only
        agent.current_session['permissions_source'] = 'template'


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
            from ..ulw import handle_ulw_mode_change
            handle_ulw_mode_change(agent, msg.get('turns'))


# =============================================================================
# Utility Functions
# =============================================================================

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

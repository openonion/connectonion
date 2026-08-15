"""
Purpose: Orchestrate WebSocket-based tool approval with permission-profile validation
LLM-Note:
  Dependencies: imports from [../../core/events.py (before_each_tool, before_iteration, after_user_input), ./constants.py (VALID_PERMISSION_PROFILES, FILE_EDIT_TOOLS), ./bash_parser.py (check_bash_chain_permitted), ../skills.py (matches_permission_pattern), pathlib.Path, typing.TYPE_CHECKING] | imported by [tool_approval/__init__.py] | tested by [tests/unit/test_tool_approval.py, tests/integration/test_config_permissions.py, tests/unit/test_shell_approval.py]
  Data flow: after_user_input → load_config_permissions() loads .co/host.yaml permissions into session['permissions'] | before_iteration → poll_mode_changes() checks for mode_change messages | before_each_tool → check_approval() validates tool against mode+permissions → if unpermitted with live IO: agent.io.send(approval_needed) → agent.io.receive() blocks for client response → if approved: return (execute tool) | if rejected: raise ValueError (LLM sees rejection message)
  State/Effects: modifies session['permissions'] (permission cache), session['approval']['approved_tools'] (session-scoped approvals), session['mode'] (the durable permission profile compatibility field) | reads .co/host.yaml file | writes to agent.logger for approval logs | sends WebSocket messages via agent.io | blocks execution waiting for user approval
  Integration: exposes check_approval (before_each_tool hook), load_config_permissions (after_user_input hook), poll_mode_changes (before_iteration compatibility hook), handle_permission_profile_change(agent, profile), get_current_permission_profile(agent) | uses agent.io.send/receive for client communication | integrates with skills plugin for permission matching | integrates with full_access plugin for bounded Full access handling
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

Permission profiles (stored in session['mode'] for wire compatibility):
    :read-only:
        - Explicitly permitted tools are auto-approved
        - Every remaining tool needs approval when live IO is present
        - Used for: normal coding assistance

    :workspace:
        - File edit tools: auto-approved (write, edit, multi_edit)
        - Every other unpermitted tool needs approval
        - Used for: rapid editing with approval only for risky ops

    :danger-full-access (handled by full_access plugin):
        - Sets skip_tool_approval=True → bypasses all checks
        - Used for: trusted operator sessions with bounded autonomous checkpoints

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
        - "mode": Profile-specific auto-approvals (`:workspace`)

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
    handle_permission_profile_change(agent, profile) → changes the profile, logs transition
    get_current_permission_profile(agent) → returns the canonical profile string

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

from pathlib import Path
from typing import TYPE_CHECKING

from ...core.approval_modes import (
    DANGER_FULL_ACCESS_PERMISSION_PROFILE,
    READ_ONLY_PERMISSION_PROFILE,
    WORKSPACE_PERMISSION_PROFILE,
    has_valid_full_access_grant,
    legacy_permission_profile_id,
)
from ...core.events import after_iteration, after_user_input, before_each_tool, before_iteration
from ...project import project_co_dir
from .bash_parser import check_bash_chain_permitted
from .constants import (
    FILE_EDIT_TOOLS,
    VALID_PERMISSION_PROFILES,
)

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
    """Get and immediately canonicalize the current permission profile.

    Modes:
        ':read-only': Unpermitted tools need approval
        ':workspace': Named file edits are auto-approved
    """
    raw_profile = agent.current_session.get(
        'mode', READ_ONLY_PERMISSION_PROFILE
    )
    if raw_profile == 'plan':
        profile = READ_ONLY_PERMISSION_PROFILE
    else:
        try:
            profile = legacy_permission_profile_id(raw_profile)
        except ValueError:
            profile = READ_ONLY_PERMISSION_PROFILE
    agent.current_session['mode'] = profile
    return profile


def _requester_is_operator(agent: 'Agent') -> bool:
    """Whether this session may select a mode that bypasses approvals."""
    requester = agent.current_session.get('requester')
    return not requester or requester.get('level') == 'admin'


def _set_mode(agent: 'Agent', mode: str) -> None:
    """Set a bounded permission profile and notify the frontend."""
    try:
        profile = legacy_permission_profile_id(mode)
    except ValueError:
        profile = READ_ONLY_PERMISSION_PROFILE
    if profile not in VALID_PERMISSION_PROFILES:
        profile = READ_ONLY_PERMISSION_PROFILE
    agent.current_session['mode'] = profile
    # Notify frontend of mode change
    if agent.io:
        agent.io.send({
            'type': 'mode_changed',
            'mode': profile,
            'triggered_by': 'agent',
        })


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

        # Wildcard match: "git diff *" matches "git diff --staged" (and bare
        # "git diff"), but NOT "git difftool". Require a word boundary after the
        # prefix so "git *" cannot match an unrelated binary like "gitleaks".
        if cmd_pattern.endswith(' *'):
            prefix = cmd_pattern[:-2]  # Remove " *"
            if actual_cmd == prefix or actual_cmd.startswith(prefix + ' '):
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
    """Check if a tool is allowed by the current permission profile.

    Mode behavior:
        ':read-only': Every unpermitted tool needs approval with live IO
        ':workspace': Named file edits are automatic; other calls still ask

    The explicit full_access mode bypasses checks only for the local/admin operator.

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

        # Before the whitelist, and before the mode: these decide what this
        # agent may do and who may command it, so no configuration grants them.
        # is_tool_permitted has the same guard, but this is the path the agent's
        # own turn takes -- that function is for callers outside the LLM loop,
        # and a guard added only there would have left the case #722 is about
        # untouched. Two copies of the matching already live in this file; this
        # comment is here so the third does not go unnoticed.
        refusal = _refuse_control_file(tool_name, tool_args)
        if refusal:
            raise ValueError(refusal)

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
                    if getattr(getattr(agent, 'logger', None), 'console', None):
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
                    if getattr(getattr(agent, 'logger', None), 'console', None):
                        agent.logger.console.log_permission_granted(tool_name, tool_args, source, reason)
                    return

    # =================================================================
    # Canonicalize restored legacy state before any authority check.
    mode = _get_mode(agent)

    # Check the explicit Full access profile (local/admin operator only)
    # =================================================================
    requester_is_operator = _requester_is_operator(agent)
    if has_valid_full_access_grant(agent.current_session) and requester_is_operator:
        pending = agent.current_session.get('pending_tool')
        tool_name = pending['name'] if pending else 'unknown'
        tool_args = pending.get('arguments', {}) if pending else {}
        if getattr(getattr(agent, 'logger', None), 'console', None):
            agent.logger.console.log_permission_granted(tool_name, tool_args, 'mode', 'full_access mode')
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
    # =================================================================
    # PROFILE: :workspace - edits auto-approved, others need approval
    # =================================================================
    if mode == WORKSPACE_PERMISSION_PROFILE:
        if tool_name in FILE_EDIT_TOOLS and requester_is_operator:
            if getattr(getattr(agent, 'logger', None), 'console', None):
                agent.logger.console.log_permission_granted(
                    tool_name, tool_args, 'profile', ':workspace'
                )
            return
        # Every other unpermitted tool falls through to approval logic.

    # =================================================================
    # Fail closed: every remaining live-IO tool needs approval
    # =================================================================
    # The dialog belongs to the authenticated actor running this session
    # =================================================================
    # Placed here, at the one line that is about to prompt — not earlier. An
    # earlier check refused `read_file` for a contact, which gates access
    # rather than approval and makes the agent useless to the people it was
    # shared with. Only a call that would have opened the dialog is affected.
    #
    # The host knows who is on this socket: CONNECT is signed and the trust
    # layer classified them before the session existed. An accepted invite is
    # the normal B2B user grant, so contacts must be able to approve ordinary
    # work in their own session. Admin status is reserved for the control plane
    # (trust mutation, deployment/configuration and privileged inspection).
    #
    # No requester recorded means the session did not arrive through the host —
    # a local `co ai` run — and behaves as before.
    requester = agent.current_session.get('requester')
    if requester and requester.get('level') not in {'contact', 'whitelist', 'admin'}:
        raise ValueError(
            f"{tool_name} needs approval from an authenticated contact or "
            f"admin. This requester is {requester.get('level', 'unknown')}."
        )

    # Get approval key for this tool
    approval_key = _get_approval_key(tool_name, tool_args)

    # Get remaining tools in this batch for client context
    pending = agent.current_session.get('pending_tool')
    tool_id = pending.get('id', '') if pending else ''
    batch_remaining = _get_batch_remaining(agent, tool_id)

    # Send approval request to client
    approval_msg = {
        'type': 'approval_needed',
        'tool_call_id': tool_id,
        'tool': approval_key,
        'arguments': tool_args,
        'description': tool_args.get('description', ''),
    }
    if batch_remaining:
        approval_msg['batch_remaining'] = batch_remaining

    # Checkpoint before blocking (enables reconnection recovery)
    if agent.storage:
        agent.storage.checkpoint(agent.current_session)

    agent.io.send(approval_msg)

    # Wait for client response (BLOCKS)
    response = agent.io.receive()

    if response.get('type') == 'INTERRUPT':
        agent.current_session['stop_signal'] = 'Interrupted by user'
        _log(agent, f"[yellow]⚠ {tool_name} - interrupted by user[/yellow]")
        from ...core.interrupt import UserInterrupt
        raise UserInterrupt()

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


def _convert_permission_patterns(raw: dict) -> dict:
    """Normalize a raw host.yaml permissions dict.

    A "Bash(cmd)" key keeps its form but gains when={command: cmd} so runtime
    matching can fnmatch the actual command. Simple tool-name keys pass through.
    """
    converted = {}
    for pattern, perm in raw.items():
        if pattern.startswith('Bash(') and pattern.endswith(')'):
            converted[pattern] = {**perm, 'when': {'command': pattern[5:-1]}}
        else:
            converted[pattern] = perm
    return converted


def load_permission_patterns(co_dir=None) -> dict:
    """Load the merged permission whitelist: template safe defaults + project host.yaml.

    Returns the same dict shape used in session['permissions']. This shared
    whitelist is honored both by the session approval flow and direct network
    EXEC. A specialized local agent may add narrower loop-only permissions after
    loading it; those grants deliberately do not enter remote EXEC.

    Args:
        co_dir: Project .co directory (default: cwd/.co). The template defaults
                always load; the project host.yaml merges on top.
    """
    import yaml

    permissions = {}

    template_path = Path(__file__).parent.parent.parent / 'network' / 'host' / 'host.yaml'
    if template_path.exists():
        with open(template_path, 'r', encoding='utf-8') as f:
            template_config = yaml.safe_load(f) or {}
        template_permissions = template_config.get('permissions')
        if template_permissions and isinstance(template_permissions, dict):
            permissions.update(_convert_permission_patterns(template_permissions))

    co_dir = Path(co_dir) if co_dir else project_co_dir()
    host_yaml = co_dir / 'host.yaml'
    if host_yaml.exists():
        with open(host_yaml, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f) or {}
        permissions_config = config.get('permissions')
        if permissions_config and isinstance(permissions_config, dict):
            for key, perm in _convert_permission_patterns(permissions_config).items():
                # Project config overrides template, but never clobbers a
                # user-granted approval.
                if permissions.get(key, {}).get('source') != 'user':
                    permissions[key] = perm

    return permissions


# The files that decide what this agent may do and who may command it. An
# operator who whitelists `write` — which every coding agent needs — was also
# handing over these, and `load_config_permissions()` reads the first one back
# as the whitelist. So a prompt-injected turn could write itself `Bash(*)` and
# every later turn, in every later session, was unrestricted (#722).
#
# Not all of `.co/`: agents write `dashboard.html` on purpose — it *is* the Home
# page, built by the dashboard skill — and logs, docs and skills are content
# too. The line is what a file decides, not where it lives.
CONTROL_FILES = ("host.yaml", "schedule.yaml", "admins.txt")
CONTROL_DIRS = ("keys",)


def _is_control_file(path: str) -> bool:
    """True if this path is one of the agent's own control files.

    Compared on the normalised path so `./co/..`, `../.co/x` and an absolute
    path all reach the same answer — a check that only matches the tidy
    spelling is a check with a published bypass.
    """
    import os

    normalised = os.path.normpath(str(path)).replace(os.sep, "/")
    parts = normalised.split("/")
    if CO_DIR_NAME not in parts:
        return False
    tail = parts[parts.index(CO_DIR_NAME) + 1:]
    if not tail:
        return False
    return tail[0] in CONTROL_FILES or tail[0] in CONTROL_DIRS


CO_DIR_NAME = ".co"


def _refuse_control_file(tool_name: str, tool_args: dict):
    """The reason this call may not touch the agent's own control files, or None.

    Shared by the two places that decide whether a tool may run: this module's
    `check_approval` (the agent's own turn) and `is_tool_permitted` (network
    EXEC and anything else outside the loop).
    """
    for key in ("file_path", "path", "target", "filename"):
        candidate = tool_args.get(key)
        if candidate and _is_control_file(candidate):
            return (f"{Path(str(candidate)).name} decides what this agent may do — "
                    f"the agent does not get to write it")

    if tool_name == 'bash' and 'command' in tool_args:
        command = str(tool_args['command'])
        if any(_is_control_file(word.strip("'\"")) for word in command.split()):
            return ("this command names a file that decides what this agent may do")
    return None


def is_tool_permitted(tool_name: str, tool_args: dict, permissions: dict) -> tuple[bool, str]:
    """Check one tool call against a permission whitelist. Returns (allowed, reason).

    Same matching the LLM approval flow uses in check_approval: bash command
    chains require every subcommand permitted; other tools match by name (and
    'when' parameter globs). Callers that run tools outside the LLM loop (network
    EXEC) use this so direct execution honors exactly the host.yaml whitelist.
    """
    import fnmatch

    if not permissions:
        return False, "no permissions configured"

    # Before the whitelist, not through it: these are refused however generously
    # the operator configured file writing, because they are what "how
    # generously" is stored in.
    refusal = _refuse_control_file(tool_name, tool_args)
    if refusal:
        return False, refusal

    # A speed bump for bash, not a boundary — and worth being exact about which.
    # It catches a control path written literally (`> .co/host.yaml`). It does
    # not catch `cd .co && echo x > host.yaml`, and nothing word-shaped can:
    # reaching that would mean interpreting the shell.
    #
    # What actually bounds bash is the operator's own whitelist. `Bash(*)` has
    # already granted everything, and this does not take it back. The complete
    # protection here is for the file tools above, where the path is an argument
    # rather than a string to be interpreted.

    # Bash chains: every subcommand in "a && b | c" must be individually
    # permitted. This is AUTHORITATIVE for bash — we never fall through to the
    # generic loop below, because a pattern like "Bash(co *)" would otherwise
    # prefix-match the whole chain string ("co status && rm -rf /") and wrongly
    # permit the dangerous half. Per-subcommand matching is the only safe check.
    if tool_name == 'bash' and 'command' in tool_args:
        permitted, reason, _ = check_bash_chain_permitted(tool_args['command'], permissions)
        return (True, reason or "permitted") if permitted else (False, "command not in the permission whitelist")

    for pattern, perm in permissions.items():
        if not perm.get('allowed'):
            continue
        if matches_permission_pattern(tool_name, tool_args, pattern):
            when_config = perm.get('when')
            if when_config:
                all_match = True
                for param_name, param_pattern in when_config.items():
                    actual_value = tool_args.get(param_name, '')
                    if not fnmatch.fnmatch(str(actual_value), str(param_pattern)):
                        all_match = False
                        break
                if not all_match:
                    continue
            return True, perm.get('reason', 'allowed')

    return False, f"'{tool_name}' is not in the permission whitelist"


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
    # Only load once per session
    if 'permissions' in agent.current_session and 'permissions_source' in agent.current_session:
        return

    # Reuse the shared loader — template safe defaults + project host.yaml —
    # so the session flow and direct EXEC honor one whitelist.
    co_dir = project_co_dir()
    host_yaml = co_dir / 'host.yaml'
    loaded = load_permission_patterns(co_dir)

    existing = agent.current_session.get('permissions', {})
    # Preserve any user-granted approvals already in the session.
    for key, perm in loaded.items():
        if existing.get(key, {}).get('source') != 'user':
            existing[key] = perm
    agent.current_session['permissions'] = existing

    if host_yaml.exists():
        agent.current_session['permissions_source'] = str(host_yaml.name)
        if hasattr(agent, 'logger') and agent.logger and getattr(agent.logger, 'console', None):
            agent.logger.console.print(
                f"[dim]Loaded {len(loaded)} permission(s) from {host_yaml.name}[/dim]"
            )
    else:
        agent.current_session['permissions_source'] = 'template'


@before_iteration
def poll_mode_changes(agent: 'Agent') -> None:
    """Poll compatibility ``mode_change`` frames at iteration start.

    Handles Read only, Auto, Full access, and a legacy Plan request. New clients
    use the Host-acknowledged OIP permission-profile transaction instead.
    """
    if agent.current_session.get('mode') == 'plan':
        handle_permission_profile_change(agent, 'plan')

    if (
        not _requester_is_operator(agent)
        and _get_mode(agent) != READ_ONLY_PERMISSION_PROFILE
    ):
        handle_permission_profile_change(agent, READ_ONLY_PERMISSION_PROFILE)

    if not agent.io:
        return

    for msg in agent.io.receive_all('mode_change'):
        requested_profile = msg.get('mode')
        if requested_profile == 'plan':
            handle_permission_profile_change(agent, requested_profile)
            continue
        try:
            profile = legacy_permission_profile_id(requested_profile)
        except ValueError:
            continue
        if profile in VALID_PERMISSION_PROFILES:
            handle_permission_profile_change(agent, profile)
        elif profile == DANGER_FULL_ACCESS_PERMISSION_PROFILE:
            if _requester_is_operator(agent):
                from ..full_access import handle_full_access_permission_profile_change
                try:
                    handle_full_access_permission_profile_change(agent, msg.get('turns'))
                except ValueError:
                    _set_mode(agent, READ_ONLY_PERMISSION_PROFILE)
                    _log(agent, "[yellow]Full access requires a positive integer turn budget[/yellow]")
            else:
                _set_mode(agent, READ_ONLY_PERMISSION_PROFILE)
                _log(agent, "[yellow]Only the operator can enable Full access[/yellow]")


@after_iteration
def poll_interrupt(agent: 'Agent') -> None:
    """Stop the run at the iteration boundary when the client sent an INTERRUPT.

    Graceful stop: drains an INTERRUPT frame and sets the existing stop_signal,
    which the iteration loop already honors right after after_iteration (halts and
    returns a closing message). Runs after_iteration so the current step (LLM call
    + tools) finishes first — not a mid-flight abort. Same primitive and placement
    as no_progress_guard; no core changes.
    """
    if not agent.io:
        return

    if agent.io.receive_all('INTERRUPT'):
        agent.current_session['stop_signal'] = 'user_interrupt'


# =============================================================================
# Utility Functions
# =============================================================================

def handle_permission_profile_change(agent: 'Agent', profile: str) -> None:
    """Handle a permission-profile request from a compatibility frame.

    Called when frontend sends { type: 'mode_change', mode: '...' }
    Handles Read only and Auto. Legacy Plan requests fall back to Read only so
    old frontends cannot leave the backend in a local workflow state with no exit.
    Full access is handled by its bounded-grant plugin.

    Args:
        agent: Agent instance
        profile: Canonical permission profile or legacy boundary value
    """
    requested_profile = profile
    if profile == 'plan':
        profile = READ_ONLY_PERMISSION_PROFILE
    else:
        try:
            profile = legacy_permission_profile_id(profile)
        except ValueError:
            return

    if profile == WORKSPACE_PERMISSION_PROFILE and not _requester_is_operator(agent):
        _set_mode(agent, READ_ONLY_PERMISSION_PROFILE)
        _log(agent, "[yellow]Only the operator can enable Auto[/yellow]")
        return

    if profile not in VALID_PERMISSION_PROFILES:
        # Full access is handled by the bounded-grant plugin.
        return

    old_profile = _get_mode(agent)
    if old_profile == profile:
        if requested_profile == 'plan':
            _set_mode(agent, profile)
        return

    # Clear skip_tool_approval when switching to a mode we handle
    agent.current_session.pop('skip_tool_approval', None)

    _set_mode(agent, profile)
    if requested_profile == 'plan':
        _log(agent, f"[cyan]Legacy Plan permission request is unavailable; changed: {old_profile} → {profile}[/cyan]")
    else:
        _log(agent, f"[cyan]Permission profile changed: {old_profile} → {profile}[/cyan]")


def handle_mode_change(agent: 'Agent', mode: str) -> None:
    """Deprecated alias for :func:`handle_permission_profile_change`."""
    handle_permission_profile_change(agent, mode)


def get_current_mode(agent: 'Agent') -> str:
    """Deprecated alias for :func:`get_current_permission_profile`."""
    return get_current_permission_profile(agent)


def get_current_permission_profile(agent: 'Agent') -> str:
    """Get the current canonical permission profile."""
    return _get_mode(agent)

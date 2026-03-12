"""
Purpose: WebSocket-based tool approval plugin with mode system and unified permissions
LLM-Note:
  Dependencies: imports from [./approval.py (check_approval, load_config_permissions, poll_mode_changes, handle_mode_change, get_current_mode), ./constants.py (VALID_MODES, DEFAULT_MODE)] | imported by [../.__init__.py useful_plugins package, cli/co_ai/agent.py, cli/templates/minimal/agent.py, ulw.py, skills.py] | tested by [tests/unit/test_tool_approval.py, tests/integration/test_config_permissions.py, tests/integration/test_bash_chain_permissions.py]
  Data flow: agent loads plugin → [load_config_permissions, poll_mode_changes, check_approval] registered as event handlers → after_user_input fires → load_config_permissions() loads .co/host.yaml → before_iteration fires → poll_mode_changes() checks WebSocket → before_each_tool fires → check_approval() validates tool → if dangerous: WebSocket approval protocol → if approved: tool executes | if rejected: ValueError raised
  State/Effects: exports tool_approval plugin list | exports utility functions handle_mode_change, get_current_mode | no module state
  Integration: exposes tool_approval (list of 3 event handlers), handle_mode_change(agent, mode), get_current_mode(agent), VALID_MODES, DEFAULT_MODE | used by Agent(plugins=[tool_approval]) | integrates with co ai CLI for WebSocket-based coding agent
  Performance: plugin registration is O(1) | event handler overhead per tool call depends on approval.py check_approval()
  Errors: no errors at import time | errors from approval.py bubble up during agent execution

Tool Approval Plugin - Request client approval before executing dangerous tools.

WebSocket-only. Uses io.send/receive pattern:
1. Sends {type: "approval_needed", tool, arguments} to client
2. Blocks until client responds with {approved: bool, scope?, feedback?, mode?}
3. If approved: execute tool (optionally save to session memory)
4. If rejected: raise ValueError, LLM sees rejection message

Rejection Modes (client sends mode field):
- "reject_soft": Skip this tool, loop continues. LLM gets hint to use ask_user.
- "reject_hard" (default): Skip remaining batch, stop loop, wait for user input.
- "reject_explain": Like soft, but instructs LLM to explain in simple terms.

Tool Classification:
- Safe tools (read, glob, grep, etc.) - defined in host.yaml template, auto-approved
- DANGEROUS_TOOLS: Write/execute operations (bash, write, edit, etc.) - need approval
- Unknown tools: Treated as safe (no approval needed)

Mode System:
- "safe" (default): Dangerous tools need approval
- "plan": Read-only only, exit_plan_mode needs approval (shows plan)
- "accept_edits": File edits auto-approved, other dangerous tools need approval
- "ulw": Handled by ulw plugin - bypasses all approvals

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

Plugin Structure:
    tool_approval = [load_config_permissions, poll_mode_changes, check_approval]
        - 3 event handlers registered automatically
        - load_config_permissions: after_user_input (loads .co/host.yaml)
        - poll_mode_changes: before_iteration (checks WebSocket for mode changes)
        - check_approval: before_each_tool (validates + requests approval)

Architecture - Unified Permission System Lifecycle:

    ┌─────────────────────────────────────────────────────────────────────────┐
    │ UNIFIED PERMISSION STRUCTURE (session['permissions'])                   │
    │                                                                         │
    │ All permissions use same unified format:                                │
    │                                                                         │
    │ permissions = {                                                         │
    │   'bash': {                           # With 'when' field (config)     │
    │     'allowed': True,                                                    │
    │     'source': 'config',                                                 │
    │     'reason': 'Pre-approved git commands',                              │
    │     'when': {'command': 'git status'},  # Granular matching            │
    │     'expires': {'type': 'never'}                                        │
    │   },                                                                    │
    │   'bash': {                           # Without 'when' (user approval) │
    │     'allowed': True,                                                    │
    │     'source': 'user',                                                   │
    │     'reason': 'approved for session',                                   │
    │     'expires': {'type': 'session_end'}                                  │
    │   },                                                                    │
    │   'read_file': {                      # Simple tool (safe)             │
    │     'allowed': True,                                                    │
    │     'source': 'safe',                                                   │
    │     'expires': {'type': 'never'}                                        │
    │   }                                                                     │
    │ }                                                                       │
    │                                                                         │
    │ Note: User approvals are tool-level. Approving "bash npm" means        │
    │ approving ALL bash commands for the session.                            │
    └─────────────────────────────────────────────────────────────────────────┘

    ┌─────────────────────────────────────────────────────────────────────────┐
    │ PERMISSION LIFECYCLE                                                    │
    │                                                                         │
    │ 1. SESSION START (@after_user_input)                                    │
    │    load_config_permissions()                                            │
    │    ├─ Read .co/host.yaml                                                │
    │    ├─ Convert Bash(git status) → unified format:                        │
    │    │  {'bash': {when: {command: 'git status'}, source: 'config'}}      │
    │    └─ Load safe tools from template                                     │
    │                                                                         │
    │ 2. SKILL INVOCATION (@after_user_input when /skill detected)           │
    │    skills._grant_skill_permissions()                                    │
    │    ├─ Snapshot current permissions                                      │
    │    ├─ Convert patterns to unified format:                               │
    │    │  Bash(git diff *) → {'bash': {when: {command: 'git diff *'},      │
    │    │                              source: 'skill', expires: turn_end}}  │
    │    └─ Merge with session (user approvals preserved)                     │
    │                                                                         │
    │ 3. TOOL EXECUTION (@before_each_tool)                                   │
    │    check_approval()                                                     │
    │    ├─ Check skip flags (no_io, skip_tool_approval)                      │
    │    ├─ Check mode (safe/plan/accept_edits)                               │
    │    ├─ Iterate permissions dict:                                         │
    │    │  ├─ matches_permission_pattern(tool_name, args, key)               │
    │    │  │  - For 'bash': matches tool name                                │
    │    │  │  - For 'Bash(git status)': parses pattern                       │
    │    │  └─ Check 'when' field (granular parameter matching):              │
    │    │     - when: {command: 'git *'} → fnmatch(actual, pattern)         │
    │    │     - when: {path: '*.md'} → fnmatch(actual_path, '*.md')         │
    │    ├─ If bash: check_bash_chain_permitted()                             │
    │    │  └─ Returns (permitted, reason, source) from matched permission    │
    │    ├─ If not permitted: WebSocket approval request                      │
    │    └─ If user approves: _save_session_approval()                        │
    │       └─ Save as 'bash' (tool-level approval, all commands allowed)    │
    │                                                                         │
    │ 4. TURN END (@before_iteration)                                         │
    │    skills.cleanup_scope()                                               │
    │    ├─ Remove permissions where expires.type == 'turn_end'               │
    │    └─ Restore snapshot (remove skill permissions, keep user)            │
    │                                                                         │
    │ 5. SESSION END                                                          │
    │    ├─ Clear all permissions                                             │
    │    └─ User approvals (scope='session') are lost                         │
    └─────────────────────────────────────────────────────────────────────────┘

    ┌─────────────────────────────────────────────────────────────────────────┐
    │ PERMISSION SOURCES                                                      │
    │                                                                         │
    │ SOURCE      KEY PATTERN       WHEN FIELD         EXPIRES               │
    │ ──────────────────────────────────────────────────────────────────────  │
    │ config      'bash'            {command: '...'}   never                  │
    │ safe        'read_file'       none               never                  │
    │ skill       'bash'            {command: '...'}   turn_end               │
    │ user        'bash'            none               session_end            │
    │ mode        tool names        none               never                  │
    └─────────────────────────────────────────────────────────────────────────┘

    ┌─────────────────────────────────────────────────────────────────────────┐
    │ KEY FUNCTIONS                                                           │
    │                                                                         │
    │ matches_permission_pattern(tool_name, args, pattern)                    │
    │ ├─ Pattern: 'bash' → matches tool name                                  │
    │ ├─ Pattern: 'Bash(git status)' → parses command, checks match          │
    │ ├─ Pattern: 'Bash(git *)' → wildcard matching                           │
    │ └─ Returns: bool                                                        │
    │                                                                         │
    │ check_bash_chain_permitted(command, permissions)                        │
    │ ├─ Extracts all commands from chain: "git status && ls"                 │
    │ ├─ Validates EACH command has permission                                │
    │ ├─ Gets source from permission that matched                             │
    │ └─ Returns: (permitted, reason, source)                                 │
    └─────────────────────────────────────────────────────────────────────────┘

Integration with other plugins:
    - skills plugin: grants turn-scoped permissions, snapshots/restores
    - ulw plugin: sets skip_tool_approval=True to bypass all checks
    - tool_approval: owns matches_permission_pattern() for validation
    - co_ai CLI: includes tool_approval by default for WebSocket agent

File Relationships:
    tool_approval/
    ├── __init__.py          # THIS FILE - plugin export + public API
    ├── approval.py          # Core logic + event handlers
    ├── constants.py         # Tool classification + modes
    └── bash_parser.py       # Bash chain validation

    Flow: Agent(plugins=[tool_approval])
          → registers 3 event handlers
          → events fire during agent execution
          → approval.py handles WebSocket protocol
"""

from .approval import (
    check_approval,
    load_config_permissions,
    poll_mode_changes,
    handle_mode_change,
    get_current_mode,
)
from .constants import VALID_MODES, DEFAULT_MODE

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

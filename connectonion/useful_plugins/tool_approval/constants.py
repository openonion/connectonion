"""
Purpose: Define tool classification and mode constants for approval system
LLM-Note:
  Dependencies: no imports | imported by [tool_approval/approval.py, tool_approval/__init__.py] | tested by [tests/unit/test_tool_approval.py, tests/integration/test_config_permissions.py]
  Data flow: provides read-only constants → consumed by approval.py check_approval() and callers → identifies modes, named edit tools, command tools, and known effectful tools
  State/Effects: no state | no side effects | pure constant definitions
  Integration: exposes VALID_MODES, DEFAULT_MODE, DANGEROUS_TOOLS, FILE_EDIT_TOOLS, COMMAND_TOOLS sets | approval.py uses modes, edit tools, and command tools; DANGEROUS_TOOLS remains public compatibility metadata
  Performance: O(1) set membership checks for tool classification
  Errors: none (constants cannot fail)

Constants Overview:
    VALID_MODES = {'safe', 'accept_edits'}
        - safe: unpermitted tools need approval (default)
        - accept_edits: named file edits auto-approved

    DANGEROUS_TOOLS: known effectful tools kept as a public reference set
    FILE_EDIT_TOOLS: write, edit, multi_edit (subset of DANGEROUS)
    COMMAND_TOOLS: bash, shell, run (approval is per-command-name)

Tool Classification:
    Permitted tools: supplied by template, config, skills, or the user → auto-approved
    Unpermitted tools: require approval with live IO, including unclassified tools
    File edit tools: FILE_EDIT_TOOLS set → auto-approved in accept_edits mode
    Command tools: COMMAND_TOOLS set → tool-level approval (approving "bash" approves all)
"""

# =============================================================================
# MODE SYSTEM
# =============================================================================
# Two modes control approval behavior:
#   - 'safe' (default): Unpermitted tools need approval
#   - 'accept_edits': File edit tools auto-approved, other unpermitted tools need approval
#
# Other modes (handled by separate plugins via skip_tool_approval flag):
#   - 'ulw': Handled by ulw plugin - sets skip_tool_approval=True
#
# Mode can be changed by the user via WebSocket
# { type: 'mode_change', mode: '...' }.
# =============================================================================

VALID_MODES = {'safe', 'accept_edits'}
DEFAULT_MODE = 'safe'


# Known tools that modify files, execute code, or have external effects.
#
# This public set is retained for compatibility and discoverability. It is not
# the security boundary: check_approval() requires approval for every tool that
# lacks an explicit permission when live IO is present.
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
}

# File edit tools - auto-approved in 'accept_edits' mode
# These tools only modify files, no external side effects.
FILE_EDIT_TOOLS = {'write', 'edit', 'multi_edit'}


# Command-based tools — used to extract command name for display purposes.
# User approvals are tool-level: approving "bash" approves ALL bash commands.
COMMAND_TOOLS = {'bash', 'shell', 'run', 'run_in_dir', 'run_background'}

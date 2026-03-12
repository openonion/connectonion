"""
Purpose: Define tool classification and mode constants for approval system
LLM-Note:
  Dependencies: no imports | imported by [tool_approval/approval.py, tool_approval/__init__.py] | tested by [tests/unit/test_tool_approval.py, tests/integration/test_config_permissions.py]
  Data flow: provides read-only constants → consumed by approval.py check_approval() → determines which tools need approval based on mode
  State/Effects: no state | no side effects | pure constant definitions
  Integration: exposes VALID_MODES, DEFAULT_MODE, DANGEROUS_TOOLS, FILE_EDIT_TOOLS, COMMAND_TOOLS sets | used by approval logic to classify tool calls
  Performance: O(1) set membership checks for tool classification
  Errors: none (constants cannot fail)

Constants Overview:
    VALID_MODES = {'safe', 'plan', 'accept_edits'}
        - safe: dangerous tools need approval (default)
        - plan: read-only only, exit_plan_mode needs approval
        - accept_edits: file edits auto-approved

    DANGEROUS_TOOLS: bash, write, edit, send_email, delete, etc.
    FILE_EDIT_TOOLS: write, edit, multi_edit (subset of DANGEROUS)
    COMMAND_TOOLS: bash, shell, run (approval is per-command-name)

Tool Classification:
    Safe tools (unlisted): read, glob, grep, ls → auto-approved
    Dangerous tools: DANGEROUS_TOOLS set → need approval in safe mode
    File edit tools: FILE_EDIT_TOOLS set → auto-approved in accept_edits mode
    Command tools: COMMAND_TOOLS set → tool-level approval (approving "bash" approves all)
"""

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


# Command-based tools — used to extract command name for display purposes.
# User approvals are tool-level: approving "bash" approves ALL bash commands.
COMMAND_TOOLS = {'bash', 'shell', 'run', 'run_in_dir', 'run_background'}

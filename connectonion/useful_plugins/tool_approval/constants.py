"""
Purpose: Define tool classification and permission-profile constants for approval system
LLM-Note:
  Dependencies: imports canonical mode IDs from [core/approval_modes.py] | imported by [tool_approval/approval.py, tool_approval/__init__.py] | tested by [tests/unit/test_tool_approval.py, tests/integration/test_config_permissions.py]
  Data flow: provides read-only constants → consumed by approval.py check_approval() and callers → identifies modes, named edit tools, command tools, and known effectful tools
  State/Effects: no state | no side effects | pure constant definitions
  Integration: exposes VALID_PERMISSION_PROFILES, DANGEROUS_TOOLS, FILE_EDIT_TOOLS, COMMAND_TOOLS sets | approval.py uses profiles, edit tools, and command tools; previous constants remain deprecated compatibility exports
  Performance: O(1) set membership checks for tool classification
  Errors: none (constants cannot fail)

Constants Overview:
    VALID_PERMISSION_PROFILES = {':read-only', ':workspace'}
        - :read-only: unpermitted tools need approval
        - :workspace: named file edits are auto-approved

    DANGEROUS_TOOLS: known effectful tools kept as a public reference set
    FILE_EDIT_TOOLS: write, edit, multi_edit (subset of DANGEROUS)
    COMMAND_TOOLS: bash, shell, run (approval is per-command-name)

Tool Classification:
    Permitted tools: supplied by template, config, skills, or the user → auto-approved
    Unpermitted tools: require approval with live IO, including unclassified tools
    File edit tools: FILE_EDIT_TOOLS set → automatic in :workspace
    Command tools: COMMAND_TOOLS set → tool-level approval (approving "bash" approves all)
"""

# =============================================================================
# PERMISSION PROFILE SYSTEM
# =============================================================================
# Two profiles are enforced directly by this approval hook:
#   - ':read-only': Unpermitted tools need approval
#   - ':workspace': File edits are automatic; other unpermitted tools need approval
#
# The third profile is handled by a separate bounded-grant plugin:
#   - ':danger-full-access': handled by full_access; sets skip_tool_approval=True
#
# New clients change profiles through the Host-acknowledged ACP transaction.
# The legacy WebSocket frame remains a migration reader only.
# =============================================================================

from ...core.approval_modes import (
    DANGER_FULL_ACCESS_PERMISSION_PROFILE,
    READ_ONLY_PERMISSION_PROFILE,
    WORKSPACE_PERMISSION_PROFILE,
)

VALID_PERMISSION_PROFILES = {
    READ_ONLY_PERMISSION_PROFILE,
    WORKSPACE_PERMISSION_PROFILE,
}

# One source-compatibility window for plugin consumers.
DEFAULT_MODE = READ_ONLY_PERMISSION_PROFILE
AUTO_APPROVE_MODE = WORKSPACE_PERMISSION_PROFILE
FULL_ACCESS_MODE = DANGER_FULL_ACCESS_PERMISSION_PROFILE
VALID_MODES = VALID_PERMISSION_PROFILES


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

# File edit tools - auto-approved in the :workspace profile
# These tools only modify files, no external side effects.
FILE_EDIT_TOOLS = {'write', 'edit', 'multi_edit'}


# Command-based tools — used to extract command name for display purposes.
# User approvals are tool-level: approving "bash" approves ALL bash commands.
COMMAND_TOOLS = {'bash', 'shell', 'run', 'run_in_dir', 'run_background'}

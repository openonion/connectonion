"""Compatibility aliases for the canonical bounded Full access plugin.

Legacy callers may still import ULW/YOLO names.  They map to the same
canonical ``:danger-full-access`` state and Host-enforced turn budget; no
legacy mode state or alternate transport is restored.
"""

from .full_access import (
    FULL_ACCESS_CONTINUE_PROMPT,
    FULL_ACCESS_DEFAULT_TURNS,
    enable_yolo,
    full_access,
    full_access_keep_working,
    handle_full_access_permission_profile_change,
    handle_yolo_mode_change,
    inject_full_access_prompt,
    poll_prompt_update,
)

ulw = full_access
yolo = full_access
handle_ulw_mode_change = handle_full_access_permission_profile_change
ulw_keep_working = full_access_keep_working
inject_ulw_prompt = inject_full_access_prompt
ULW_DEFAULT_TURNS = FULL_ACCESS_DEFAULT_TURNS
ULW_CONTINUE_PROMPT = FULL_ACCESS_CONTINUE_PROMPT
YOLO_DEFAULT_TURNS = FULL_ACCESS_DEFAULT_TURNS
YOLO_CONTINUE_PROMPT = FULL_ACCESS_CONTINUE_PROMPT

__all__ = [
    "ULW_CONTINUE_PROMPT",
    "ULW_DEFAULT_TURNS",
    "YOLO_CONTINUE_PROMPT",
    "YOLO_DEFAULT_TURNS",
    "enable_yolo",
    "handle_ulw_mode_change",
    "handle_yolo_mode_change",
    "inject_ulw_prompt",
    "poll_prompt_update",
    "ulw",
    "ulw_keep_working",
    "yolo",
]

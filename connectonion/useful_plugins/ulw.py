"""Deprecated ULW import shim.

Use :mod:`connectonion.useful_plugins.full_access` and its Full access / YOLO
names.  This module exists only for one rolling compatibility window; runtime
state and emitted events are canonical.
"""

from .full_access import (
    FULL_ACCESS_CONTINUE_PROMPT,
    FULL_ACCESS_DEFAULT_TURNS,
    full_access,
    full_access_keep_working,
    handle_full_access_permission_profile_change,
    inject_full_access_prompt,
)

ulw = full_access
handle_ulw_mode_change = handle_full_access_permission_profile_change
ulw_keep_working = full_access_keep_working
inject_ulw_prompt = inject_full_access_prompt
ULW_DEFAULT_TURNS = FULL_ACCESS_DEFAULT_TURNS
ULW_CONTINUE_PROMPT = FULL_ACCESS_CONTINUE_PROMPT

__all__ = [
    "ULW_CONTINUE_PROMPT",
    "ULW_DEFAULT_TURNS",
    "handle_ulw_mode_change",
    "inject_ulw_prompt",
    "ulw",
    "ulw_keep_working",
]

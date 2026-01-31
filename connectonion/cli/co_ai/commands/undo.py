"""Undo/Redo commands with Git backing."""

import subprocess
from typing import Optional

_agent = None
_undo_stack: list[dict] = []
_redo_stack: list[dict] = []


def set_agent(agent):
    global _agent
    _agent = agent


def _is_git_repo() -> bool:
    result = subprocess.run(["git", "rev-parse", "--git-dir"], capture_output=True)
    return result.returncode == 0


def _git_stash_push(message: str) -> bool:
    result = subprocess.run(
        ["git", "stash", "push", "-m", message, "--include-untracked"],
        capture_output=True, text=True
    )
    return result.returncode == 0


def _git_stash_pop() -> bool:
    result = subprocess.run(["git", "stash", "pop"], capture_output=True, text=True)
    return result.returncode == 0


def _git_stash_apply(index: int = 0) -> bool:
    result = subprocess.run(
        ["git", "stash", "apply", f"stash@{{{index}}}"],
        capture_output=True, text=True
    )
    return result.returncode == 0


def _git_stash_drop(index: int = 0) -> bool:
    result = subprocess.run(
        ["git", "stash", "drop", f"stash@{{{index}}}"],
        capture_output=True, text=True
    )
    return result.returncode == 0


def cmd_undo(args: str = "") -> str:
    if not _is_git_repo():
        return "**Error:** Not a git repository. Undo requires git."
    
    if not _agent or not hasattr(_agent, 'messages'):
        return "No conversation to undo."
    
    messages = _agent.messages
    if len(messages) < 2:
        return "Nothing to undo."
    
    user_msg = None
    assistant_msg = None
    
    for i in range(len(messages) - 1, -1, -1):
        if messages[i].get('role') == 'assistant' and assistant_msg is None:
            assistant_msg = messages[i]
        elif messages[i].get('role') == 'user' and assistant_msg and user_msg is None:
            user_msg = messages[i]
            break
    
    if not user_msg or not assistant_msg:
        return "Nothing to undo."
    
    _git_stash_push(f"oo-undo-{len(_undo_stack)}")
    
    _undo_stack.append({
        "user": user_msg,
        "assistant": assistant_msg,
        "stash_index": len(_undo_stack)
    })
    
    messages.remove(user_msg)
    messages.remove(assistant_msg)
    _redo_stack.clear()
    
    return f"Undone last message. File changes stashed. Use `/redo` to restore."


def cmd_redo(args: str = "") -> str:
    if not _undo_stack:
        return "Nothing to redo."
    
    if not _agent or not hasattr(_agent, 'messages'):
        return "No active conversation."
    
    entry = _undo_stack.pop()
    
    _git_stash_pop()
    
    _agent.messages.append(entry["user"])
    _agent.messages.append(entry["assistant"])
    
    return "Restored last undone message and file changes."

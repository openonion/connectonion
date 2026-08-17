"""Safe, provider-neutral OIP presentation events for coding work rooms.

Native coding providers expose commands, local paths, and arbitrary output.  Those
values remain available to the provider and legacy compatibility stream, but this
module deliberately does not copy them into the default Work Room envelope.
"""

from __future__ import annotations

import base64
import re
from typing import Any, Iterable, Mapping


_ACTIVITY_STATUSES = {"running", "completed", "failed"}
_FILE_LIMIT = 8
_FILE_NAME_LIMIT = 128
_SAFE_ACTIVITY_TITLES = frozenset(
    {
        "Update workspace files",
        "Inspect the workspace",
        "Search for context",
        "Use a provider tool",
        "Compile the requested C11 program",
        "Compile the requested C program",
        "Compile and run the requested tests",
        "Run the requested tests",
        "Run the requested program",
        "Run a workspace command",
    }
)
_ACTIVITY_HISTORY_ATTRIBUTE = "_provider_workroom_activity_history"
_STATE_REVISIONS_ATTRIBUTE = "_provider_workroom_state_revisions"
_SAFE_ARTIFACT_ALTS = frozenset(
    {
        "Latest provider workspace view",
        "Latest provider browser view",
    }
)
_ARTIFACT_ID = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
_ARTIFACT_DATA_URL = re.compile(
    r"^data:(image/png|image/jpeg);base64,([A-Za-z0-9+/]+={0,2})$"
)
_MAX_ARTIFACT_DATA_URL_LENGTH = 262_144


def provider_task_title(prompt: object) -> str:
    """Return a stable task category without echoing model-controlled text."""
    text = _words(prompt)
    if not text:
        return "Complete the requested task"
    if _is_c_program_request(text):
        return "Build and verify the requested C program"
    if _contains(text, "create", "write", "edit", "implement", "fix", "update", "build"):
        return "Implement and verify the requested change"
    if _contains(text, "test", "compile", "check", "verify"):
        return "Review and test the requested change"
    if _contains(text, "inspect", "read", "review", "explore", "find", "list"):
        return "Inspect the requested workspace"
    return "Complete the requested task"


def provider_status_summary(status: object) -> str:
    """Describe current provider state without claiming unverified outcomes."""
    return {
        "awaiting_approval": "Waiting for your decision",
        "completed": "The provider completed its run",
        "failed": "The provider reported an error",
        "cancelled": "The provider stopped",
    }.get(str(status), "Working in the selected workspace")


def provider_terminal_summary(
    status: object,
    activities: Iterable[Mapping[str, object]] | None = None,
) -> str:
    """Return a bounded terminal summary backed by safe activity evidence.

    ``activities`` is deliberately restricted to the finite presentation
    vocabulary generated below.  This lets the Work Room say that recorded
    checks completed without ever echoing native command text or provider
    output.
    """
    if str(status) == "completed":
        titles = _completed_activity_titles(activities)
        compiled = bool(
            {
                "Compile the requested C11 program",
                "Compile the requested C program",
                "Compile and run the requested tests",
            }
            & titles
        )
        tested = bool(
            {
                "Compile and run the requested tests",
                "Run the requested tests",
            }
            & titles
        )
        if compiled and tested:
            return (
                "Completed the provider run after the recorded compilation "
                "and test checks"
            )
        if tested:
            return "Completed the provider run after the recorded test checks"
        if compiled:
            return "Completed the provider run after the recorded compilation check"
        if "Run the requested program" in titles:
            return "Completed the provider run after the recorded program check"
    return {
        "completed": "The provider completed its run",
        "failed": "The provider reported an error",
        "cancelled": "The provider stopped",
    }.get(str(status), "The provider ended its run")


def clear_provider_activity_history(agent: object, invocation_id: object) -> None:
    """Start a clean, provider-scoped evidence record for one invocation."""
    if not isinstance(invocation_id, str) or not invocation_id:
        return
    history = getattr(agent, _ACTIVITY_HISTORY_ATTRIBUTE, None)
    if not isinstance(history, dict):
        history = {}
        setattr(agent, _ACTIVITY_HISTORY_ATTRIBUTE, history)
    history.pop(invocation_id, None)


def next_provider_state_revision(agent: object, invocation_id: object) -> int:
    """Advance one provider invocation's monotonic Work Room state revision.

    A provider invocation is replayed over a reconnect and may be sent down a
    live lane before its durable trace is committed.  The revision belongs to
    the semantic lifecycle event rather than either delivery lane, so a client
    can reject an older snapshot without guessing from timestamps or output.
    """
    if not isinstance(invocation_id, str) or not invocation_id:
        raise ValueError("provider state revision requires an invocation id")
    revisions = getattr(agent, _STATE_REVISIONS_ATTRIBUTE, None)
    if not isinstance(revisions, dict):
        revisions = {}
        setattr(agent, _STATE_REVISIONS_ATTRIBUTE, revisions)
    previous = revisions.get(invocation_id, 0)
    if isinstance(previous, bool) or not isinstance(previous, int) or previous < 0:
        previous = 0
    revision = previous + 1
    revisions[invocation_id] = revision
    return revision


def next_provider_state_revision_after(event: Mapping[str, object]) -> int:
    """Return the successor for a Host-synthesized terminal lifecycle event.

    ``InterruptibleIO`` must immediately publish a cancelled state before the
    native adapter unwinds.  It cannot own the adapter's agent-local revision
    map, so it derives the same next revision from the visible invocation.  The
    adapter's later durable terminal event gets that same revision, allowing
    the browser to upsert it as the same semantic state.
    """
    previous = event.get("stateRevision")
    if isinstance(previous, bool) or not isinstance(previous, int) or previous < 1:
        return 1
    return previous + 1


def remember_provider_activity(
    agent: object,
    invocation_id: object,
    activity: Mapping[str, object],
) -> None:
    """Keep only vetted presentation facts for the terminal summary."""
    if not isinstance(invocation_id, str) or not invocation_id:
        return
    title = activity.get("title")
    status = activity.get("status")
    if title not in _SAFE_ACTIVITY_TITLES or status not in _ACTIVITY_STATUSES:
        return
    history = getattr(agent, _ACTIVITY_HISTORY_ATTRIBUTE, None)
    if not isinstance(history, dict):
        history = {}
        setattr(agent, _ACTIVITY_HISTORY_ATTRIBUTE, history)
    entries = history.setdefault(invocation_id, [])
    if isinstance(entries, list):
        entries.append({"title": title, "status": status})


def take_provider_activity_history(
    agent: object,
    invocation_id: object,
) -> list[Mapping[str, object]]:
    """Consume an invocation's safe evidence so later runs cannot reuse it."""
    history = getattr(agent, _ACTIVITY_HISTORY_ATTRIBUTE, None)
    if not isinstance(history, dict) or not isinstance(invocation_id, str):
        return []
    entries = history.pop(invocation_id, [])
    return entries if isinstance(entries, list) else []


def _completed_activity_titles(
    activities: Iterable[Mapping[str, object]] | None,
) -> set[str]:
    if activities is None:
        return set()
    return {
        title
        for activity in activities
        if isinstance(activity, Mapping)
        and activity.get("status") == "completed"
        and isinstance((title := activity.get("title")), str)
        and title in _SAFE_ACTIVITY_TITLES
    }


def provider_activity_event(
    *,
    provider: str,
    activity_id: str,
    sequence: int,
    native_kind: object,
    status: object,
    name: object = "",
    details: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Translate one native operation into a safe, additive OIP activity."""
    kind = _activity_kind(native_kind, name)
    normalized_status = _activity_status(status)
    title, summary = _activity_copy(kind, normalized_status, name, details)
    event: dict[str, Any] = {
        "type": "provider_activity",
        "provider": provider,
        "activityId": activity_id,
        "sequence": sequence,
        "kind": kind,
        "status": normalized_status,
        "title": title,
        "summary": summary,
    }
    files = _file_evidence(details) if kind == "file_change" else []
    if files:
        event["files"] = files
    return event


def provider_artifact_event(
    *,
    provider: str,
    invocation_id: str,
    parent_tool_call_id: str,
    artifact_id: str,
    state_revision: int,
    thumbnail_data_url: str,
    alt: str,
) -> dict[str, Any]:
    """Build one bounded, image-only Work Room preview event.

    Native adapters do not expose arbitrary provider text as a visual.  An
    adapter may opt in only after it has captured a real, Host-owned image of
    the provider workspace or browser.  The inline PNG/JPEG avoids third-party
    URL fetches, SVG/script execution, and bearer URLs leaking into a reader's
    Work Room; the browser still validates it again before rendering.
    """
    if provider not in {"codex", "claude_code"}:
        raise ValueError("provider artifact requires a supported provider")
    if not all(
        isinstance(value, str) and value
        for value in (invocation_id, parent_tool_call_id)
    ):
        raise ValueError("provider artifact requires invocation correlation")
    if not isinstance(artifact_id, str) or not _ARTIFACT_ID.fullmatch(artifact_id):
        raise ValueError("provider artifact id is invalid")
    if (
        isinstance(state_revision, bool)
        or not isinstance(state_revision, int)
        or state_revision < 1
    ):
        raise ValueError("provider artifact requires a positive state revision")
    if alt not in _SAFE_ARTIFACT_ALTS:
        raise ValueError("provider artifact alt text is not approved")
    _validate_artifact_data_url(thumbnail_data_url)
    return {
        "type": "provider_artifact",
        "provider": provider,
        "invocationId": invocation_id,
        "parentToolCallId": parent_tool_call_id,
        "artifactId": artifact_id,
        "kind": "screenshot",
        "stateRevision": state_revision,
        "thumbnailDataUrl": thumbnail_data_url,
        "alt": alt,
    }


def _validate_artifact_data_url(value: object) -> None:
    """Refuse a non-image, oversized, or malformed inline thumbnail."""
    if not isinstance(value, str) or len(value) > _MAX_ARTIFACT_DATA_URL_LENGTH:
        raise ValueError("provider artifact thumbnail is invalid")
    matched = _ARTIFACT_DATA_URL.fullmatch(value)
    if matched is None:
        raise ValueError("provider artifact thumbnail must be an inline PNG or JPEG")
    mime, encoded = matched.groups()
    try:
        binary = base64.b64decode(encoded, validate=True)
    except ValueError as exc:
        raise ValueError("provider artifact thumbnail is malformed") from exc
    valid_image = (
        mime == "image/png" and binary.startswith(b"\x89PNG\r\n\x1a\n")
    ) or (
        mime == "image/jpeg" and binary.startswith(b"\xff\xd8") and binary.endswith(b"\xff\xd9")
    )
    if not valid_image:
        raise ValueError("provider artifact thumbnail does not match its image type")


def _words(value: object) -> str:
    return " ".join(value.lower().split()) if isinstance(value, str) else ""


def _contains(text: str, *words: str) -> bool:
    return any(word in text for word in words)


def _is_c_program_request(text: str) -> bool:
    """Classify an explicit C-task request without echoing its contents."""
    return bool(
        re.search(r"(?:^|\s)c(?:11|17|23)?(?:\s|$)", text)
        or ".c" in text
        or _contains(text, "compiler", "compile")
    )


def _activity_status(value: object) -> str:
    text = str(value)
    if text in {"pending", "in_progress"}:
        return "running"
    return text if text in _ACTIVITY_STATUSES else "failed"


def _activity_kind(native_kind: object, name: object) -> str:
    native = _words(native_kind).replace(" ", "")
    label = _words(name)
    if native in {"commandexecution", "command", "bash", "shell", "exec"}:
        return "command"
    if native in {"filechange", "file", "write", "edit", "patch"}:
        return "file_change"
    if native in {"websearch", "search"}:
        return "search"
    if _contains(label, "read", "glob", "grep", "list", "find", "inspect"):
        return "inspect"
    if _contains(label, "bash", "shell", "command", "exec"):
        return "command"
    if _contains(label, "write", "edit", "patch", "create"):
        return "file_change"
    if _contains(label, "search", "browse", "web"):
        return "search"
    return "tool"


def _activity_copy(
    kind: str,
    status: str,
    name: object,
    details: Mapping[str, Any] | None,
) -> tuple[str, str]:
    if kind == "command":
        return _command_activity_copy(status, name, details)
    copy = {
        "file_change": ("Update workspace files", "Preparing workspace file changes", "Workspace files updated", "Workspace file change failed"),
        "inspect": ("Inspect the workspace", "Inspecting workspace context", "Workspace inspection completed", "Workspace inspection failed"),
        "search": ("Search for context", "Searching for relevant context", "Context search completed", "Context search failed"),
        "tool": ("Use a provider tool", "Using a provider tool", "Provider tool completed", "Provider tool failed"),
    }[kind]
    return copy[0], copy[{"running": 1, "completed": 2, "failed": 3}[status]]


def _command_activity_copy(
    status: str,
    name: object,
    details: Mapping[str, Any] | None,
) -> tuple[str, str]:
    """Map a command to a finite phase name; never return the command itself."""
    command = _command_text(name, details)
    phase = _command_phase(command)
    copy = {
        "compile_c11": (
            "Compile the requested C11 program",
            "Compiling the requested C11 program",
            "Compiled the requested C11 program",
            "Could not compile the requested C11 program",
        ),
        "compile_c": (
            "Compile the requested C program",
            "Compiling the requested C program",
            "Compiled the requested C program",
            "Could not compile the requested C program",
        ),
        "compile_and_test": (
            "Compile and run the requested tests",
            "Compiling and running the requested tests",
            "Completed the requested compilation and tests",
            "The requested compilation or tests failed",
        ),
        "test": (
            "Run the requested tests",
            "Running the requested tests",
            "Completed the requested tests",
            "The requested tests failed",
        ),
        "run": (
            "Run the requested program",
            "Running the requested program",
            "Completed the requested program run",
            "The requested program run failed",
        ),
        "inspect": (
            "Inspect the workspace",
            "Inspecting workspace context",
            "Completed the workspace inspection",
            "The workspace inspection failed",
        ),
        "command": (
            "Run a workspace command",
            "Running a workspace command",
            "Completed a workspace command",
            "A workspace command failed",
        ),
    }[phase]
    return copy[0], copy[{"running": 1, "completed": 2, "failed": 3}[status]]


def command_phase(name: object = "", details: Mapping[str, Any] | None = None) -> str:
    """Public finite command classifier for native approval copy.

    The source text is examined only to select one of these fixed labels; it is
    never returned or included in a Work Room event.
    """
    return _command_phase(_command_text(name, details))


def _command_text(name: object, details: Mapping[str, Any] | None) -> str:
    command = details.get("command") if details else None
    if isinstance(command, (list, tuple)):
        command = " ".join(str(part) for part in command)
    value = command if isinstance(command, str) else name
    return _words(value)


def _command_phase(command: str) -> str:
    # Do not label an outbound operation as an inspection merely because its
    # executable begins with git. The caller uses this finite category only
    # for safe UI copy; broader policy is enforced by the approval adapter.
    if re.search(
        r"(?:^|\s)(?:curl|wget|ssh|scp|rsync|nc)(?:\s|$)"
        r"|(?:^|\s)git\s+(?:push|fetch|pull|clone)(?:\s|$)"
        r"|(?:^|\s)(?:npm|pnpm)\s+(?:publish|install)(?:\s|$)"
        r"|(?:^|\s)pip(?:3)?\s+install(?:\s|$)",
        command,
    ):
        return "command"
    compiler = bool(re.search(r"(?:^|\s)(?:cc|gcc|clang)(?:\s|$)", command))
    c11 = "-std=c11" in command
    tests = bool(re.search(r"(?:pytest|vitest|jest|ctest|npm test|pnpm test|test[_-]?sort|sort[_-]?test)", command))
    if compiler and tests:
        return "compile_and_test"
    if compiler:
        return "compile_c11" if c11 else "compile_c"
    if tests:
        return "test"
    if re.search(r"(?:^|\s)\./[a-z0-9_.-]+(?:\s|$)", command):
        return "run"
    if re.search(r"(?:^|\s)(?:git|rg|grep|find|ls|cat|sed|head|tail|stat)(?:\s|$)", command):
        return "inspect"
    return "command"


def _file_evidence(details: Mapping[str, Any] | None) -> list[str]:
    if not details:
        return []
    candidates: list[object] = [details.get("path"), details.get("file_path")]
    files = details.get("files")
    if isinstance(files, (list, tuple)):
        candidates.extend(files)
    output: list[str] = []
    for candidate in candidates:
        name = _file_name(candidate)
        if name and name not in output:
            output.append(name)
        if len(output) == _FILE_LIMIT:
            break
    return output


def _file_name(value: object) -> str:
    if not isinstance(value, str):
        return ""
    name = value.replace("\\", "/").rstrip("/").rsplit("/", 1)[-1]
    if not name or name in {".", ".."}:
        return ""
    return name if len(name) <= _FILE_NAME_LIMIT else name[: _FILE_NAME_LIMIT - 1] + "…"

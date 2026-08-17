"""Contracts for the safe, provider-neutral Work Room event envelope."""

import json

import pytest

from connectonion.core.provider_events import (
    provider_artifact_event,
    provider_activity_event,
    provider_status_summary,
    provider_task_title,
    provider_terminal_summary,
)


_PNG = (
    "data:image/png;base64,"
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9WlRjyoAAAAASUVORK5CYII="
)


def test_task_title_is_semantic_and_never_echoes_the_provider_prompt():
    prompt = "Create sort.c and test_sort.c, then compile with TOKEN=private-value"

    title = provider_task_title(prompt)

    assert title == "Build and verify the requested C program"
    assert "sort.c" not in title
    assert "private" not in title


def test_invocation_summaries_do_not_overclaim_a_provider_result():
    assert provider_status_summary("running") == "Working in the selected workspace"
    assert provider_status_summary("awaiting_approval") == "Waiting for your decision"
    assert provider_terminal_summary("completed") == "The provider completed its run"
    assert provider_terminal_summary("failed") == "The provider reported an error"


def test_terminal_summary_can_report_only_recorded_safe_checks():
    summary = provider_terminal_summary(
        "completed",
        [
            {"title": "Compile the requested C11 program", "status": "completed"},
            {"title": "Run the requested tests", "status": "completed"},
            {"title": "private provider text", "status": "completed"},
        ],
    )

    assert summary == (
        "Completed the provider run after the recorded compilation and test checks"
    )
    assert "private" not in summary


def test_command_activity_is_semantic_and_omits_raw_command_path_and_output():
    event = provider_activity_event(
        provider="codex",
        activity_id="cmd-7",
        sequence=3,
        native_kind="commandExecution",
        status="completed",
        name="cc -std=c11 -Wall -Werror sort.c -o sort",
        details={
            "command": "cc -std=c11 -Wall -Werror sort.c -o sort --token private-value",
            "cwd": "/private/tmp/operator/private-workroom",
            "result": "all checks passed with private-value",
        },
    )

    assert event == {
        "type": "provider_activity",
        "provider": "codex",
        "activityId": "cmd-7",
        "sequence": 3,
        "kind": "command",
        "status": "completed",
        "title": "Compile the requested C11 program",
        "summary": "Compiled the requested C11 program",
    }
    rendered = json.dumps(event)
    assert "private" not in rendered
    assert "cc -std" not in rendered
    assert "/private" not in rendered


def test_file_activity_exposes_only_a_bounded_basename_as_evidence():
    event = provider_activity_event(
        provider="codex",
        activity_id="edit-2",
        sequence=4,
        native_kind="fileChange",
        status="running",
        name="/private/tmp/operator/sort.c",
        details={"path": "/private/tmp/operator/sort.c"},
    )

    assert event == {
        "type": "provider_activity",
        "provider": "codex",
        "activityId": "edit-2",
        "sequence": 4,
        "kind": "file_change",
        "status": "running",
        "title": "Update workspace files",
        "summary": "Preparing workspace file changes",
        "files": ["sort.c"],
    }


def test_claude_read_maps_to_a_shared_inspection_vocabulary():
    event = provider_activity_event(
        provider="claude_code",
        activity_id="claude:read-1",
        sequence=1,
        native_kind="tool",
        status="running",
        name="Read",
        details={},
    )

    assert event["kind"] == "inspect"
    assert event["title"] == "Inspect the workspace"
    assert event["summary"] == "Inspecting workspace context"


def test_provider_artifact_is_a_bounded_image_bound_to_one_state_revision():
    event = provider_artifact_event(
        provider="codex",
        invocation_id="codex:call-7",
        parent_tool_call_id="call-7",
        artifact_id="screen-7",
        state_revision=4,
        thumbnail_data_url=_PNG,
        alt="Latest provider workspace view",
    )

    assert event == {
        "type": "provider_artifact",
        "provider": "codex",
        "invocationId": "codex:call-7",
        "parentToolCallId": "call-7",
        "artifactId": "screen-7",
        "kind": "screenshot",
        "stateRevision": 4,
        "thumbnailDataUrl": _PNG,
        "alt": "Latest provider workspace view",
    }


@pytest.mark.parametrize("thumbnail,alt", [
    ("data:image/svg+xml;base64,PHN2Zz48L3N2Zz4=", "Latest provider workspace view"),
    (_PNG, "Run curl --token private-value"),
])
def test_provider_artifact_rejects_untrusted_or_unsafe_rendering_input(thumbnail, alt):
    with pytest.raises(ValueError):
        provider_artifact_event(
            provider="codex",
            invocation_id="codex:call-7",
            parent_tool_call_id="call-7",
            artifact_id="screen-7",
            state_revision=4,
            thumbnail_data_url=thumbnail,
            alt=alt,
        )

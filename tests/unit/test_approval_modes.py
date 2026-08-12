import pytest

from connectonion.core.approval_modes import (
    DANGER_FULL_ACCESS_PERMISSION_PROFILE,
    READ_ONLY_PERMISSION_PROFILE,
    WORKSPACE_PERMISSION_PROFILE,
    has_valid_full_access_grant,
    legacy_permission_profile_id,
    migrate_legacy_full_access_fields,
    normalize_runtime_approval_session,
    permission_profile_id,
)


@pytest.mark.parametrize(
    ("legacy", "canonical"),
    [
        ("safe", READ_ONLY_PERMISSION_PROFILE),
        ("accept_edits", WORKSPACE_PERMISSION_PROFILE),
        ("ulw", DANGER_FULL_ACCESS_PERMISSION_PROFILE),
    ],
)
def test_legacy_mode_ids_normalize_only_through_the_compatibility_reader(
    legacy,
    canonical,
):
    assert legacy_permission_profile_id(legacy) == canonical
    with pytest.raises(ValueError, match="Unsupported permission profile"):
        permission_profile_id(legacy)


def test_legacy_full_access_fields_migrate_without_overwriting_canonical_state():
    session = {
        "ulw_turns": 10,
        "ulw_turns_used": 3,
        "ulw_prompt": "legacy",
        "full_access_turns": 6,
    }

    assert migrate_legacy_full_access_fields(session) == {
        "full_access_turns": 6,
        "full_access_turns_used": 3,
        "full_access_prompt": "legacy",
    }


def test_runtime_session_migrates_one_valid_legacy_full_access_grant():
    assert normalize_runtime_approval_session({
        "mode": "ulw",
        "ulw_turns": 10,
        "ulw_turns_used": 3,
        "skip_tool_approval": True,
    }) == {
        "mode": ":danger-full-access",
        "full_access_turns": 10,
        "full_access_turns_used": 3,
        "skip_tool_approval": True,
    }


def test_full_access_grant_requires_all_bounded_authority_fields():
    assert has_valid_full_access_grant({
        "mode": ":danger-full-access",
        "full_access_turns": 10,
        "full_access_turns_used": 3,
        "skip_tool_approval": True,
    })
    assert not has_valid_full_access_grant({"mode": ":danger-full-access"})


@pytest.mark.parametrize(
    "session",
    [
        {"mode": "future", "skip_tool_approval": True},
        {"mode": "plan", "skip_tool_approval": True},
        {"mode": ":danger-full-access", "full_access_turns": 5},
        {
            "mode": ":danger-full-access",
            "full_access_turns": 5,
            "full_access_turns_used": 5,
            "skip_tool_approval": True,
        },
    ],
)
def test_runtime_session_downgrades_malformed_authority_before_execution(session):
    normalized = normalize_runtime_approval_session(session)

    assert normalized["mode"] == ":read-only"
    assert not {
        "skip_tool_approval",
        "full_access_turns",
        "full_access_turns_used",
        "full_access_prompt",
    } & normalized.keys()

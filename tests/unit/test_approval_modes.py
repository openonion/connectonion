import pytest

from connectonion.core.approval_modes import (
    AUTO_APPROVE_MODE,
    DEFAULT_MODE,
    FULL_ACCESS_MODE,
    approval_mode_id,
    legacy_approval_mode_id,
    migrate_legacy_full_access_fields,
)


@pytest.mark.parametrize(
    ("legacy", "canonical"),
    [
        ("safe", DEFAULT_MODE),
        ("accept_edits", AUTO_APPROVE_MODE),
        ("ulw", FULL_ACCESS_MODE),
    ],
)
def test_legacy_mode_ids_normalize_only_through_the_compatibility_reader(
    legacy,
    canonical,
):
    assert legacy_approval_mode_id(legacy) == canonical
    with pytest.raises(ValueError, match="Unsupported approval mode"):
        approval_mode_id(legacy)


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

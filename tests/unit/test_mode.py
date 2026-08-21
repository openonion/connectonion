import pytest

from connectonion.core.mode import (
    AUTO,
    DEFAULT_MODE,
    FULL_ACCESS,
    MODES,
    READ_ONLY,
    consume_full_access_turn,
    full_access_turns_left,
    mode_id,
    mode_of,
    set_mode,
    skips_approval,
)


def test_public_mode_vocabulary_has_exactly_three_values_and_defaults_to_auto():
    assert MODES == ("read-only", "auto", "full-access")
    assert DEFAULT_MODE == AUTO


@pytest.mark.parametrize("mode", MODES)
def test_mode_id_accepts_only_exact_public_values(mode):
    assert mode_id(mode) == mode


@pytest.mark.parametrize(
    "legacy",
    [
        ":read-only",
        ":workspace",
        ":danger-full-access",
        "safe",
        "default",
        "manual",
        "accept_edits",
        "auto_approve",
        "ulw",
        "full_access",
        "plan",
        "planning",
        None,
    ],
)
def test_mode_id_rejects_legacy_unknown_and_missing_values(legacy):
    with pytest.raises(ValueError, match="Unsupported mode"):
        mode_id(legacy)


@pytest.mark.parametrize(
    "session",
    [
        {},
        {"mode": "future"},
        {"mode": ":read-only"},
        {"mode": "ulw", "turns_left": 10},
        {"mode": FULL_ACCESS},
        {"mode": FULL_ACCESS, "turns_left": 0},
        {"mode": FULL_ACCESS, "turns_left": True},
    ],
)
def test_mode_of_degrades_unknown_or_incomplete_stored_state_to_auto(session):
    assert mode_of(session) == AUTO
    assert not skips_approval(session)


def test_set_mode_is_the_single_canonical_writer():
    session = {"turns_left": 99, "unrelated": "kept"}

    assert set_mode(session, READ_ONLY) == READ_ONLY
    assert session == {"mode": READ_ONLY, "unrelated": "kept"}

    assert set_mode(session, AUTO) == AUTO
    assert session == {"mode": AUTO, "unrelated": "kept"}

    assert set_mode(session, FULL_ACCESS, turns_left=3) == FULL_ACCESS
    assert session == {
        "mode": FULL_ACCESS,
        "turns_left": 3,
        "unrelated": "kept",
    }
    assert skips_approval(session)


@pytest.mark.parametrize("turns_left", [None, 0, -1, True, 1.5, "3"])
def test_full_access_rejects_an_invalid_or_unbounded_budget(turns_left):
    with pytest.raises(ValueError, match="positive turns_left"):
        set_mode({}, FULL_ACCESS, turns_left=turns_left)


@pytest.mark.parametrize("mode", [READ_ONLY, AUTO])
def test_non_full_access_modes_reject_a_turn_budget(mode):
    with pytest.raises(ValueError, match="only valid for full-access"):
        set_mode({}, mode, turns_left=2)


def test_full_access_countdown_expires_atomically_to_auto():
    session = {}
    set_mode(session, FULL_ACCESS, turns_left=2)

    assert consume_full_access_turn(session) == FULL_ACCESS
    assert session == {"mode": FULL_ACCESS, "turns_left": 1}
    assert full_access_turns_left(session) == 1

    assert consume_full_access_turn(session) == AUTO
    assert session == {"mode": AUTO}
    assert not skips_approval(session)


def test_consuming_a_malformed_full_access_grant_repairs_it_to_auto():
    session = {"mode": FULL_ACCESS, "turns_left": "unbounded"}

    assert consume_full_access_turn(session) == AUTO
    assert session == {"mode": AUTO}


@pytest.mark.parametrize("mode", [READ_ONLY, AUTO])
def test_consuming_an_ordinary_mode_is_a_noop(mode):
    session = {"mode": mode, "unrelated": 1}

    assert consume_full_access_turn(session) == mode
    assert session == {"mode": mode, "unrelated": 1}

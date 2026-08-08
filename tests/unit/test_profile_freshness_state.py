"""The profile revision watermark is monotonic, atomic, and fail closed."""

import json

import pytest

from connectonion.network import profile_freshness as freshness


def test_next_revision_never_moves_back_when_the_clock_does(tmp_path, monkeypatch):
    state = tmp_path / "state.json"
    freshness.write_state(state, 100)
    monkeypatch.setattr(freshness.time, "time_ns", lambda: 50)

    assert freshness.next_revision(state) == 101


def test_a_boolean_is_not_a_revision():
    with pytest.raises(ValueError, match="positive 64-bit"):
        freshness.validate_revision(True)


def test_malformed_state_is_not_treated_as_first_install(tmp_path):
    state = tmp_path / "state.json"
    state.write_text(json.dumps({"revision": "100"}), encoding="utf-8")

    with pytest.raises(ValueError, match="positive 64-bit"):
        freshness.read_state(state)


def test_write_state_never_lowers_a_watermark(tmp_path):
    state = tmp_path / "state.json"
    freshness.write_state(state, 100, "signature")

    with pytest.raises(ValueError, match="lower"):
        freshness.write_state(state, 99, "older")

    assert freshness.read_state(state) == {
        "revision": 100,
        "signature": "signature",
    }

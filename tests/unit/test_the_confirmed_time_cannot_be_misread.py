"""A confirmed time says which zone it is in.

`co gcalendar meet "…" "2026-09-15T16:30:00+10:00" …` answered:

    Start: 2026-09-15 06:30 AM

which is the same instant, correctly converted to UTC — and unreadable as
anything but "the meeting is at half past six in the morning". The event was
right; the sentence describing it was not.

Two claims in #1547 turned out to be stale, and are *not* fixed here because
measurement said they were already true:

  * `_parse_time` does accept an ISO string with an offset — `fromisoformat`
    handles it, and `'2026-09-15T16:30:00+10:00'` parses fine today.
  * `'timeZone': 'UTC'` in the body is not self-contradictory. `_parse_time`
    converts to UTC and strips the offset *before* the body is built, so the
    stored `dateTime` really is UTC and the label is honest.

Fixing either would have been a change with no defect under it. What remains is
the label on the way out.
"""

import pytest

from connectonion.useful_tools.google_calendar import GoogleCalendar


@pytest.fixture
def cal():
    return GoogleCalendar.__new__(GoogleCalendar)


def test_the_offset_the_caller_typed_still_parses(cal):
    """Guarding the claim above, so nobody 'fixes' a parser that works."""
    parsed = cal._parse_time("2026-09-15T16:30:00+10:00")

    assert (parsed.hour, parsed.minute) == (6, 30), "converted to UTC, as designed"
    assert parsed.tzinfo is None, "stripped, which is why the body's UTC label is true"


def test_a_converted_time_is_labelled(cal):
    """06:30 with no zone reads as the wrong meeting. 06:30 UTC cannot."""
    shown = cal._format_datetime("2026-09-15T06:30:00")

    assert "06:30 AM" in shown
    assert "UTC" in shown


def test_a_time_that_carries_its_own_offset_keeps_it(cal):
    shown = cal._format_datetime("2026-09-15T16:30:00+10:00")

    assert "04:30 PM" in shown
    assert "+10:00" in shown
    assert "UTC" not in shown, "it is not UTC, and saying so would be the same bug"


def test_a_zulu_time_is_labelled_utc_not_z(cal):
    shown = cal._format_datetime("2026-09-15T06:30:00Z")

    assert "UTC" in shown


def test_the_confirmation_carries_the_label(cal, monkeypatch):
    """The whole point: the sentence a person reads after creating a meeting."""

    class Service:
        def events(self):
            return self

        def insert(self, **kwargs):
            return self

        def execute(self):
            return {"id": "evt_1", "hangoutLink": "https://meet.google.com/x"}

    monkeypatch.setattr(cal, "_get_service", lambda: Service(), raising=False)

    out = cal.create_meet("Intro", "2026-09-15T16:30:00+10:00",
                          "2026-09-15T17:15:00+10:00", attendees="g@example.com")

    assert "UTC" in out, f"a bare time is what made this unreadable:\n{out}"

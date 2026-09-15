"""A date window is the unit every mail sweep actually wants."""

from datetime import datetime, timedelta, timezone

import pytest

from connectonion.cli.commands.mail_window import (
    LISTING_FIELDS, parse_since, parse_until, window_listing,
)


class FakeMailbox:
    """Answers list_between and records what it was asked for."""

    def __init__(self, per_call=2):
        self.calls, self.per_call = [], per_call

    def list_between(self, start, end, max_results):
        self.calls.append((start, end, max_results))
        return [{"id": f"{len(self.calls)}-{i}", "from": "a@b.c", "to": ["me@x.y"],
                 "date": f"{start[:10]}T0{i}:00:00Z", "subject": "s", "unread": False,
                 "body": "should not be printed"}
                for i in range(min(self.per_call, max_results))]


def test_a_relative_window_is_read_as_a_span_ending_now():
    for value, days in (("30d", 30), ("2w", 14), ("6m", 180), ("1y", 365), (" 3 d ", 3)):
        gap = datetime.now(timezone.utc) - parse_since(value)
        assert abs(gap - timedelta(days=days)) < timedelta(minutes=1), value


def test_a_plain_date_is_read_as_that_date_in_utc():
    assert parse_since("2026-06-01") == datetime(2026, 6, 1, tzinfo=timezone.utc)
    assert parse_since("2026-06-01T09:30:00Z").hour == 9


def test_an_unreadable_window_says_what_would_work():
    with pytest.raises(ValueError) as caught:
        parse_since("last week")
    assert "30d" in str(caught.value) and "2026-06-01" in str(caught.value)


def test_until_defaults_to_now():
    assert (datetime.now(timezone.utc) - parse_until(None)) < timedelta(minutes=1)


def test_the_window_is_walked_a_week_at_a_time():
    """One call for a long span comes back silently truncated by the provider."""
    box = FakeMailbox()
    window_listing(box, "21d", None, last=100)
    assert len(box.calls) == 3
    starts = [call[0][:10] for call in box.calls]
    assert starts == sorted(starts)                      # forward, oldest first
    assert box.calls[0][1] == box.calls[1][0]            # contiguous, no gap


def test_the_cap_is_honoured_and_stops_the_walk_early():
    box = FakeMailbox(per_call=5)
    rows = window_listing(box, "90d", None, last=7)
    assert len(rows) == 7
    assert sum(call[2] for call in box.calls) <= 7 + 5   # never asks for more than it needs


def test_results_come_back_oldest_first():
    rows = window_listing(FakeMailbox(), "14d", None, last=100)
    assert [row["date"] for row in rows] == sorted(row["date"] for row in rows)


def test_a_backwards_window_is_refused_rather_than_returning_nothing():
    with pytest.raises(ValueError) as caught:
        window_listing(FakeMailbox(), "2026-09-01", "2026-06-01", last=10)
    assert "earlier" in str(caught.value)


def test_json_carries_the_listing_fields_and_not_the_body(capsys):
    from connectonion.cli.commands.mail_window import print_json_listing
    import json

    print_json_listing(window_listing(FakeMailbox(), "7d", None, last=2))
    rows = json.loads(capsys.readouterr().out)
    assert rows and all(set(row) <= set(LISTING_FIELDS) for row in rows)
    assert all("body" not in row for row in rows)
    assert rows[0]["to"] == ["me@x.y"]      # recipients survive, which is why it exists

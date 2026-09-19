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


def test_the_window_is_walked_a_week_at_a_time_from_the_recent_end():
    """One call for a long span comes back silently truncated by the provider.

    Walked backwards, and the direction is not cosmetic: the walk stops as soon
    as the cap is full, so whichever end it starts from is the end the caller
    keeps. Starting at `since` answered "the last 30 days" with mail from a
    month ago and nothing since.
    """
    box = FakeMailbox()
    window_listing(box, "21d", None, last=100)
    assert len(box.calls) == 3
    starts = [call[0][:10] for call in box.calls]
    assert starts == sorted(starts, reverse=True)        # backwards, newest first
    assert box.calls[0][0] == box.calls[1][1]            # contiguous, no gap


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


class BusyMailbox:
    """A mailbox with one message an hour, which honours the newest-first flag.

    The real failure needed a mailbox with more mail in the window than the cap,
    which `FakeMailbox` never had: it answers a fixed two per call regardless of
    what is actually there, so the wrong half was indistinguishable from the
    right one.
    """

    def __init__(self):
        self.asked_newest_first = []

    def list_between(self, start, end, max_results, newest_first=False):
        self.asked_newest_first.append(newest_first)
        first, last_ = datetime.fromisoformat(start), datetime.fromisoformat(end)
        hours, rows = [], []
        moment = first.replace(minute=0, second=0, microsecond=0)
        while moment < last_:
            hours.append(moment)
            moment += timedelta(hours=1)
        kept = sorted(hours, reverse=True)[:max_results] if newest_first else hours[:max_results]
        for moment in sorted(kept):
            rows.append({"id": moment.isoformat(), "from": "a@b.c", "to": ["me@x.y"],
                         "date": moment.isoformat(), "subject": "s", "unread": False})
        return rows


def test_a_capped_window_keeps_the_newest_not_the_oldest():
    # The 1.8.6 bug, on a real mailbox: `--since 30d -n 10` answered with ten
    # messages from a month ago, the newest of them three weeks stale, and
    # nothing said the rest existed.
    box = BusyMailbox()

    rows = window_listing(box, "30d", None, last=10)

    assert len(rows) == 10
    newest = datetime.fromisoformat(rows[-1]["date"])
    assert datetime.now(timezone.utc) - newest < timedelta(days=1), rows[-1]["date"]
    assert all(box.asked_newest_first), box.asked_newest_first


def test_a_window_that_had_to_be_cut_says_so_on_stderr(capsys):
    # stdout stays exactly one JSON array for whoever is parsing it; the person
    # and anything reading stderr still find out it is a partial answer.
    window_listing(BusyMailbox(), "30d", None, last=10)

    captured = capsys.readouterr()
    assert "there are more" in captured.err
    assert captured.out == ""


def test_a_window_that_fit_says_nothing(capsys):
    window_listing(BusyMailbox(), "2d", None, last=500)

    assert capsys.readouterr().err == ""


def test_a_provider_that_does_not_know_the_flag_still_works():
    # FakeMailbox takes no newest_first; older callers of list_between do not
    # pass one either, and neither should have to grow a parameter to be listed.
    box = FakeMailbox()                       # its list_between takes three arguments

    rows = window_listing(box, "21d", None, last=4)

    assert len(rows) == 4
    assert len(box.calls) == 2                # two chunks of two, then the cap


def test_json_carries_the_listing_fields_and_not_the_body(capsys):
    from connectonion.cli.commands.mail_window import print_json_listing
    import json

    print_json_listing(window_listing(FakeMailbox(), "7d", None, last=2))
    rows = json.loads(capsys.readouterr().out)
    assert rows and all(set(row) <= set(LISTING_FIELDS) for row in rows)
    assert all("body" not in row for row in rows)
    assert rows[0]["to"] == ["me@x.y"]      # recipients survive, which is why it exists

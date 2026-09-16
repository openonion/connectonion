"""Adding one attendee does not un-answer everybody else.

`update_event` fetches the event — so it holds each attendee's
`responseStatus` — and then throws that away, replacing the list with bare
`{'email': …}` entries. Google reads an absent `responseStatus` as
`needsAction`, so adding one person resets everyone.

1.8.5 made this worse rather than causing it. Before `sendUpdates='all'`
(#1548) the reset was silent; now every already-answered attendee is emailed a
fresh invitation for a meeting they had accepted, which is the version people
actually notice.

The fix keeps what Google already knows about an address that is staying, and
only new addresses arrive unanswered — which is what they are.
"""

import pytest

from connectonion.useful_tools.google_calendar import GoogleCalendar

EXISTING = [
    {"email": "a@example.com", "responseStatus": "accepted"},
    {"email": "b@example.com", "responseStatus": "declined"},
    {"email": "organiser@example.com", "responseStatus": "accepted", "organizer": True},
]


class Recorder:
    def __init__(self, attendees=None):
        self.attendees = EXISTING if attendees is None else attendees
        self.sent = {}

    def events(self):
        return self

    def get(self, **kwargs):
        return _Result({
            "id": "evt_1", "summary": "Standup",
            "start": {"dateTime": "2026-09-20T10:00:00Z"},
            "end": {"dateTime": "2026-09-20T10:30:00Z"},
            "attendees": list(self.attendees),
        })

    def update(self, **kwargs):
        self.sent = kwargs
        return _Result({"id": "evt_1", "summary": "Standup"})


class _Result:
    def __init__(self, payload):
        self._payload = payload

    def execute(self):
        return self._payload


def run(attendees, existing=None):
    cal = GoogleCalendar.__new__(GoogleCalendar)
    rec = Recorder(existing)
    cal._get_service = lambda: rec
    cal.update_event("evt_1", attendees=attendees)
    return {a["email"]: a for a in rec.sent["body"]["attendees"]}


def test_an_attendee_who_accepted_stays_accepted():
    out = run("a@example.com,b@example.com,c@example.com")

    assert out["a@example.com"]["responseStatus"] == "accepted"
    assert out["b@example.com"]["responseStatus"] == "declined"


def test_a_newly_added_attendee_has_not_answered():
    out = run("a@example.com,b@example.com,c@example.com")

    assert "c@example.com" in out
    assert out["c@example.com"].get("responseStatus") in (None, "needsAction")


def test_removing_someone_removes_them():
    """The list is still authoritative — this preserves answers, not membership."""
    out = run("a@example.com")

    assert set(out) == {"a@example.com"}


def test_everything_google_knows_about_a_kept_attendee_survives():
    """Not just responseStatus: organizer, optional, comment, displayName all
    live on the same entry, and rebuilding it from an email drops them too."""
    out = run("organiser@example.com")

    assert out["organiser@example.com"].get("organizer") is True
    assert out["organiser@example.com"]["responseStatus"] == "accepted"


def test_the_address_is_matched_case_insensitively():
    """Someone typing Aaron@Example.com must not un-answer aaron@example.com."""
    out = run("A@Example.com")

    assert out["A@Example.com"]["responseStatus"] == "accepted", (
        "a differently-cased address is the same person to a mail system"
    )


def test_an_event_with_no_attendees_yet_is_unaffected():
    out = run("new@example.com", existing=[])

    assert set(out) == {"new@example.com"}
    assert out["new@example.com"].get("responseStatus") in (None, "needsAction")

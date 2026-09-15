"""An event with attendees invites them, and says who it invited.

Google's `events.insert` defaults `sendUpdates` to `none`. We never passed it,
so `co gcalendar meet ... --attendees someone@example.com` created the event,
printed a Meet link, and told the attendee nothing. It cost us a live client
meeting on 2026-09-15, whose guest said it plainly:

    "Didn't get an email invite but anyway there is a Google Meet link there"

The same gap sat on update and delete, which is worse: an attendee who *was*
invited is never told that the meeting moved or was cancelled, so they show up
to a dead link.

The CLI could not tell the operator either — "Event created" reads identically
whether three people were invited or nobody was. So the confirmation now names
them, and that is what makes the difference checkable from the output alone.
"""

from unittest.mock import MagicMock

import pytest

from connectonion.useful_tools.google_calendar import GoogleCalendar


class Recorder:
    """A stand-in Google service that records how each call was made."""

    def __init__(self):
        self.insert_kwargs = None
        self.update_kwargs = None
        self.delete_kwargs = None

    def events(self):
        return self

    def get(self, **kwargs):
        # update_event reads the event before patching it, so the fake has to
        # answer that too — an incomplete double fails in a way that looks like
        # the code under test is broken.
        return _Result({"id": "evt_1", "summary": "Standup",
                        "start": {"dateTime": "2026-09-15T16:30:00+10:00"},
                        "end": {"dateTime": "2026-09-15T17:15:00+10:00"},
                        "attendees": [{"email": "a@example.com"}]})

    def insert(self, **kwargs):
        self.insert_kwargs = kwargs
        return _Result({"id": "evt_1", "htmlLink": "https://cal/evt_1",
                        "hangoutLink": "https://meet.google.com/abc-defg-hij"})

    def update(self, **kwargs):
        self.update_kwargs = kwargs
        return _Result({"id": "evt_1", "summary": "Moved"})

    def delete(self, **kwargs):
        self.delete_kwargs = kwargs
        return _Result({})


class _Result:
    def __init__(self, payload):
        self._payload = payload

    def execute(self):
        return self._payload


@pytest.fixture
def calendar(monkeypatch):
    cal = GoogleCalendar.__new__(GoogleCalendar)
    recorder = Recorder()
    monkeypatch.setattr(cal, "_get_service", lambda: recorder, raising=False)
    return cal, recorder


def test_creating_an_event_with_attendees_notifies_them(calendar):
    cal, rec = calendar

    cal.create_event("Kickoff", "2026-09-15 16:30", "2026-09-15 17:15",
                     attendees="a@example.com, b@example.com")

    assert rec.insert_kwargs["sendUpdates"] == "all"


def test_a_meet_invitation_notifies_them(calendar):
    """The exact call that failed on a real client."""
    cal, rec = calendar

    cal.create_meet("Intro", "2026-09-15 16:30", "2026-09-15 17:15",
                    attendees="guest@example.com")

    assert rec.insert_kwargs["sendUpdates"] == "all"


def test_moving_a_meeting_tells_the_people_in_it(calendar):
    """Worse than never inviting: they hold the old slot and arrive to nothing."""
    cal, rec = calendar

    cal.update_event("evt_1", start_time="2026-09-16 09:00")

    assert rec.update_kwargs["sendUpdates"] == "all"


def test_cancelling_tells_them_too(calendar):
    cal, rec = calendar

    cal.delete_event("evt_1")

    assert rec.delete_kwargs["sendUpdates"] == "all"


def test_an_event_with_nobody_in_it_does_not_ask_google_to_mail_anyone(calendar):
    """`sendUpdates=all` on a solo event is a pointless round trip, and it makes
    "who was notified" unanswerable by making it always 'everyone'."""
    cal, rec = calendar

    cal.create_event("Focus block", "2026-09-15 16:30", "2026-09-15 17:15")

    assert rec.insert_kwargs["sendUpdates"] == "none"


def test_the_confirmation_names_who_was_invited(calendar):
    """"Event created" read the same whether three people were invited or none."""
    cal, rec = calendar

    out = cal.create_event("Kickoff", "2026-09-15 16:30", "2026-09-15 17:15",
                           attendees="a@example.com, b@example.com")

    assert "a@example.com" in out and "b@example.com" in out
    assert "Invitations sent" in out


def test_the_confirmation_says_so_when_there_was_nobody_to_invite(calendar):
    cal, rec = calendar

    out = cal.create_event("Focus block", "2026-09-15 16:30", "2026-09-15 17:15")

    assert "Invitations sent" not in out

"""An invented week for the Agenda calendar, as the two providers answer it (#2998, #3087).

Thursday 1 October 2026 is "today". The week is honest about what a calendar has to draw: an early event
(05:30), a late one (21:30), two back to back, two that overlap, a 90-minute one, a quarter-hour one, a
single all-day event and one that runs three days, from two providers, and one event outside the week.
"""

from datetime import datetime, timezone

FROZEN = datetime(2026, 10, 1, 12, tzinfo=timezone.utc)  # a Thursday


def _google(id_, title, start, end, **more):
    return {"id": id_, "summary": title, "htmlLink": f"https://calendar.example/{id_}",
            "start": {"dateTime": f"2026-10-{start}:00Z"}, "end": {"dateTime": f"2026-10-{end}:00Z"}, **more}


def _outlook(id_, title, start, end):
    return {"id": id_, "subject": title, "webLink": f"https://outlook.example/{id_}",
            "start": {"dateTime": f"2026-10-{start}:00.0000000", "timeZone": "UTC"},
            "end": {"dateTime": f"2026-10-{end}:00.0000000", "timeZone": "UTC"}}


GOOGLE = [
    _google("g1", "Pilot renewal call with Fernhill", "02T09:30", "02T10:00", location="Fernhill Labs, Room 2",
            attendees=[{"email": "mara@fernhill.example"}]),
    {"id": "g2", "summary": "Harbour offsite", "htmlLink": "https://calendar.example/g2",
     "start": {"date": "2026-10-05"}, "end": {"date": "2026-10-08"}},  # three days: Google's end is the day after
    _google("g3", "Dentist", "01T16:00", "01T16:45"),
    _google("g4", "Board dinner", "20T19:00", "20T21:00"),
    _google("g5", "Dawn tide check", "02T05:30", "02T06:15"),
    _google("g6", "Design review", "02T10:00", "02T11:30", location="Quarry Lane Studio"),  # 90 minutes, back to back with g1
    _google("g7", "Night ferry to Cove", "03T21:30", "03T23:00"),
    {"id": "g8", "summary": "Kiln firing day", "htmlLink": "https://calendar.example/g8",
     "start": {"date": "2026-10-03"}, "end": {"date": "2026-10-04"}},
    _google("g9", "Lunch with Mara", "01T12:30", "01T13:30", attendees=[{"email": "mara@fernhill.example"}]),
]
OUTLOOK = [
    _outlook("o1", "Quarterly receipts with Ines", "01T08:00", "01T08:30"),
    _outlook("o2", "Supplier call", "02T10:30", "02T11:00"),  # inside the design review
    _outlook("o3", "Standup", "01T08:30", "01T08:45"),  # a quarter of an hour, back to back with o1
]
# What each account listed (#3087): Google has one calendar of his and three shared ones that are never read.
LISTED = {"read": 1, "left_out": {"freeBusyReader": 2, "reader": 1}}
ALL_OWN = {"read": 2, "left_out": {}}
FILING = """# Harbour filing

## Status
2026-09-28 — The Harbour return must be filed; due 2026-10-06 [1]

Sources: outlook:aa11 (2026-09-28)
"""
INVOICE = "# Fernhill invoice\n\n## Status\n2026-09-20 — Send the pilot invoice; due 2026-09-25 [1]\n"

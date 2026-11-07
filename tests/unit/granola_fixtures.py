"""Synthetic Granola API responses shared by Granola unit tests.

No real credentials or network access required.
PROFILE  = "work"          (non-secret user-chosen label, not the API key)
FOLDER_ID = "fld-fixture"  (personal folder under test)
All note dicts include private_notes_* and attendee emails to prove they are
excluded from adapter output; they must never appear in any record envelope.
"""

import httpx
import pytest

BASE = "https://public-api.granola.ai/v1"
PROFILE = "work"
FOLDER_ID = "fld-fixture"
SPACE_ID = "spc-fixture"
_API_KEY = "grn_unit-test-key-do-not-use"  # never a real key; leading underscore = internal


# ---------------------------------------------------------------------------
# Synthetic folder list
# ---------------------------------------------------------------------------

# Single-page folder response (default fixture route).
FOLDERS_PAGE = {
    "folders": [
        {"id": "fld-fixture", "name": "Team Meetings", "space_id": None},
        {"id": "fld-other",   "name": "Personal",      "space_id": None},
    ],
    "hasMore": False,
    "cursor":  None,
}

# A folder that belongs to a shared space (space_id is not None).
# Used to verify that handle_granola_folders() filters it out.
FOLDER_IN_SPACE = {"id": "fld-in-space", "name": "Shared Team Space Folder", "space_id": "spc-fixture"}

# Two-page folder scenario — page 1.
FOLDERS_PAGE_1 = {
    "folders": [{"id": "fld-fixture", "name": "Team Meetings", "space_id": None}],
    "hasMore": True,
    "cursor":  "cursor_f2",
}

# Two-page folder scenario — page 2.
FOLDERS_PAGE_2 = {
    "folders": [{"id": "fld-other", "name": "Personal", "space_id": None}],
    "hasMore": False,
    "cursor":  None,
}

# Repeated folder cursor — signals a broken pagination loop.
FOLDERS_REPEAT_CURSOR = {
    "folders": [{"id": "fld-fixture", "name": "Team Meetings", "space_id": None}],
    "hasMore": True,
    "cursor":  "cursor_same",
}

# ---------------------------------------------------------------------------
# Synthetic individual notes
# Private notes and attendee emails are intentionally present here so tests
# can assert they are *absent* in every generated record.
# ---------------------------------------------------------------------------

# Full note with all optional fields populated.
NOTE_FULL = {
    "id": "not_note1",
    "title": "Weekly Sync",
    "created_at": "2026-10-20T10:00:00Z",
    "updated_at": "2026-10-20T11:30:00Z",
    "web_url": "https://granola.ai/notes/not_note1",
    "folder_id": "fld-fixture",
    "space_id": None,
    "calendar_event": {
        "id": "cal_event1",
        "scheduled_start": "2026-10-20T10:00:00Z",
        "scheduled_end":   "2026-10-20T11:00:00Z",
    },
    "people": [
        {"full_name": "Alice Smith", "email": "alice@example.com"},  # email MUST be excluded
        {"full_name": "Bob Jones",   "email": "bob@example.com"},    # email MUST be excluded
    ],
    "summary": {
        "plain_text": "We discussed Q4 planning and budget allocation.",
        "markdown":   "## Q4 Planning\n\nWe discussed Q4 planning and budget allocation.",
    },
    "private_notes_text":     "Alice seemed hesitant.",  # MUST be excluded
    "private_notes_markdown": "**Alice** seemed hesitant.",  # MUST be excluded
}

# Minimal note: no calendar event, no people, no private notes.
NOTE_MINIMAL = {
    "id": "not_note2",
    "title": "1:1 with Bob",
    "created_at": "2026-10-21T14:00:00Z",
    "updated_at": "2026-10-21T14:45:00Z",
    "web_url": "https://granola.ai/notes/not_note2",
    "folder_id": "fld-fixture",
    "space_id": None,
    "calendar_event": None,
    "people": [],
    "summary": {
        "plain_text": "Bob updated on his project progress.",
        "markdown":   "## Bob's Updates\n\nBob updated on his project progress.",
    },
    "private_notes_text":     "",
    "private_notes_markdown": "",
}

# Note in a space (not a folder), no calendar event.
NOTE_IN_SPACE = {
    "id": "not_note3",
    "title": "Space Meeting",
    "created_at": "2026-10-22T09:00:00Z",
    "updated_at": "2026-10-22T09:50:00Z",
    "web_url": "https://granola.ai/notes/not_note3",
    "folder_id": None,
    "space_id": "spc-fixture",
    "calendar_event": None,
    "people": [{"full_name": "Carol Lee", "email": "carol@example.com"}],
    "summary": {
        "plain_text": "Space meeting summary.",
        "markdown":   "Space meeting summary.",
    },
    "private_notes_text":     None,
    "private_notes_markdown": None,
}

# Note with only markdown summary (no plain_text).
NOTE_MARKDOWN_ONLY = {
    "id": "not_note4",
    "title": "Planning Session",
    "created_at": "2026-10-23T08:00:00Z",
    "updated_at": "2026-10-23T08:50:00Z",
    "web_url": "https://granola.ai/notes/not_note4",
    "folder_id": "fld-fixture",
    "space_id": None,
    "calendar_event": None,
    "people": [],
    "summary": {
        "plain_text": None,
        "markdown":   "## Planning\n\nFocus on Q1 goals.",
    },
    "private_notes_text":     None,
    "private_notes_markdown": None,
}

# ---------------------------------------------------------------------------
# Synthetic list-notes API responses (cursor-based pagination)
# ---------------------------------------------------------------------------

# Single page — no further pages.
NOTES_SINGLE_PAGE = {
    "notes":   [NOTE_FULL, NOTE_MINIMAL],
    "hasMore": False,
    "cursor":  None,
}

# Two-page scenario — page 1.
NOTES_PAGE_1 = {
    "notes":   [NOTE_FULL],
    "hasMore": True,
    "cursor":  "cursor_page2",
}

# Two-page scenario — page 2.
NOTES_PAGE_2 = {
    "notes":   [NOTE_MINIMAL],
    "hasMore": False,
    "cursor":  None,
}

# Empty result (no notes matched the filter).
NOTES_EMPTY = {
    "notes":   [],
    "hasMore": False,
    "cursor":  None,
}

# verify() response: minimal 1-note probe.
NOTES_VERIFY_PROBE = {
    "notes":   [NOTE_FULL],
    "hasMore": True,
    "cursor":  "cursor_more",
}

# Repeated cursor — signals a broken API pagination loop.
NOTES_REPEAT_CURSOR = {
    "notes":   [NOTE_FULL],
    "hasMore": True,
    "cursor":  "cursor_same",
}

# ---------------------------------------------------------------------------
# Synthetic error responses
# ---------------------------------------------------------------------------

ERR_401 = {"error": "Unauthorized", "message": "API key missing or invalid."}
ERR_403 = {"error": "Forbidden", "message": "This resource is not accessible with your key."}
ERR_404 = {"error": "NotFound", "message": "Note not found, deleted, or not yet processed."}
ERR_429 = {"error": "RateLimited", "message": "Too many requests."}
ERR_500 = {"error": "InternalServerError", "message": "An unexpected error occurred."}

# ---------------------------------------------------------------------------
# pytest fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def granola_env(monkeypatch):
    """Inject a safe synthetic GRANOLA_API_KEY for every test that imports this fixture."""
    monkeypatch.setenv("GRANOLA_API_KEY", _API_KEY)


# ---------------------------------------------------------------------------
# Phase 5: note stubs (lightweight metadata, for co granola notes command)
# ---------------------------------------------------------------------------

# Active note stub — no deleted_at; safe to list in co granola notes.
NOTE_STUB_1 = {
    "id": "not_note1",
    "title": "Weekly Sync",
    "created_at": "2026-10-20T10:00:00Z",
    "updated_at": "2026-10-20T11:30:00Z",
    "deleted_at": None,
}

# Active note stub — second fixture for multi-stub tests.
NOTE_STUB_2 = {
    "id": "not_note2",
    "title": "1:1 with Bob",
    "created_at": "2026-10-21T14:00:00Z",
    "updated_at": "2026-10-21T14:45:00Z",
    "deleted_at": None,
}

# Deleted note stub — deleted_at is set; must be filtered out by co granola notes.
NOTE_STUB_DELETED = {
    "id": "not_deleted",
    "title": "Deleted Meeting",
    "created_at": "2026-10-18T09:00:00Z",
    "updated_at": "2026-10-18T10:00:00Z",
    "deleted_at": "2026-10-19T08:00:00Z",
}

# Full note with deleted_at set — simulates a race condition where a note is
# deleted between list_notes() and the detail fetch in co granola import.
# The adapter's _granola_shape_problems() must reject this note.
NOTE_DELETED_FULL = {
    "id": "not_race",
    "title": "Race Condition Note",
    "created_at": "2026-10-20T10:00:00Z",
    "updated_at": "2026-10-20T11:30:00Z",
    "deleted_at": "2026-10-21T00:00:00Z",
    "web_url": "https://granola.ai/notes/not_race",
    "folder_id": "fld-fixture",
    "space_id": None,
    "calendar_event": None,
    "people": [],
    "summary": {"plain_text": "Deleted note.", "markdown": "Deleted note."},
    "private_notes_text": None,
    "private_notes_markdown": None,
}


@pytest.fixture
def granola_api(monkeypatch, granola_env):
    """Route-based httpx mock for the Granola public API.

    Returns (routes, calls) where:
      routes: mutable dict {path: (status, body) | body | callable}
      calls:  list of {"method", "path", "params", "headers"} appended per request

    Tests may modify routes before instantiating GranolaClient to inject errors
    or alternative page responses.  The fixture asserts all requests use GET.
    """
    routes: dict = {
        "/v1/notes":           (200, NOTES_SINGLE_PAGE),
        "/v1/folders":         (200, FOLDERS_PAGE),
        "/v1/notes/not_note1": (200, NOTE_FULL),
        "/v1/notes/not_note2": (200, NOTE_MINIMAL),
        "/v1/notes/not_note3": (200, NOTE_IN_SPACE),
    }
    calls: list[dict] = []

    class _MockTransport(httpx.BaseTransport):
        def handle_request(self, request: httpx.Request) -> httpx.Response:
            assert request.method == "GET", (
                f"GranolaClient must only use GET; got {request.method} {request.url}"
            )
            path = request.url.path
            params = dict(request.url.params)
            calls.append({
                "method":  request.method,
                "path":    path,
                "params":  params,
                "headers": dict(request.headers),
            })
            entry = routes.get(path)
            if entry is None:
                return httpx.Response(
                    404, json=ERR_404,
                    request=request,
                )
            if callable(entry):
                entry = entry()
            status, body = entry if isinstance(entry, tuple) else (200, entry)
            return httpx.Response(status, json=body, request=request)

    # Patch httpx.Client so GranolaClient picks up the mock transport when
    # it creates its own client instance.
    original_init = httpx.Client.__init__

    def patched_init(self_client, **kwargs):
        kwargs["transport"] = _MockTransport()
        original_init(self_client, **kwargs)

    monkeypatch.setattr(httpx.Client, "__init__", patched_init)
    return routes, calls

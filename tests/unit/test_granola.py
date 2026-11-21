"""Unit tests for connectonion/useful_tools/granola.py — GranolaClient (Phase 2).

Covered by these tests:
  - GranolaConfigError on missing / empty GRANOLA_API_KEY
  - API key is transmitted via Bearer header and never appears in return values or error text
  - GranolaAuthError on HTTP 401; GranolaPermissionError on HTTP 403
  - verify() happy path; empty-notes path; key-not-in-result check
  - list_folders() returns folder list; empty list is valid
  - list_notes() single-page, two-page cursor pagination
  - list_notes() page_size = min(_MAX_PAGE_SIZE, remaining) per request
  - list_notes() date filter params forwarded to API
  - list_notes() repeated cursor → GranolaIncompleteRead with partial_pages
  - list_notes() hasMore=true but cursor absent → GranolaIncompleteRead
  - list_notes() MAX_PAGES limit → GranolaIncompleteRead
  - list_notes() missing folder_id → GranolaConfigError
  - list_notes() invalid limit → GranolaConfigError
  - list_notes() limit=0 and limit=MAX_SELECTED+1 rejected
  - list_notes() 401/403 propagate; empty result valid
  - 429 / 500 retry exhaustion → GranolaIncompleteRead with partial_pages and reason
  - partial_pages carries notes from pages that succeeded before the failure
  - get_note() happy path; 404 → ValueError; 401/403 propagate
"""

# Register granola_fixtures as a pytest plugin so granola_api / granola_env
# fixtures are discovered (the file is not conftest.py, so pytest_plugins is required).
pytest_plugins = ["granola_fixtures"]

import pytest

import connectonion.useful_tools.granola as granola_mod
from connectonion.useful_tools.granola import (
    GranolaAuthError,
    GranolaClient,
    GranolaConfigError,
    GranolaIncompleteRead,
    GranolaPermissionError,
    MAX_PAGES,
    MAX_SELECTED,
    _MAX_PAGE_SIZE,
    _MAX_RETRIES,
)
from tests.unit.granola_fixtures import (
    ERR_401,
    ERR_403,
    ERR_404,
    ERR_429,
    ERR_500,
    FOLDER_ID,
    FOLDERS_PAGE,
    FOLDERS_PAGE_1,
    FOLDERS_PAGE_2,
    FOLDERS_REPEAT_CURSOR,
    NOTE_FULL,
    NOTE_MINIMAL,
    NOTES_EMPTY,
    NOTES_PAGE_1,
    NOTES_PAGE_2,
    NOTES_REPEAT_CURSOR,
    NOTES_SINGLE_PAGE,
    NOTES_VERIFY_PROBE,
    _API_KEY,
)


# ============================================================================
# Init / authentication
# ============================================================================


class TestInit:
    def test_missing_key_raises_config_error(self, monkeypatch):
        monkeypatch.delenv("GRANOLA_API_KEY", raising=False)
        with pytest.raises(GranolaConfigError, match="GRANOLA_API_KEY"):
            GranolaClient()

    def test_empty_key_raises_config_error(self, monkeypatch):
        monkeypatch.setenv("GRANOLA_API_KEY", "")
        with pytest.raises(GranolaConfigError, match="GRANOLA_API_KEY"):
            GranolaClient()

    def test_key_not_in_config_error_message(self, monkeypatch):
        """GranolaConfigError for missing key must not contain any credential value."""
        monkeypatch.delenv("GRANOLA_API_KEY", raising=False)
        with pytest.raises(GranolaConfigError) as exc_info:
            GranolaClient()
        assert _API_KEY not in str(exc_info.value)

    def test_valid_key_constructs_client(self, granola_api):
        client = GranolaClient()
        assert isinstance(client, GranolaClient)

    def test_bearer_header_sent_with_every_request(self, granola_api):
        """Authorization: Bearer must appear in all API calls."""
        routes, calls = granola_api
        GranolaClient().verify()
        assert calls, "Expected at least one API call"
        for call in calls:
            auth = call["headers"].get("authorization", "")
            assert auth.startswith("Bearer "), (
                f"Expected Authorization: Bearer ...; got {auth!r}"
            )

    def test_bearer_token_value_equals_api_key(self, granola_api):
        """The Bearer token must equal the value from GRANOLA_API_KEY env var."""
        routes, calls = granola_api
        GranolaClient().verify()
        auth = calls[0]["headers"].get("authorization", "")
        assert auth == f"Bearer {_API_KEY}"

    def test_only_get_requests_are_made(self, granola_api):
        """GranolaClient must never issue non-GET requests (read-only contract)."""
        routes, calls = granola_api
        client = GranolaClient()
        client.verify()
        client.list_folders()
        client.list_notes(folder_id=FOLDER_ID)
        for call in calls:
            assert call["method"] == "GET", f"Non-GET request: {call}"


# ============================================================================
# verify()
# ============================================================================


class TestVerify:
    def test_verify_returns_verified_read_true(self, granola_api):
        result = GranolaClient().verify()
        assert result["verified_read"] is True

    def test_verify_note_field_is_string(self, granola_api):
        result = GranolaClient().verify()
        assert isinstance(result["note"], str)

    def test_verify_note_title_from_first_note(self, granola_api):
        routes, calls = granola_api
        routes["/v1/notes"] = (200, NOTES_VERIFY_PROBE)
        result = GranolaClient().verify()
        assert result["note"] == NOTE_FULL["title"]

    def test_verify_no_notes_placeholder(self, granola_api):
        routes, calls = granola_api
        routes["/v1/notes"] = (200, NOTES_EMPTY)
        result = GranolaClient().verify()
        assert result == {"verified_read": True, "note": "(no notes yet)"}

    def test_verify_result_does_not_contain_api_key(self, granola_api):
        """verify() return value must never expose the API key."""
        result = GranolaClient().verify()
        assert _API_KEY not in str(result)

    def test_verify_401_raises_auth_error(self, granola_api):
        routes, calls = granola_api
        routes["/v1/notes"] = (401, ERR_401)
        with pytest.raises(GranolaAuthError):
            GranolaClient().verify()

    def test_verify_403_raises_permission_error(self, granola_api):
        routes, calls = granola_api
        routes["/v1/notes"] = (403, ERR_403)
        with pytest.raises(GranolaPermissionError):
            GranolaClient().verify()

    def test_verify_sends_page_size_1(self, granola_api):
        """verify() must use page_size=1 to minimise data read."""
        routes, calls = granola_api
        GranolaClient().verify()
        notes_calls = [c for c in calls if c["path"] == "/v1/notes"]
        assert notes_calls
        assert notes_calls[0]["params"].get("page_size") in ("1", 1)


# ============================================================================
# list_folders()
# ============================================================================


class TestListFolders:
    def test_returns_folder_list(self, granola_api):
        folders = GranolaClient().list_folders()
        assert isinstance(folders, list)
        assert len(folders) == 2
        assert folders[0]["id"] == "fld-fixture"
        assert folders[1]["id"] == "fld-other"

    def test_empty_folders_is_valid(self, granola_api):
        routes, calls = granola_api
        routes["/v1/folders"] = (200, {"folders": []})
        folders = GranolaClient().list_folders()
        assert folders == []

    def test_401_raises_auth_error(self, granola_api):
        routes, calls = granola_api
        routes["/v1/folders"] = (401, ERR_401)
        with pytest.raises(GranolaAuthError):
            GranolaClient().list_folders()

    def test_403_raises_permission_error(self, granola_api):
        routes, calls = granola_api
        routes["/v1/folders"] = (403, ERR_403)
        with pytest.raises(GranolaPermissionError):
            GranolaClient().list_folders()

    def test_folders_result_does_not_contain_api_key(self, granola_api):
        folders = GranolaClient().list_folders()
        assert _API_KEY not in str(folders)

    def test_two_page_pagination_fetches_all_folders(self, granola_api):
        """list_folders() must follow cursor pagination to collect all folders."""
        routes, calls = granola_api
        page_responses = [FOLDERS_PAGE_1, FOLDERS_PAGE_2]
        call_idx = [0]

        def paginated():
            resp = page_responses[call_idx[0] % len(page_responses)]
            call_idx[0] += 1
            return (200, resp)

        routes["/v1/folders"] = paginated
        folders = GranolaClient().list_folders()
        assert len(folders) == 2
        assert folders[0]["id"] == "fld-fixture"
        assert folders[1]["id"] == "fld-other"
        folder_calls = [c for c in calls if c["path"] == "/v1/folders"]
        assert len(folder_calls) == 2

    def test_folders_second_page_sends_cursor(self, granola_api):
        """The cursor from page 1 must appear in the page-2 request."""
        routes, calls = granola_api
        page_responses = [FOLDERS_PAGE_1, FOLDERS_PAGE_2]
        call_idx = [0]

        def paginated():
            resp = page_responses[call_idx[0] % len(page_responses)]
            call_idx[0] += 1
            return (200, resp)

        routes["/v1/folders"] = paginated
        GranolaClient().list_folders()
        folder_calls = [c for c in calls if c["path"] == "/v1/folders"]
        assert "cursor" not in folder_calls[0]["params"]
        assert folder_calls[1]["params"].get("cursor") == FOLDERS_PAGE_1["cursor"]

    def test_folders_repeated_cursor_raises_incomplete_read(self, granola_api):
        routes, calls = granola_api
        routes["/v1/folders"] = lambda: (200, FOLDERS_REPEAT_CURSOR)
        with pytest.raises(GranolaIncompleteRead) as exc_info:
            GranolaClient().list_folders()
        exc = exc_info.value
        assert "cursor" in exc.reason.lower()
        assert len(exc.partial_pages) == 2

    def test_folders_has_more_no_cursor_raises_incomplete_read(self, granola_api):
        routes, calls = granola_api
        routes["/v1/folders"] = lambda: (200, {
            "folders": [{"id": "fld-fixture"}], "hasMore": True, "cursor": None,
        })
        with pytest.raises(GranolaIncompleteRead) as exc_info:
            GranolaClient().list_folders()
        exc = exc_info.value
        assert "cursor" in exc.reason.lower()
        assert len(exc.partial_pages) == 1

    def test_folders_500_raises_incomplete_read(self, granola_api, monkeypatch):
        monkeypatch.setattr(granola_mod.time, "sleep", lambda _: None)
        routes, calls = granola_api
        routes["/v1/folders"] = lambda: (500, ERR_500)
        with pytest.raises(GranolaIncompleteRead) as exc_info:
            GranolaClient().list_folders()
        assert "500" in exc_info.value.reason

    def test_folders_noncontiguous_cursor_loop_raises_incomplete_read(self, granola_api):
        """A→B→A non-adjacent loop is detected immediately via seen_cursors."""
        routes, calls = granola_api
        cycle = [
            {"folders": [{"id": "fld-a"}], "hasMore": True, "cursor": "cursor_B"},
            {"folders": [{"id": "fld-b"}], "hasMore": True, "cursor": "cursor_A"},
            # page 3 returns cursor_B again — loop
        ]
        call_idx = [0]

        def cycling():
            resp = cycle[call_idx[0] % len(cycle)]
            call_idx[0] += 1
            return (200, resp)

        routes["/v1/folders"] = cycling
        with pytest.raises(GranolaIncompleteRead) as exc_info:
            GranolaClient().list_folders()
        exc = exc_info.value
        assert "cursor" in exc.reason.lower()
        # 3 pages fetched: page 1 (cursor_B), page 2 (cursor_A), page 3 (cursor_B repeated)
        assert len(exc.partial_pages) == 3

    def test_folders_max_pages_raises_incomplete_read_with_partial_pages(
        self, granola_api, monkeypatch
    ):
        """MAX_PAGES guard stops pagination and preserves all pages fetched so far."""
        monkeypatch.setattr(granola_mod, "MAX_PAGES", 2)
        routes, calls = granola_api
        page_num = [0]

        def infinite_pages():
            page_num[0] += 1
            return (200, {
                "folders": [{"id": f"fld-{page_num[0]}"}],
                "hasMore":  True,
                "cursor":   f"cursor_{page_num[0]}",
            })

        routes["/v1/folders"] = infinite_pages
        with pytest.raises(GranolaIncompleteRead) as exc_info:
            GranolaClient().list_folders()
        exc = exc_info.value
        assert "MAX_PAGES" in exc.reason
        # exactly MAX_PAGES=2 pages were fetched and preserved
        assert len(exc.partial_pages) == 2


# ============================================================================
# list_notes() — argument validation
# ============================================================================


class TestListNotesValidation:
    def test_missing_folder_id_raises_config_error(self, granola_api):
        with pytest.raises(GranolaConfigError, match="folder_id"):
            GranolaClient().list_notes()

    def test_limit_zero_raises_config_error(self, granola_api):
        with pytest.raises(GranolaConfigError, match="limit"):
            GranolaClient().list_notes(folder_id=FOLDER_ID, limit=0)

    def test_limit_too_large_raises_config_error(self, granola_api):
        with pytest.raises(GranolaConfigError, match="limit"):
            GranolaClient().list_notes(folder_id=FOLDER_ID, limit=MAX_SELECTED + 1)

    def test_limit_negative_raises_config_error(self, granola_api):
        with pytest.raises(GranolaConfigError, match="limit"):
            GranolaClient().list_notes(folder_id=FOLDER_ID, limit=-1)


# ============================================================================
# list_notes() — happy paths
# ============================================================================


class TestListNotesFetch:
    def test_single_page_returns_all_notes(self, granola_api):
        notes = GranolaClient().list_notes(folder_id=FOLDER_ID)
        assert len(notes) == 2
        assert notes[0]["id"] == NOTE_FULL["id"]
        assert notes[1]["id"] == NOTE_MINIMAL["id"]

    def test_empty_result_is_valid(self, granola_api):
        routes, calls = granola_api
        routes["/v1/notes"] = (200, NOTES_EMPTY)
        notes = GranolaClient().list_notes(folder_id=FOLDER_ID)
        assert notes == []

    def test_two_page_pagination_fetches_all(self, granola_api):
        routes, calls = granola_api
        page_responses = [NOTES_PAGE_1, NOTES_PAGE_2]
        call_idx = [0]

        def paginated():
            resp = page_responses[call_idx[0] % len(page_responses)]
            call_idx[0] += 1
            return (200, resp)

        routes["/v1/notes"] = paginated
        notes = GranolaClient().list_notes(folder_id=FOLDER_ID)
        assert len(notes) == 2
        assert notes[0]["id"] == NOTE_FULL["id"]
        assert notes[1]["id"] == NOTE_MINIMAL["id"]
        # Must have fetched exactly 2 pages
        notes_calls = [c for c in calls if c["path"] == "/v1/notes"]
        assert len(notes_calls) == 2

    def test_second_page_sends_cursor(self, granola_api):
        """The cursor from page 1 must appear as a param in the page-2 request."""
        routes, calls = granola_api
        page_responses = [NOTES_PAGE_1, NOTES_PAGE_2]
        call_idx = [0]

        def paginated():
            resp = page_responses[call_idx[0] % len(page_responses)]
            call_idx[0] += 1
            return (200, resp)

        routes["/v1/notes"] = paginated
        GranolaClient().list_notes(folder_id=FOLDER_ID)
        notes_calls = [c for c in calls if c["path"] == "/v1/notes"]
        assert "cursor" not in notes_calls[0]["params"]
        assert notes_calls[1]["params"].get("cursor") == NOTES_PAGE_1["cursor"]

    def test_folder_id_forwarded_in_params(self, granola_api):
        routes, calls = granola_api
        GranolaClient().list_notes(folder_id=FOLDER_ID)
        notes_call = next(c for c in calls if c["path"] == "/v1/notes")
        assert notes_call["params"].get("folder_id") == FOLDER_ID

    def test_401_raises_auth_error(self, granola_api):
        routes, calls = granola_api
        routes["/v1/notes"] = (401, ERR_401)
        with pytest.raises(GranolaAuthError):
            GranolaClient().list_notes(folder_id=FOLDER_ID)

    def test_403_raises_permission_error(self, granola_api):
        routes, calls = granola_api
        routes["/v1/notes"] = (403, ERR_403)
        with pytest.raises(GranolaPermissionError):
            GranolaClient().list_notes(folder_id=FOLDER_ID)

    def test_result_does_not_contain_api_key(self, granola_api):
        notes = GranolaClient().list_notes(folder_id=FOLDER_ID)
        assert _API_KEY not in str(notes)


# ============================================================================
# list_notes() — limit and page_size
# ============================================================================


class TestListNotesLimit:
    def test_limit_respected(self, granola_api):
        """With limit=1 and a 2-note page, only 1 note is returned."""
        notes = GranolaClient().list_notes(folder_id=FOLDER_ID, limit=1)
        assert len(notes) == 1
        assert notes[0]["id"] == NOTE_FULL["id"]

    def test_page_size_equals_min_of_max_and_remaining(self, granola_api):
        """page_size sent to API must equal min(_MAX_PAGE_SIZE, limit)."""
        routes, calls = granola_api
        GranolaClient().list_notes(folder_id=FOLDER_ID, limit=5)
        notes_call = next(c for c in calls if c["path"] == "/v1/notes")
        page_size = int(notes_call["params"]["page_size"])
        assert page_size == min(_MAX_PAGE_SIZE, 5)

    def test_page_size_caps_at_max_page_size(self, granola_api):
        """Without a limit, page_size must not exceed _MAX_PAGE_SIZE."""
        routes, calls = granola_api
        GranolaClient().list_notes(folder_id=FOLDER_ID)
        notes_call = next(c for c in calls if c["path"] == "/v1/notes")
        page_size = int(notes_call["params"]["page_size"])
        assert page_size <= _MAX_PAGE_SIZE

    def test_limit_1_sends_page_size_1(self, granola_api):
        routes, calls = granola_api
        GranolaClient().list_notes(folder_id=FOLDER_ID, limit=1)
        notes_call = next(c for c in calls if c["path"] == "/v1/notes")
        assert int(notes_call["params"]["page_size"]) == 1

    def test_no_limit_uses_max_selected_as_effective_cap(self, granola_api, monkeypatch):
        """Without explicit limit, at most MAX_SELECTED notes are returned."""
        monkeypatch.setattr(granola_mod, "MAX_SELECTED", 1)
        # NOTES_SINGLE_PAGE has 2 notes; with MAX_SELECTED=1 only 1 should be returned.
        notes = GranolaClient().list_notes(folder_id=FOLDER_ID)
        assert len(notes) == 1
        assert notes[0]["id"] == NOTE_FULL["id"]


# ============================================================================
# list_notes() — date filter params
# ============================================================================


class TestListNotesDateFilters:
    def test_created_after_forwarded(self, granola_api):
        routes, calls = granola_api
        ts = "2026-10-01T00:00:00Z"
        GranolaClient().list_notes(folder_id=FOLDER_ID, created_after=ts)
        notes_call = next(c for c in calls if c["path"] == "/v1/notes")
        assert notes_call["params"].get("created_after") == ts

    def test_updated_after_forwarded(self, granola_api):
        routes, calls = granola_api
        ts = "2026-10-15T00:00:00Z"
        GranolaClient().list_notes(folder_id=FOLDER_ID, updated_after=ts)
        notes_call = next(c for c in calls if c["path"] == "/v1/notes")
        assert notes_call["params"].get("updated_after") == ts

    def test_created_before_forwarded(self, granola_api):
        routes, calls = granola_api
        ts = "2026-10-31T00:00:00Z"
        GranolaClient().list_notes(folder_id=FOLDER_ID, created_before=ts)
        notes_call = next(c for c in calls if c["path"] == "/v1/notes")
        assert notes_call["params"].get("created_before") == ts

    def test_all_date_filters_forwarded_together(self, granola_api):
        routes, calls = granola_api
        GranolaClient().list_notes(
            folder_id=FOLDER_ID,
            created_after="2026-10-01T00:00:00Z",
            updated_after="2026-10-15T00:00:00Z",
            created_before="2026-10-31T00:00:00Z",
        )
        notes_call = next(c for c in calls if c["path"] == "/v1/notes")
        p = notes_call["params"]
        assert p["created_after"] == "2026-10-01T00:00:00Z"
        assert p["updated_after"] == "2026-10-15T00:00:00Z"
        assert p["created_before"] == "2026-10-31T00:00:00Z"

    def test_omitted_date_filters_not_in_params(self, granola_api):
        routes, calls = granola_api
        GranolaClient().list_notes(folder_id=FOLDER_ID)
        notes_call = next(c for c in calls if c["path"] == "/v1/notes")
        p = notes_call["params"]
        assert "created_after" not in p
        assert "updated_after" not in p
        assert "created_before" not in p


# ============================================================================
# list_notes() — pagination protocol violations
# ============================================================================


class TestListNotesPaginationErrors:
    def test_repeated_cursor_raises_incomplete_read(self, granola_api):
        routes, calls = granola_api
        routes["/v1/notes"] = lambda: (200, NOTES_REPEAT_CURSOR)
        with pytest.raises(GranolaIncompleteRead) as exc_info:
            GranolaClient().list_notes(folder_id=FOLDER_ID)
        exc = exc_info.value
        assert "cursor" in exc.reason.lower()
        assert len(exc.partial_pages) == 2  # 2 pages fetched before loop detected

    def test_repeated_cursor_partial_pages_carry_notes(self, granola_api):
        routes, calls = granola_api
        routes["/v1/notes"] = lambda: (200, NOTES_REPEAT_CURSOR)
        with pytest.raises(GranolaIncompleteRead) as exc_info:
            GranolaClient().list_notes(folder_id=FOLDER_ID)
        for page in exc_info.value.partial_pages:
            assert isinstance(page, list)

    def test_has_more_no_cursor_raises_incomplete_read(self, granola_api):
        routes, calls = granola_api
        routes["/v1/notes"] = lambda: (200, {
            "notes": [NOTE_FULL], "hasMore": True, "cursor": None,
        })
        with pytest.raises(GranolaIncompleteRead) as exc_info:
            GranolaClient().list_notes(folder_id=FOLDER_ID)
        exc = exc_info.value
        assert "cursor" in exc.reason.lower()
        assert len(exc.partial_pages) == 1

    def test_noncontiguous_cursor_loop_raises_incomplete_read(self, granola_api):
        """A→B→A non-adjacent loop must be detected via seen_cursors, not just prev-cursor."""
        routes, calls = granola_api
        # Pages cycle A→B→A: cursor_B appears on page 1 and again on page 3.
        cycle = [
            {"notes": [NOTE_FULL],    "hasMore": True, "cursor": "cursor_B"},
            {"notes": [NOTE_MINIMAL], "hasMore": True, "cursor": "cursor_A"},
            # page 3 returns cursor_B again — loop
        ]
        call_idx = [0]

        def cycling():
            resp = cycle[call_idx[0] % len(cycle)]
            call_idx[0] += 1
            return (200, resp)

        routes["/v1/notes"] = cycling
        with pytest.raises(GranolaIncompleteRead) as exc_info:
            GranolaClient().list_notes(folder_id=FOLDER_ID)
        exc = exc_info.value
        assert "cursor" in exc.reason.lower()
        # 3 pages fetched: page 1 (cursor_B), page 2 (cursor_A), page 3 (cursor_B repeated)
        assert len(exc.partial_pages) == 3

    def test_max_pages_limit_raises_incomplete_read(self, granola_api, monkeypatch):
        monkeypatch.setattr(granola_mod, "MAX_PAGES", 1)
        routes, calls = granola_api
        page_num = [0]

        def infinite_pages():
            page_num[0] += 1
            return (200, {
                "notes":   [NOTE_FULL],
                "hasMore": True,
                "cursor":  f"cursor_{page_num[0]}",
            })

        routes["/v1/notes"] = infinite_pages
        with pytest.raises(GranolaIncompleteRead) as exc_info:
            GranolaClient().list_notes(folder_id=FOLDER_ID)
        exc = exc_info.value
        assert "MAX_PAGES" in exc.reason
        assert len(exc.partial_pages) == 1  # exactly 1 page before limit hit


# ============================================================================
# list_notes() — retry / transient errors
# ============================================================================


class TestListNotesRetry:
    def _no_sleep(self, monkeypatch):
        monkeypatch.setattr(granola_mod.time, "sleep", lambda _: None)

    def test_500_exhausts_retries_raises_incomplete_read(self, granola_api, monkeypatch):
        self._no_sleep(monkeypatch)
        routes, calls = granola_api
        routes["/v1/notes"] = lambda: (500, ERR_500)
        with pytest.raises(GranolaIncompleteRead) as exc_info:
            GranolaClient().list_notes(folder_id=FOLDER_ID)
        assert "500" in exc_info.value.reason

    def test_429_exhausts_retries_raises_incomplete_read(self, granola_api, monkeypatch):
        self._no_sleep(monkeypatch)
        routes, calls = granola_api
        routes["/v1/notes"] = lambda: (429, ERR_429)
        with pytest.raises(GranolaIncompleteRead) as exc_info:
            GranolaClient().list_notes(folder_id=FOLDER_ID)
        assert "429" in exc_info.value.reason

    def test_retry_count_is_max_retries_plus_one(self, granola_api, monkeypatch):
        """After all retries, exactly (_MAX_RETRIES + 1) requests must have been made."""
        self._no_sleep(monkeypatch)
        routes, calls = granola_api
        routes["/v1/notes"] = lambda: (500, ERR_500)
        with pytest.raises(GranolaIncompleteRead):
            GranolaClient().list_notes(folder_id=FOLDER_ID)
        notes_calls = [c for c in calls if c["path"] == "/v1/notes"]
        assert len(notes_calls) == _MAX_RETRIES + 1

    def test_transient_failure_empty_partial_pages_when_first_page_fails(
        self, granola_api, monkeypatch
    ):
        self._no_sleep(monkeypatch)
        routes, calls = granola_api
        routes["/v1/notes"] = lambda: (500, ERR_500)
        with pytest.raises(GranolaIncompleteRead) as exc_info:
            GranolaClient().list_notes(folder_id=FOLDER_ID)
        assert exc_info.value.partial_pages == []

    def test_partial_pages_populated_when_later_page_fails(
        self, granola_api, monkeypatch
    ):
        """If page 1 succeeds and page 2 always 500s, partial_pages carries page 1."""
        self._no_sleep(monkeypatch)
        routes, calls = granola_api
        call_idx = [0]

        def flaky():
            call_idx[0] += 1
            if call_idx[0] == 1:
                return (200, NOTES_PAGE_1)
            return (500, ERR_500)

        routes["/v1/notes"] = flaky
        with pytest.raises(GranolaIncompleteRead) as exc_info:
            GranolaClient().list_notes(folder_id=FOLDER_ID)
        exc = exc_info.value
        assert len(exc.partial_pages) == 1
        assert exc.partial_pages[0] == NOTES_PAGE_1["notes"]

    def test_reason_does_not_contain_api_key(self, granola_api, monkeypatch):
        self._no_sleep(monkeypatch)
        routes, calls = granola_api
        routes["/v1/notes"] = lambda: (500, ERR_500)
        with pytest.raises(GranolaIncompleteRead) as exc_info:
            GranolaClient().list_notes(folder_id=FOLDER_ID)
        assert _API_KEY not in exc_info.value.reason

    def test_incomplete_read_has_reason_attribute(self, granola_api, monkeypatch):
        self._no_sleep(monkeypatch)
        routes, calls = granola_api
        routes["/v1/notes"] = lambda: (500, ERR_500)
        with pytest.raises(GranolaIncompleteRead) as exc_info:
            GranolaClient().list_notes(folder_id=FOLDER_ID)
        assert isinstance(exc_info.value.reason, str)
        assert exc_info.value.reason  # non-empty


# ============================================================================
# get_note()
# ============================================================================


class TestGetNote:
    def test_get_full_note(self, granola_api):
        note = GranolaClient().get_note("not_note1")
        assert note["id"] == NOTE_FULL["id"]
        assert note["title"] == NOTE_FULL["title"]

    def test_get_minimal_note(self, granola_api):
        note = GranolaClient().get_note("not_note2")
        assert note["id"] == NOTE_MINIMAL["id"]

    def test_get_note_404_raises_value_error(self, granola_api):
        with pytest.raises(ValueError, match="404"):
            GranolaClient().get_note("not_note_missing")

    def test_get_note_401_raises_auth_error(self, granola_api):
        routes, calls = granola_api
        routes["/v1/notes/not_note1"] = (401, ERR_401)
        with pytest.raises(GranolaAuthError):
            GranolaClient().get_note("not_note1")

    def test_get_note_403_raises_permission_error(self, granola_api):
        routes, calls = granola_api
        routes["/v1/notes/not_note1"] = (403, ERR_403)
        with pytest.raises(GranolaPermissionError):
            GranolaClient().get_note("not_note1")

    def test_get_note_result_does_not_contain_api_key(self, granola_api):
        note = GranolaClient().get_note("not_note1")
        assert _API_KEY not in str(note)


class TestHydrateNotes:
    def test_hydrates_list_stubs_to_detail_objects(self, granola_api):
        stubs = [{"id": "not_note1"}, {"id": "not_note2"}]
        notes = GranolaClient().hydrate_notes(stubs)
        assert [note["id"] for note in notes] == ["not_note1", "not_note2"]

    def test_missing_stub_id_is_configuration_error(self, granola_api):
        with pytest.raises(GranolaConfigError, match="without an id"):
            GranolaClient().hydrate_notes([{}])


# ============================================================================
# GranolaIncompleteRead — exception contract
# ============================================================================


class TestGranolaIncompleteReadContract:
    def test_is_not_value_error(self):
        """GranolaIncompleteRead must not be a ValueError — it carries partial data."""
        exc = GranolaIncompleteRead("test", [])
        assert not isinstance(exc, ValueError)

    def test_attributes_accessible(self):
        pages = [[NOTE_FULL], [NOTE_MINIMAL]]
        exc = GranolaIncompleteRead("some reason", pages)
        assert exc.reason == "some reason"
        assert exc.partial_pages is pages

    def test_str_is_reason(self):
        exc = GranolaIncompleteRead("the reason text", [])
        assert "the reason text" in str(exc)

"""Granola adapter unit tests — Phase-1 contract (record mapping, privacy, schema).

These tests exercise granola_notes_to_records() and validate_profile() using
synthetic fixtures only.  No real tokens or network calls are made.

Covered by Phase 1:
  - Stable IDs, original URL/dates preserved in every record
  - private_notes_text / private_notes_markdown NEVER appear in any record
  - Attendee data (emails AND full names) NEVER appear in any record (personal data excluded from MVP)
  - Space-only notes (folder_id absent) go to AdapterResult.errors, never produce a record
  - summary_kind = "generated_summary" always set
  - Fallback: plain_text preferred; markdown used when plain_text absent
  - Malformed / non-dict items produce AdapterResult.errors, not exceptions
  - Duplicate note IDs in one batch yield one record (first wins)
  - validate_profile() accepts valid labels, rejects invalid ones; also called inside granola_notes_to_records()
  - GranolaIncompleteRead carries partial_pages + reason
  - All exception classes are importable ValueError subclasses (except GranolaIncompleteRead)

Tests that require a live GranolaClient (Phase-2 implementation) are in
tests/unit/test_granola.py; they depend on the granola_api fixture.
"""

import pytest

from connectonion.useful_tools.adapter import (
    RECORD_FIELDS,
    AdapterResult,
    granola_notes_to_records,
    record_id,
    validate_record,
)
from connectonion.useful_tools.granola import (
    PROFILE_RE,
    GranolaAuthError,
    GranolaConfigError,
    GranolaIncompleteRead,
    GranolaPermissionError,
    validate_profile,
)
from granola_fixtures import (
    FOLDER_ID,
    NOTE_FULL,
    NOTE_IN_SPACE,
    NOTE_MARKDOWN_ONLY,
    NOTE_MINIMAL,
    NOTES_SINGLE_PAGE,
    PROFILE,
)

# ---------------------------------------------------------------------------
# Helper: shared assertion for every record produced by the adapter
# ---------------------------------------------------------------------------


def _assert_record_contract(record: dict, profile: str) -> None:
    """Assert that *record* satisfies the shared envelope contract and Granola invariants."""
    problems = validate_record(record)
    assert not problems, f"Contract violations: {problems}"
    assert set(record) <= set(RECORD_FIELDS) | {"media"}, "Unknown top-level fields"
    assert record["source"] == "granola"
    assert record["account"] == profile
    assert record["id"] == record_id("granola", profile, record["external_id"])
    assert record["kind"] == "meeting_note"
    assert record["extensions"].get("summary_kind") == "generated_summary"


def test_current_api_detail_shape_maps_selected_personal_folder_without_private_data():
    """Live API discovery: detail uses folder_membership and summary_text."""
    note = {
        "id": "not-current-shape",
        "title": "Synthetic title",
        "created_at": "2026-10-24T00:00:00Z",
        "updated_at": "2026-10-24T01:00:00Z",
        "web_url": "https://granola.ai/notes/not-current-shape",
        "folder_membership": [{"id": FOLDER_ID, "name": "Personal", "space_id": None}],
        "space_membership": [],
        "summary_text": "Allowed generated summary",
        "summary_markdown": "# Allowed generated summary",
        "owner": {"name": "Private Owner", "email": "owner@example.test"},
        "attendees": [{"name": "Private Attendee", "email": "attendee@example.test"}],
        "private_notes_text": "private",
        "private_notes_markdown": "private",
        "transcript": "private transcript",
        "attachments": [{"id": "attachment"}],
    }
    result = granola_notes_to_records([note], PROFILE, selected_folder_id=FOLDER_ID)
    assert len(result.records) == 1
    record = result.records[0]
    assert record["text"] == "Allowed generated summary"
    assert record["extensions"]["folder_id"] == FOLDER_ID
    assert record["extensions"]["folder_name"] == "Personal"
    for forbidden in ("Private Owner", "owner@example.test", "Private Attendee", "attendee@example.test", "private transcript", "attachment"):
        assert forbidden not in str(record)


# ---------------------------------------------------------------------------
# Privacy — the single most important invariant
# ---------------------------------------------------------------------------


class TestPrivacyExclusion:
    """private_notes_* and attendee emails must never reach a record envelope."""

    def test_private_notes_text_absent(self):
        result = granola_notes_to_records([NOTE_FULL], PROFILE)
        assert result.records
        record = result.records[0]
        # Check top-level and extensions
        record_str = str(record)
        assert "private_notes_text" not in record_str
        assert "Alice seemed hesitant" not in record_str

    def test_private_notes_markdown_absent(self):
        result = granola_notes_to_records([NOTE_FULL], PROFILE)
        record = result.records[0]
        record_str = str(record)
        assert "private_notes_markdown" not in record_str
        assert "Alice** seemed" not in record_str

    def test_attendee_emails_absent(self):
        result = granola_notes_to_records([NOTE_FULL], PROFILE)
        record = result.records[0]
        record_str = str(record)
        assert "alice@example.com" not in record_str
        assert "bob@example.com" not in record_str

    def test_attendees_not_in_extensions(self):
        """Attendee data (full_name and emails) is not stored — personal data excluded from MVP."""
        result = granola_notes_to_records([NOTE_FULL], PROFILE)
        ext = result.records[0]["extensions"]
        assert "attendees" not in ext

    def test_no_transcript_field_in_record(self):
        """Transcript is excluded from MVP; must not appear in any form."""
        result = granola_notes_to_records([NOTE_FULL], PROFILE)
        record = result.records[0]
        record_str = str(record)
        assert "transcript" not in record_str

    def test_no_audio_or_attachment_in_record(self):
        result = granola_notes_to_records([NOTE_FULL], PROFILE)
        record = result.records[0]
        assert not record.get("media"), "MVP: no media references"
        record_str = str(record)
        assert "audio" not in record_str
        assert "attachment" not in record_str

    def test_space_only_note_rejected_not_stored(self):
        """Space-only notes are rejected to errors; no record is stored so no email can leak."""
        result = granola_notes_to_records([NOTE_IN_SPACE], PROFILE)
        assert not result.records
        assert result.errors
        assert "carol@example.com" not in str(result.errors)

    def test_private_notes_none_values_safe(self):
        """None private_notes fields must not cause an error (NOTE_MARKDOWN_ONLY has both as None)."""
        result = granola_notes_to_records([NOTE_MARKDOWN_ONLY], PROFILE)
        assert not result.errors
        assert len(result.records) == 1


# ---------------------------------------------------------------------------
# Record identity and field mapping
# ---------------------------------------------------------------------------


class TestFieldMapping:
    """Verify that each field from the note is mapped to the correct envelope field."""

    def test_stable_id_composition(self):
        result = granola_notes_to_records([NOTE_FULL], PROFILE)
        record = result.records[0]
        assert record["id"] == f"granola:{PROFILE}:{NOTE_FULL['id']}"

    def test_external_id_equals_note_id(self):
        result = granola_notes_to_records([NOTE_FULL], PROFILE)
        assert result.records[0]["external_id"] == NOTE_FULL["id"]

    def test_title_preserved(self):
        result = granola_notes_to_records([NOTE_FULL], PROFILE)
        assert result.records[0]["title"] == NOTE_FULL["title"]

    def test_url_is_web_url(self):
        result = granola_notes_to_records([NOTE_FULL], PROFILE)
        assert result.records[0]["url"] == NOTE_FULL["web_url"]

    def test_at_is_created_at(self):
        result = granola_notes_to_records([NOTE_FULL], PROFILE)
        assert result.records[0]["at"] == NOTE_FULL["created_at"]

    def test_updated_is_updated_at(self):
        result = granola_notes_to_records([NOTE_FULL], PROFILE)
        assert result.records[0]["updated"] == NOTE_FULL["updated_at"]

    def test_text_uses_plain_text_when_available(self):
        result = granola_notes_to_records([NOTE_FULL], PROFILE)
        assert result.records[0]["text"] == NOTE_FULL["summary"]["plain_text"]

    def test_text_falls_back_to_markdown_when_no_plain_text(self):
        result = granola_notes_to_records([NOTE_MARKDOWN_ONLY], PROFILE)
        assert result.records[0]["text"] == NOTE_MARKDOWN_ONLY["summary"]["markdown"]

    def test_folder_id_in_extensions(self):
        result = granola_notes_to_records([NOTE_FULL], PROFILE)
        assert result.records[0]["extensions"]["folder_id"] == NOTE_FULL["folder_id"]

    def test_calendar_event_in_extensions(self):
        """Only meeting time (scheduled_start / scheduled_end) is stored; calendar_event_id is not."""
        result = granola_notes_to_records([NOTE_FULL], PROFILE)
        ext = result.records[0]["extensions"]
        cal = NOTE_FULL["calendar_event"]
        assert "calendar_event_id" not in ext
        assert ext["scheduled_start"] == cal["scheduled_start"]
        assert ext["scheduled_end"] == cal["scheduled_end"]

    def test_none_calendar_event_omitted_from_extensions(self):
        result = granola_notes_to_records([NOTE_MINIMAL], PROFILE)
        ext = result.records[0]["extensions"]
        assert "calendar_event_id" not in ext
        assert "scheduled_start" not in ext
        assert "scheduled_end" not in ext

    def test_empty_attendees_list_omitted_from_extensions(self):
        result = granola_notes_to_records([NOTE_MINIMAL], PROFILE)
        ext = result.records[0]["extensions"]
        assert "attendees" not in ext

    def test_summary_kind_always_set(self):
        for note in [NOTE_FULL, NOTE_MINIMAL, NOTE_MARKDOWN_ONLY]:
            result = granola_notes_to_records([note], PROFILE)
            assert result.records[0]["extensions"]["summary_kind"] == "generated_summary"

    def test_author_is_empty_string(self):
        """Meeting notes have no single author; author must be empty, never an email."""
        result = granola_notes_to_records([NOTE_FULL], PROFILE)
        assert result.records[0]["author"] == ""


# ---------------------------------------------------------------------------
# Contract compliance
# ---------------------------------------------------------------------------


class TestContractCompliance:
    """Every produced record must satisfy the shared envelope contract."""

    def test_full_note_passes_contract(self):
        result = granola_notes_to_records([NOTE_FULL], PROFILE)
        _assert_record_contract(result.records[0], PROFILE)

    def test_minimal_note_passes_contract(self):
        result = granola_notes_to_records([NOTE_MINIMAL], PROFILE)
        _assert_record_contract(result.records[0], PROFILE)

    def test_markdown_only_note_passes_contract(self):
        result = granola_notes_to_records([NOTE_MARKDOWN_ONLY], PROFILE)
        _assert_record_contract(result.records[0], PROFILE)

    def test_batch_from_single_page_all_pass_contract(self):
        notes = NOTES_SINGLE_PAGE["notes"]
        result = granola_notes_to_records(notes, PROFILE)
        assert len(result.records) == len(notes)
        for record in result.records:
            _assert_record_contract(record, PROFILE)

    def test_id_is_deterministic_across_calls(self):
        """Same note → same ID regardless of when it is mapped."""
        r1 = granola_notes_to_records([NOTE_FULL], PROFILE, fetched="2026-10-23T00:00:00Z")
        r2 = granola_notes_to_records([NOTE_FULL], PROFILE, fetched="2026-10-24T00:00:00Z")
        assert r1.records[0]["id"] == r2.records[0]["id"]

    def test_fetched_timestamp_differs_between_calls(self):
        r1 = granola_notes_to_records([NOTE_FULL], PROFILE, fetched="2026-10-23T00:00:00Z")
        r2 = granola_notes_to_records([NOTE_FULL], PROFILE, fetched="2026-10-24T00:00:00Z")
        assert r1.records[0]["fetched"] != r2.records[0]["fetched"]


# ---------------------------------------------------------------------------
# Deduplication
# ---------------------------------------------------------------------------


class TestDeduplication:
    """The same note ID appearing twice in one batch yields exactly one record."""

    def test_duplicate_note_produces_one_record_and_one_error(self):
        result = granola_notes_to_records([NOTE_FULL, NOTE_FULL], PROFILE)
        assert len(result.records) == 1
        assert len(result.errors) == 1
        error_msg = next(iter(result.errors.values()))
        assert "duplicate" in error_msg.lower()

    def test_two_distinct_notes_produce_two_records(self):
        result = granola_notes_to_records([NOTE_FULL, NOTE_MINIMAL], PROFILE)
        assert len(result.records) == 2
        assert not result.errors


# ---------------------------------------------------------------------------
# Malformed input — errors reported, not raised
# ---------------------------------------------------------------------------


class TestMalformedInput:
    """Non-dict items and notes with empty IDs are rejected gracefully."""

    def test_non_dict_item_goes_to_errors(self):
        result = granola_notes_to_records(["not a dict", NOTE_FULL], PROFILE)
        assert len(result.records) == 1
        assert len(result.errors) == 1

    def test_none_item_goes_to_errors(self):
        result = granola_notes_to_records([None, NOTE_FULL], PROFILE)
        assert len(result.records) == 1
        assert len(result.errors) == 1

    def test_note_with_empty_id_goes_to_errors(self):
        bad_note = {**NOTE_FULL, "id": ""}
        result = granola_notes_to_records([bad_note], PROFILE)
        assert not result.records
        assert result.errors

    def test_note_with_missing_id_goes_to_errors(self):
        bad_note = {k: v for k, v in NOTE_FULL.items() if k != "id"}
        result = granola_notes_to_records([bad_note], PROFILE)
        assert not result.records
        assert result.errors

    def test_empty_input_list_yields_empty_result(self):
        result = granola_notes_to_records([], PROFILE)
        assert result.records == []
        assert result.errors == {}

    def test_valid_and_invalid_items_mixed(self):
        """Valid items are kept even when the batch contains invalid ones."""
        result = granola_notes_to_records([NOTE_FULL, "bad", NOTE_MINIMAL], PROFILE)
        ids = {r["external_id"] for r in result.records}
        assert ids == {NOTE_FULL["id"], NOTE_MINIMAL["id"]}
        assert len(result.errors) == 1

    def test_space_only_note_goes_to_errors(self):
        """Notes without folder_id (space-only) are rejected to errors, not records."""
        result = granola_notes_to_records([NOTE_IN_SPACE], PROFILE)
        assert not result.records
        assert len(result.errors) == 1
        error_msg = next(iter(result.errors.values()))
        assert "folder_id" in error_msg or "space" in error_msg.lower()


# ---------------------------------------------------------------------------
# Profile validation
# ---------------------------------------------------------------------------


class TestValidateProfile:
    """validate_profile() enforces the contract frozen in Phase 1."""

    @pytest.mark.parametrize("profile", [
        "work",
        "home",
        "work-2024",
        "a",
        "A",
        "a1",
        "MyTeam",
        "team-alpha-2026",
        "a" * 64,                        # maximum length
        "a" + "b" * 62 + "c",            # 64 chars exactly
    ])
    def test_valid_profiles_accepted(self, profile: str):
        validate_profile(profile)   # must not raise

    @pytest.mark.parametrize("profile, reason", [
        ("",                    "empty string"),
        ("-work",               "starts with hyphen"),
        ("work-",               "ends with hyphen"),
        ("my:profile",          "contains colon"),
        ("my profile",          "contains space"),
        ("my.profile",          "contains dot"),
        ("a" * 65,              "too long"),
        ("work@home",           "contains @"),
        ("alice@example.com",   "looks like email"),
        ("-",                   "lone hyphen"),
        ("--",                  "double hyphen only"),
    ])
    def test_invalid_profiles_rejected(self, profile: str, reason: str):
        with pytest.raises(GranolaConfigError, match="Invalid profile"):
            validate_profile(profile)

    def test_colon_rejected_to_protect_record_id(self):
        """A colon in the profile would break the 'granola:<profile>:<note_id>' ID."""
        with pytest.raises(GranolaConfigError):
            validate_profile("gran:ola")

    def test_non_string_rejected(self):
        with pytest.raises(GranolaConfigError):
            validate_profile(None)   # type: ignore[arg-type]

    def test_integer_rejected(self):
        with pytest.raises(GranolaConfigError):
            validate_profile(42)     # type: ignore[arg-type]

    def test_invalid_profile_raises_in_converter(self):
        """granola_notes_to_records() calls validate_profile(); a colon breaks the ID."""
        with pytest.raises(GranolaConfigError, match="Invalid profile"):
            granola_notes_to_records([NOTE_FULL], "my:profile")


# ---------------------------------------------------------------------------
# Exception classes
# ---------------------------------------------------------------------------


class TestExceptionClasses:
    """All exception classes must be importable and correctly typed."""

    def test_config_error_is_value_error(self):
        err = GranolaConfigError("missing key")
        assert isinstance(err, ValueError)

    def test_auth_error_is_value_error(self):
        err = GranolaAuthError("401")
        assert isinstance(err, ValueError)

    def test_permission_error_is_value_error(self):
        err = GranolaPermissionError("403")
        assert isinstance(err, ValueError)

    def test_incomplete_read_carries_partial_pages_and_reason(self):
        pages = [[{"id": "not_note1"}], [{"id": "not_note2"}]]
        err = GranolaIncompleteRead("rate limit exhausted after 3 retries", pages)
        assert err.reason == "rate limit exhausted after 3 retries"
        assert err.partial_pages == pages
        assert str(err) == "rate limit exhausted after 3 retries"

    def test_incomplete_read_is_not_value_error(self):
        """GranolaIncompleteRead is a distinct Exception, not a ValueError."""
        err = GranolaIncompleteRead("test", [])
        assert isinstance(err, Exception)
        assert not isinstance(err, ValueError)

    def test_incomplete_read_empty_partial_pages(self):
        err = GranolaIncompleteRead("first request failed", [])
        assert err.partial_pages == []


# ---------------------------------------------------------------------------
# P2 regression: legacy folder fallback must gate on space_id is None
# ---------------------------------------------------------------------------


class TestGranolaPersonalFolderLegacyFallback:
    """_granola_personal_folder legacy path (no folder_membership key) must also
    require space_id is None.  Previously only folder_id was checked, allowing a
    shared-space note with the correct folder_id to pass the personal-folder guard."""

    def test_legacy_note_with_matching_folder_id_and_null_space_id_is_accepted(self):
        """Note has no folder_membership; folder_id matches; space_id is null → accepted."""
        from connectonion.useful_tools.adapter import _granola_personal_folder
        note = {
            "id": "not-legacy-personal",
            "folder_id": FOLDER_ID,
            "space_id": None,
        }
        result = _granola_personal_folder(note, selected_folder_id=FOLDER_ID)
        assert result is not None
        assert result["id"] == FOLDER_ID

    def test_legacy_note_with_matching_folder_id_but_non_null_space_id_is_rejected(self):
        """P2 fix: note has no folder_membership; folder_id matches; but space_id is set.
        Before the fix this note would have been admitted (second-layer bypass).
        After the fix, space_id != None must cause rejection."""
        from connectonion.useful_tools.adapter import _granola_personal_folder
        from granola_fixtures import SPACE_ID
        note = {
            "id": "not-legacy-space",
            "folder_id": FOLDER_ID,
            "space_id": SPACE_ID,   # shared-space note — must be rejected
        }
        result = _granola_personal_folder(note, selected_folder_id=FOLDER_ID)
        assert result is None

    def test_legacy_note_non_null_space_id_produces_shape_problem(self):
        """_granola_shape_problems rejects a legacy-shape shared-space note."""
        from connectonion.useful_tools.adapter import _granola_shape_problems
        from granola_fixtures import SPACE_ID
        note = {
            "id": "not-legacy-space-shape",
            "folder_id": FOLDER_ID,
            "space_id": SPACE_ID,
            "deleted_at": None,
        }
        problems = _granola_shape_problems(note, selected_folder_id=FOLDER_ID)
        assert len(problems) == 1
        assert "personal" in problems[0].lower() or "space" in problems[0].lower()


# ---------------------------------------------------------------------------
# Constants sanity checks
# ---------------------------------------------------------------------------


class TestConstants:
    """Check that frozen constants match the canvas spec."""

    def test_max_pages_is_1000(self):
        from connectonion.useful_tools.granola import MAX_PAGES
        assert MAX_PAGES == 1_000

    def test_max_selected_is_1000(self):
        from connectonion.useful_tools.granola import MAX_SELECTED
        assert MAX_SELECTED == 1_000

    def test_profile_re_anchored(self):
        """PROFILE_RE must be anchored (fullmatch, not partial)."""
        assert not PROFILE_RE.fullmatch("-bad")
        assert not PROFILE_RE.fullmatch("bad-")
        assert PROFILE_RE.fullmatch("good-profile")

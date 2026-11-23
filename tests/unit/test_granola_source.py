"""Synthetic tests for `co granola changes` / `co granola show` (the #3249 CLI JSON source contract).

Every Granola response here is a fixture served by a fake HTTP client; no key,
network or real note is used.
"""

import copy
import json
from unittest.mock import Mock

import pytest
from typer.testing import CliRunner

import connectonion.useful_tools.granola as granola_mod
from connectonion.cli.main import app
from connectonion.rem.files import state_path, write_json
from connectonion.useful_tools import granola_source as source
from connectonion.useful_tools.granola_source import GranolaSourceError, note_changes, show_note
from tests.unit.granola_fixtures import FOLDER_ID, NOTE_FULL

PERSONAL = {"id": FOLDER_ID, "name": "Team Meetings", "space_id": None}
CHILD = {"id": "fld-child", "name": "Child", "space_id": None, "parent_folder_id": FOLDER_ID}
SHARED = {"id": FOLDER_ID, "name": "Team Meetings", "space_id": "spc-fixture"}

STUB_OLD = {"id": "not_old", "title": "Old", "updated_at": "2026-10-01T09:00:00Z"}
STUB_A = {"id": "not_a", "title": "Planning", "updated_at": "2026-11-02T10:00:00+00:00"}
STUB_B = {"id": "not_b", "title": "Retro", "updated_at": "2026-11-01T12:00:00Z"}
STUB_GONE = {"id": "not_gone", "title": "Gone", "updated_at": "2026-11-03T08:00:00Z",
             "deleted_at": "2026-11-03T08:00:00Z"}

DETAIL = {**copy.deepcopy(NOTE_FULL), "folder_membership": [
    {"id": FOLDER_ID, "name": "Team Meetings", "space_id": None, "email": "member@example.com"}]}


def response(status=200, body=None, headers=None):
    return Mock(status_code=status, json=lambda: body, headers=headers or {})


class FakeHttp:
    """Routes GETs by path; `routes` maps a path to a response or a list of responses."""

    def __init__(self, routes):
        self.routes, self.calls = routes, []

    def get(self, url, params=None):
        path = url.removeprefix(granola_mod.BASE_URL)
        self.calls.append((path, dict(params or {})))
        route = self.routes[path]
        return route.pop(0) if isinstance(route, list) else route


@pytest.fixture
def root(tmp_path):
    return tmp_path / "rem"


def approve(root, selection=None, **source_fields):
    sources = {"granola": {"enabled": True, "consented": True,
                           "remote": {"selection": selection or {"folder_id": FOLDER_ID}}, **source_fields}}
    (root / ".state").mkdir(parents=True, exist_ok=True)
    write_json(state_path(root, "subscriptions.json"), sources)


@pytest.fixture
def api(monkeypatch):
    """Serve fixture routes through the real GranolaClient, with a fixture-only key."""
    monkeypatch.setenv("GRANOLA_API_KEY", "fixture-only-key")
    monkeypatch.setattr(granola_mod.time, "sleep", lambda seconds: None)
    real = granola_mod.GranolaClient

    def install(routes):
        http = FakeHttp(routes)
        monkeypatch.setattr(granola_mod, "GranolaClient", lambda: real(_http=http))
        return http
    return install


def folders(*rows):
    return response(body={"folders": list(rows), "hasMore": False})


def notes(*rows, more=False, cursor=None):
    return response(body={"notes": list(rows), "hasMore": more, "cursor": cursor})


def refuse_client(monkeypatch):
    """Any attempt to read the key or reach Granola fails the test."""
    monkeypatch.setattr(granola_mod, "GranolaClient", Mock(side_effect=AssertionError("Granola was contacted")))


# ---------------------------------------------------------------------------
# Approval is checked first: no key read, no request
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("fields", [
    None,                                       # never approved
    {"enabled": False},                         # disabled
    {"consented": False},                       # awaiting consent
    {"unsubscribed": True},                     # removed by the user
])
def test_unapproved_source_reads_nothing(monkeypatch, root, fields):
    refuse_client(monkeypatch)
    if fields is not None:
        approve(root, **fields)
    for read, value in ((note_changes, "2026-11-01T00:00:00Z"), (show_note, "not_a")):
        with pytest.raises(GranolaSourceError) as error:
            read(root, value)
        assert error.value.code == "approval_required"


@pytest.mark.parametrize("selection", [
    {"folder_id": ""},
    {"folder_id": FOLDER_ID, "include_children": "yes"},
    {"folder_id": FOLDER_ID, "note_id": "not a/note"},
    {"folder_id": FOLDER_ID, "api_key": "x"},
])
def test_malformed_approval_is_invalid_scope(monkeypatch, root, selection):
    refuse_client(monkeypatch)
    approve(root, selection)
    with pytest.raises(GranolaSourceError) as error:
        note_changes(root, "2026-11-01T00:00:00Z")
    assert error.value.code == "invalid_scope"


@pytest.mark.parametrize("since", ["2026-11-01", "2026-11-01T00:00:00", "yesterday", ""])
def test_since_needs_a_timezone_and_is_checked_before_network(monkeypatch, root, since):
    refuse_client(monkeypatch)
    approve(root)
    with pytest.raises(GranolaSourceError) as error:
        note_changes(root, since)
    assert error.value.code == "invalid_since"


def test_missing_key_is_not_configured(monkeypatch, root):
    monkeypatch.delenv("GRANOLA_API_KEY", raising=False)
    monkeypatch.setattr("connectonion.environment.setting", lambda name: None)
    approve(root)
    with pytest.raises(GranolaSourceError) as error:
        note_changes(root, "2026-11-01T00:00:00Z")
    assert error.value.code == "not_configured"


# ---------------------------------------------------------------------------
# changes
# ---------------------------------------------------------------------------

def test_changes_lists_metadata_after_cutoff_sorted_without_summaries(api, root):
    approve(root)
    http = api({"/folders": folders(PERSONAL), "/notes": notes(STUB_A, STUB_OLD, STUB_GONE, STUB_B)})
    rows = note_changes(root, "2026-11-01T00:00:00+00:00")
    assert rows == [
        {"id": "not_b", "version": "2026-11-01T12:00:00Z", "time": "2026-11-01T12:00:00Z", "title": "Retro"},
        {"id": "not_a", "version": "2026-11-02T10:00:00Z", "time": "2026-11-02T10:00:00Z", "title": "Planning"},
    ]
    note_call = [params for path, params in http.calls if path == "/notes"][0]
    assert note_call["folder_id"] == FOLDER_ID and note_call["updated_after"] == "2026-11-01T00:00:00Z"
    assert not any(path.startswith("/notes/") for path, _ in http.calls)   # no body reads


def test_changes_cutoff_is_exclusive(api, root):
    approve(root)
    api({"/folders": folders(PERSONAL), "/notes": notes(STUB_B)})
    assert note_changes(root, "2026-11-01T12:00:00Z") == []


def test_changes_empty_result_is_valid(api, root):
    approve(root)
    api({"/folders": folders(PERSONAL), "/notes": notes()})
    assert note_changes(root, "2026-11-01T00:00:00Z") == []


def test_changes_follows_pagination(api, root):
    approve(root)
    http = api({"/folders": folders(PERSONAL),
                "/notes": [notes(STUB_A, more=True, cursor="page2"), notes(STUB_B)]})
    assert [row["id"] for row in note_changes(root, "2026-11-01T00:00:00Z")] == ["not_b", "not_a"]
    assert [params.get("cursor") for path, params in http.calls if path == "/notes"] == [None, "page2"]


def test_changes_single_note_selection_filters_other_notes(api, root):
    approve(root, {"folder_id": FOLDER_ID, "note_id": "not_a"})
    api({"/folders": folders(PERSONAL), "/notes": notes(STUB_A, STUB_B)})
    assert [row["id"] for row in note_changes(root, "2026-11-01T00:00:00Z")] == ["not_a"]


def test_changes_refuses_to_truncate(api, root, monkeypatch):
    monkeypatch.setattr(source, "MAX_SELECTED", 2)
    approve(root)
    api({"/folders": folders(PERSONAL), "/notes": notes(STUB_A, STUB_B)})
    with pytest.raises(GranolaSourceError) as error:
        note_changes(root, "2026-11-01T00:00:00Z")
    assert error.value.code == "too_many_changes"


@pytest.mark.parametrize("rows,code", [
    ((SHARED,), "out_of_scope"),
    ((PERSONAL, CHILD), "out_of_scope"),
    ((), "not_found"),
])
def test_changes_rechecks_the_approved_folder(api, root, rows, code):
    approve(root)
    http = api({"/folders": folders(*rows), "/notes": notes(STUB_A)})
    with pytest.raises(GranolaSourceError) as error:
        note_changes(root, "2026-11-01T00:00:00Z")
    assert error.value.code == code
    assert not any(path == "/notes" for path, _ in http.calls)


def test_changes_include_children_needs_personal_descendants(api, root):
    approve(root, {"folder_id": FOLDER_ID, "include_children": True})
    api({"/folders": folders(PERSONAL, CHILD), "/notes": notes(STUB_A)})
    assert [row["id"] for row in note_changes(root, "2026-11-01T00:00:00Z")] == ["not_a"]

    shared_child = {**CHILD, "space_id": "spc-fixture"}
    api({"/folders": folders(PERSONAL, shared_child), "/notes": notes(STUB_A)})
    with pytest.raises(GranolaSourceError) as error:
        note_changes(root, "2026-11-01T00:00:00Z")
    assert error.value.code == "out_of_scope"


@pytest.mark.parametrize("failure,code", [
    (response(401), "auth_failed"),
    (response(403), "permission_denied"),
    ([response(429, headers={"Retry-After": "0"})] * 4, "rate_limited"),
    ([response(503)] * 4, "incomplete"),
    (response(418), "unavailable"),
    (response(body={"notes": None}), "incomplete"),
])
def test_changes_provider_failures_are_coded_and_never_partial(api, root, failure, code):
    approve(root)
    api({"/folders": folders(PERSONAL), "/notes": failure if isinstance(failure, list) else failure})
    with pytest.raises(GranolaSourceError) as error:
        note_changes(root, "2026-11-01T00:00:00Z")
    assert error.value.code == code
    assert "fixture-only-key" not in str(error.value)


def test_changes_partial_pagination_failure_is_an_error(api, root):
    approve(root)
    api({"/folders": folders(PERSONAL), "/notes": [notes(STUB_A, more=True, cursor="page2")] + [response(500)] * 4})
    with pytest.raises(GranolaSourceError) as error:
        note_changes(root, "2026-11-01T00:00:00Z")
    assert error.value.code == "incomplete"


def test_credential_shaped_title_is_withheld(api, root):
    approve(root)
    api({"/folders": folders(PERSONAL),
         "/notes": notes({**STUB_A, "title": "key sk-ant-api03-" + "A" * 40})})
    assert note_changes(root, "2026-11-01T00:00:00Z")[0]["title"] == source.WITHHELD


# ---------------------------------------------------------------------------
# show
# ---------------------------------------------------------------------------

def test_show_returns_only_allowed_fields(api, root):
    approve(root)
    api({"/folders": folders(PERSONAL), "/notes/not_note1": response(body=DETAIL)})
    note = show_note(root, "not_note1")
    assert note == {
        "id": "not_note1", "version": "2026-10-20T11:30:00Z", "time": "2026-10-20T11:30:00Z",
        "title": "Weekly Sync", "text": "## Q4 Planning\n\nWe discussed Q4 planning and budget allocation.",
        "author": None, "link": "https://granola.ai/notes/not_note1", "meeting_time": "2026-10-20T10:00:00Z",
    }
    dumped = json.dumps(note)
    for private in ("hesitant", "alice@example.com", "Bob Jones", "member@example.com"):
        assert private not in dumped


def test_show_outside_the_approved_note_is_refused_before_network(monkeypatch, root):
    refuse_client(monkeypatch)
    approve(root, {"folder_id": FOLDER_ID, "note_id": "not_a"})
    with pytest.raises(GranolaSourceError) as error:
        show_note(root, "not_b")
    assert error.value.code == "out_of_scope"


@pytest.mark.parametrize("membership", [
    [{"id": "fld-other", "space_id": None}],
    [{"id": FOLDER_ID, "space_id": "spc-fixture"}],
    [],
])
def test_show_note_in_another_folder_is_out_of_scope(api, root, membership):
    approve(root)
    api({"/folders": folders(PERSONAL), "/notes/not_note1": response(body={**DETAIL, "folder_membership": membership})})
    with pytest.raises(GranolaSourceError) as error:
        show_note(root, "not_note1")
    assert error.value.code == "out_of_scope"


@pytest.mark.parametrize("detail", [response(404), response(body={**DETAIL, "deleted_at": "2026-11-01T00:00:00Z"})])
def test_show_missing_or_deleted_note_is_not_found(api, root, detail):
    approve(root)
    api({"/folders": folders(PERSONAL), "/notes/not_note1": detail})
    with pytest.raises(GranolaSourceError) as error:
        show_note(root, "not_note1")
    assert error.value.code == "not_found"


@pytest.mark.parametrize("url", ["http://granola.ai/notes/x", "https://granola.ai.evil.example/x",
                                 "https://user:pw@granola.ai/x", None])
def test_show_rejects_unsafe_links(api, root, url):
    approve(root)
    api({"/folders": folders(PERSONAL), "/notes/not_note1": response(body={**DETAIL, "web_url": url})})
    with pytest.raises(GranolaSourceError) as error:
        show_note(root, "not_note1")
    assert error.value.code == "invalid_response"


def test_show_withholds_credential_shaped_summary(api, root):
    approve(root)
    secret = {**DETAIL, "summary": {"markdown": "token ghp_" + "a" * 36}}
    api({"/folders": folders(PERSONAL), "/notes/not_note1": response(body=secret)})
    assert show_note(root, "not_note1")["text"] == source.WITHHELD


# ---------------------------------------------------------------------------
# CLI: discovery, JSON on stdout, coded errors on stderr, exit codes
# ---------------------------------------------------------------------------

def test_help_lists_both_commands_without_reading_credentials(monkeypatch):
    refuse_client(monkeypatch)
    runner = CliRunner()
    group = runner.invoke(app, ["granola", "--help"])
    assert group.exit_code == 0 and "changes" in group.output and "show" in group.output
    for command in ("changes", "show"):
        result = runner.invoke(app, ["granola", command, "--help"])
        assert result.exit_code == 0
        assert "Example:" in result.output and "Next:" in result.output and "--json" in result.output


def test_cli_changes_json_success(api, root):
    approve(root)
    api({"/folders": folders(PERSONAL), "/notes": notes(STUB_A)})
    result = CliRunner().invoke(app, ["granola", "changes", "--since", "2026-11-01T00:00:00Z",
                                      "--json", "--root", str(root)])
    assert result.exit_code == 0
    assert json.loads(result.stdout) == [{"id": "not_a", "version": "2026-11-02T10:00:00Z",
                                          "time": "2026-11-02T10:00:00Z", "title": "Planning"}]


def test_cli_show_json_success(api, root):
    approve(root)
    api({"/folders": folders(PERSONAL), "/notes/not_note1": response(body=DETAIL)})
    result = CliRunner().invoke(app, ["granola", "show", "not_note1", "--json", "--root", str(root)])
    assert result.exit_code == 0
    assert json.loads(result.stdout)["link"] == "https://granola.ai/notes/not_note1"


def test_cli_error_is_json_on_stderr_with_exit_1(monkeypatch, root):
    refuse_client(monkeypatch)
    result = CliRunner().invoke(app, ["granola", "changes", "--since", "2026-11-01T00:00:00Z",
                                      "--json", "--root", str(root)])
    assert result.exit_code == 1
    assert result.stdout == ""
    assert json.loads(result.stderr)["error"]["code"] == "approval_required"


def test_cli_missing_since_is_usage_error(monkeypatch):
    refuse_client(monkeypatch)
    result = CliRunner().invoke(app, ["granola", "changes", "--json"])
    assert result.exit_code == 2

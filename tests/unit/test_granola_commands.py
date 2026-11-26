"""CLI contract tests for `co granola` (including DD-081 `changes` and `show --json`)."""

import json
import httpx
import pytest
from typer.testing import CliRunner

from connectonion.cli.main import app

RUNNER = CliRunner()


def _install_mock_granola(monkeypatch, handler):
    from connectonion.useful_tools import granola

    monkeypatch.setenv("GRANOLA_API_KEY", "grn_cli_test")
    orig_init = granola.GranolaClient.__init__

    def patched_init(self, *, _base_url=granola.BASE_URL, _http=None):
        orig_init(
            self,
            _base_url=_base_url,
            _http=_http or httpx.Client(
                transport=httpx.MockTransport(handler),
                headers={"Authorization": "Bearer grn_cli_test"},
            ),
        )

    monkeypatch.setattr(granola.GranolaClient, "__init__", patched_init)


def _default_handler(req: httpx.Request) -> httpx.Response:
    if req.url.path == "/v1/folders":
        return httpx.Response(200, json={
            "folders": [
                {"id": "fld_1on1", "name": "1:1s", "space_id": None, "parent_folder_id": None},
                {"id": "fld_team_shared", "name": "Shared Space", "space_id": "spc_1", "parent_folder_id": None},
            ],
            "hasMore": False,
        })
    if req.url.path == "/v1/notes":
        if req.url.params.get("page_size") == "1" and "folder_id" not in req.url.params:
            return httpx.Response(200, json={
                "notes": [{"id": "not_b", "title": "Architecture Sync"}],
                "hasMore": False,
            })
        assert req.url.params.get("folder_id") == "fld_1on1"
        return httpx.Response(200, json={
            "notes": [
                {
                    "id": "not_b",
                    "title": "Architecture Sync",
                    "created_at": "2026-11-24T08:00:00Z",
                    "updated_at": "2026-11-24T09:30:00Z",
                    "web_url": "https://notes.granola.ai/d/not_b",
                },
                {
                    "id": "not_deleted",
                    "title": "Deleted Draft",
                    "created_at": "2026-11-23T08:00:00Z",
                    "updated_at": "2026-11-24T09:00:00Z",
                    "deleted_at": "2026-11-24T09:10:00Z",
                },
                {
                    "id": "not_a",
                    "title": "Kickoff sk-proj-1234567890abcdefghijklmnop",
                    "created_at": "2026-11-22T08:00:00Z",
                    "updated_at": "2026-11-23T11:00:00Z",
                    "web_url": "https://notes.granola.ai/d/not_a",
                },
            ],
            "hasMore": False,
        })
    if req.url.path == "/v1/notes/not_b":
        return httpx.Response(200, json={
            "id": "not_b",
            "title": "Architecture Sync",
            "created_at": "2026-11-24T08:00:00Z",
            "updated_at": "2026-11-24T09:30:00Z",
            "web_url": "https://notes.granola.ai/d/not_b",
            "folder_id": "fld_1on1",
            "space_id": None,
            "calendar_event": {"scheduled_start": "2026-11-24T08:00:00Z"},
            "summary": {"markdown": "## Summary\nAgreed on CLI JSON contract."},
        })
    return httpx.Response(404, json={"error": "not found"})


def test_bare_co_granola_prints_help():
    res = RUNNER.invoke(app, ["granola"])
    assert res.exit_code == 0
    assert "folders" in res.stdout and "changes" in res.stdout and "show" in res.stdout


def test_check_and_folders_list_only_personal_folders(monkeypatch):
    _install_mock_granola(monkeypatch, _default_handler)

    chk = RUNNER.invoke(app, ["granola", "check"])
    assert chk.exit_code == 0, chk.stderr
    assert "Connected" in chk.stdout
    assert "1 personal folder" in chk.stdout

    flds = RUNNER.invoke(app, ["granola", "folders", "--json"])
    assert flds.exit_code == 0, flds.stderr
    payload = json.loads(flds.stdout)
    assert [f["id"] for f in payload["folders"]] == ["fld_1on1"]
    assert payload["shared_skipped"] == 1
    assert "Next:" in flds.stderr


def test_changes_works_standalone_on_fresh_install_without_rem_state(monkeypatch, tmp_path):
    """Regression for #3223/#3249: co granola changes needs only --folder and GRANOLA_API_KEY, zero subscriptions.json."""
    monkeypatch.chdir(tmp_path)
    _install_mock_granola(monkeypatch, _default_handler)

    res = RUNNER.invoke(
        app,
        ["granola", "changes", "--since", "2026-11-23T00:00:00Z", "--folder", "fld_1on1", "--json"],
    )
    assert res.exit_code == 0, res.stderr
    data = json.loads(res.stdout)
    assert set(data.keys()) == {"since", "until", "items"}
    # Oldest updated_at first; deleted note omitted; credential-shaped token redacted
    assert [item["id"] for item in data["items"]] == ["not_a", "not_b"]
    assert data["items"][0]["title"] == "[withheld: possible credential]"
    assert data["items"][1]["link"] == "https://notes.granola.ai/d/not_b"
    assert "Next:" in res.stderr


def test_changes_rejects_invalid_since_with_exit_2(monkeypatch):
    _install_mock_granola(monkeypatch, _default_handler)

    no_tz = RUNNER.invoke(
        app,
        ["granola", "changes", "--since", "2026-11-23T00:00:00", "--folder", "fld_1on1", "--json"],
    )
    assert no_tz.exit_code == 2
    assert no_tz.stdout == ""


def test_show_accepts_citation_prefix_and_returns_live_summary(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    _install_mock_granola(monkeypatch, _default_handler)

    res = RUNNER.invoke(
        app,
        ["granola", "show", "granola:not_b", "--folder", "fld_1on1", "--json"],
    )
    assert res.exit_code == 0, res.stderr
    item = json.loads(res.stdout)
    assert item["id"] == "not_b"
    assert item["title"] == "Architecture Sync"
    assert item["author"] is None
    assert item["time"] == "2026-11-24T09:30:00Z"
    assert item["meeting_time"] == "2026-11-24T08:00:00Z"
    assert "Agreed on CLI JSON contract." in item["text"]
    assert item["link"] == "https://notes.granola.ai/d/not_b"


def test_notes_command_lists_folder_notes(monkeypatch):
    _install_mock_granola(monkeypatch, _default_handler)

    res = RUNNER.invoke(app, ["granola", "notes", "fld_1on1", "--json"])
    assert res.exit_code == 0, res.stderr
    data = json.loads(res.stdout)
    assert data["folder_id"] == "fld_1on1"
    assert [n["id"] for n in data["notes"]] == ["not_b", "not_a"]


def test_shared_folder_and_failed_reads_exit_1_with_empty_json_stdout(monkeypatch):
    _install_mock_granola(monkeypatch, _default_handler)

    res = RUNNER.invoke(
        app,
        ["granola", "changes", "--since", "2026-11-20T00:00:00Z", "--folder", "fld_team_shared", "--json"],
    )
    assert res.exit_code == 1
    assert res.stdout == ""
    assert "shared Granola space" in res.stderr
    assert "Next:" in res.stderr


def test_rem_instructions_loads_rem_source_granola():
    from connectonion.rem.runner import instructions

    composed = instructions("extract", "granola")
    assert "Granola as a source" in composed
    assert "granola:<id>" in composed


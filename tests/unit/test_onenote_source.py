import json
from pathlib import Path
import httpx
import pytest
import yaml
from connectonion.provider_credentials import ProviderCredentialError
from connectonion.useful_tools.onenote_source import OneNoteSource
from onenote_source_fixtures import graph, BASE, DATA, HTML

from connectonion.useful_tools.onenote_source import sync_onenote


@pytest.mark.parametrize("mode", ["daily", "export"])
def test_import_uses_shared_contract_and_common_consumer(graph, tmp_path, mode):
    from connectonion.useful_tools.adapter import (
        RECORD_FIELDS, MEDIA_FIELDS, consume_jsonl_records, consume_records,
        make_record, validate_record, write_daily_jsonl, AdapterResult,
    )
    source_dir = tmp_path / "onenote"
    result = sync_onenote(OneNoteSource(), "nb-fixture", "section-fixture", ["page-good", "page-empty"],
                          source_dir, mode=mode, export_id="contract" if mode == "export" else None)
    rows = [json.loads(line) for line in Path(result["jsonl"]).read_text(encoding="utf-8").splitlines()]
    for row in rows:
        assert not validate_record(row)
        assert set(row) <= set(RECORD_FIELDS) | {"media"}
        assert row["id"].endswith(":" + row["external_id"])
        assert row["extensions"]["scope"]["section"]
        assert row["extensions"]["ingestion"]["mode"] == mode
        for media in row.get("media", []):
            assert set(media) == set(MEDIA_FIELDS)
    assert not rows[1].get("media")  # Optional empty media does not discard empty content.
    jira_dir = tmp_path / "jira"
    jira = AdapterResult(records=[make_record("fixture", "fixture.invalid", "page-good", "issue", title="Shared consumer")])
    write_daily_jsonl(jira.records, jira_dir)
    daily = consume_jsonl_records(jira_dir, source_dir)
    assert not daily.errors
    if mode == "daily":
        assert {row["source"] for row in consume_records(daily)} == {"fixture", "onenote"}
        assert len({row["id"] for row in daily.records}) == 3
    else:
        assert len(daily.records) == 1  # Exports are explicitly consumed, never scanned as daily.
        assert consume_records(AdapterResult(records=rows)) == rows


def test_shared_mapping_rejection_is_reported_without_losing_valid_page(graph, monkeypatch):
    from connectonion.useful_tools import onenote_source
    original = onenote_source._page_text
    monkeypatch.setattr(onenote_source, "_page_text", lambda content: [] if content == HTML else original(content))
    result = OneNoteSource().collect("nb-fixture", "section-fixture", ["page-good", "page-empty"])
    assert [record["external_id"] for record in result.records] == ["page-empty"]
    assert "onenote:page-good" in result.errors
    assert "text" in result.errors["onenote:page-good"]


def test_legacy_daily_directory_is_preserved_and_cli_reports_upgrade_requirement(graph, tmp_path):
    from typer.testing import CliRunner
    from connectonion.cli.main import app
    result = sync_onenote(OneNoteSource(), "nb-fixture", "section-fixture", ["page-good"], tmp_path)
    target = Path(result["jsonl"])
    legacy = {"source": "onenote", "account": "https://graph.microsoft.com/v1.0/users/fixture-user",
              "id": "page-good", "date": "2026-10-02T01:00:00Z", "text": "Legacy content"}
    target.write_text(json.dumps(legacy) + "\n", encoding="utf-8")
    original = target.read_bytes()
    config = (tmp_path / "source.yaml").read_bytes()
    output = CliRunner().invoke(app, ["onenote", "source", "sync", "nb-fixture", "section-fixture",
                                     "page-good", "--output", str(tmp_path), "--json"])
    assert output.exit_code == 1
    error = json.loads(output.stdout)["error"]
    assert "incompatible" in error and "new --output" in error
    assert target.read_bytes() == original
    assert (tmp_path / "source.yaml").read_bytes() == config

def test_selected_import_preserves_content_media_and_partial_errors(graph):
    routes, calls = graph
    routes["/me/onenote/pages/page-malformed"] = ["invalid"]
    result = OneNoteSource().collect("nb-fixture", "section-fixture",
                                   ["page-good", "page-empty", "page-gone", "page-malformed", "page-outside"])
    assert {r["external_id"] for r in result.records} == {"page-good", "page-empty"}
    assert set(result.errors) == {"page-gone", "page-malformed", "page-outside"}
    record = result.records[0]
    assert record["source"] == "onenote" and record["url"].startswith("https://example.invalid/")
    assert record["at"] == "2026-10-01T01:00:00Z" and record["updated"] == "2026-10-02T01:00:00Z"
    assert "Keep & cite" in record["text"] and "do_not_include" not in record["text"]
    assert record["media"][0]["mime"] == "image/png" and record["media"][0]["size"] == 42
    assert record["media"][1]["name"] == "fixture.txt"
    assert all(m["status"] == "metadata_only" and m["sha256"] is None for m in record["media"])
    assert all(m["fetch_reference"] for m in record["extensions"]["media_fetch_references"])
    assert result.records[1]["text"] == "" and result.records[1]["url"].endswith("/pages/page-empty")
    assert not any("resources/" in url or "page-outside/content" in url for _, url, _ in calls)


@pytest.mark.parametrize("mode", ["daily", "export"])
def test_sync_explicit_layout_and_source_config(graph, tmp_path, mode):
    result = sync_onenote(OneNoteSource(), "nb-fixture", "section-fixture", ["page-good"],
                          tmp_path, mode=mode, export_id="fixture-export" if mode == "export" else None)
    doc = yaml.safe_load((tmp_path / "source.yaml").read_text(encoding="utf-8"))
    assert doc["driver"] == "onenote" and doc["scope"]["pages"] == ["page-good"]
    assert doc["media_policy"] == "metadata_only" and doc["retention"] == "90d"
    assert doc["validated_with"]["connectonion_version"] and doc["validated_with"]["path"]
    target = Path(result["jsonl"])
    record = json.loads(target.read_text(encoding="utf-8").strip())
    assert record["extensions"]["ingestion"] == {"mode": mode, "path": target.relative_to(tmp_path).as_posix()}
    if mode == "export":
        manifest = json.loads((target.parent / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["records"] == 1 and manifest["scope"] == doc["scope"]
        with pytest.raises(ValueError, match="exists"):
            sync_onenote(OneNoteSource(), "nb-fixture", "section-fixture", ["page-good"],
                         tmp_path, mode=mode, export_id="fixture-export")
    assert "fixture-secret-token" not in (tmp_path / "source.yaml").read_text(encoding="utf-8")


@pytest.mark.parametrize("options", [{"mode": "unknown"}, {"mode": "export", "export_id": "../escape"},
                                    {"mode": "export"}, {"mode": "daily", "export_id": "unexpected"}])
def test_invalid_storage_rejected_before_network_or_writes(graph, tmp_path, options):
    _, calls = graph
    with pytest.raises(ValueError):
        sync_onenote(OneNoteSource(), "nb-fixture", "section-fixture", ["page-good"], tmp_path, **options)
    assert not calls and not list(tmp_path.iterdir())


def test_repeat_daily_import_reports_dedup_instead_of_claiming_new_writes(graph, tmp_path):
    first = sync_onenote(OneNoteSource(), "nb-fixture", "section-fixture", ["page-good"], tmp_path)
    _, calls = graph
    calls.clear()
    second = sync_onenote(OneNoteSource(), "nb-fixture", "section-fixture", ["page-good"], tmp_path)
    assert first["written"] == 1 and second["written"] == 0 and second["skipped"] == 1
    assert not any(url.endswith("/content") for _, url, _ in calls)


def test_all_failed_import_leaves_no_files(graph, tmp_path):
    result = sync_onenote(OneNoteSource(), "nb-fixture", "section-fixture", ["page-gone"], tmp_path)
    assert result["records"] == 0 and result["errors"]
    assert not (tmp_path / "daily").exists() and not (tmp_path / "source.yaml").exists()


def test_account_or_scope_cannot_overwrite_an_existing_source_config(graph, tmp_path):
    sync_onenote(OneNoteSource(), "nb-fixture", "section-fixture", ["page-good"], tmp_path)
    original = (tmp_path / "source.yaml").read_bytes()
    with pytest.raises(ValueError, match="another account or scope"):
        routes, _ = graph
        routes["/me"] = {"id": "other-account"}
        sync_onenote(OneNoteSource(), "nb-fixture", "section-fixture", ["page-empty"], tmp_path)
    assert (tmp_path / "source.yaml").read_bytes() == original


@pytest.mark.parametrize("status", [401, 403, 404, 429, 503])
def test_page_errors_are_safe_and_unauthorized_aborts(graph, monkeypatch, status):
    monkeypatch.setattr("connectonion.useful_tools.onenote_source.time.sleep", lambda seconds: None)
    from connectonion.useful_tools.outlook import Outlook
    monkeypatch.setattr(Outlook, "_refresh_via_backend", lambda self, rt: "fresh")
    routes, _ = graph
    routes["/me/onenote/pages/page-good/content"] = (status, "fixture-secret-token")
    if status == 401:
        with pytest.raises(ProviderCredentialError, match="co auth microsoft"):
            OneNoteSource().collect("nb-fixture", "section-fixture", ["page-good"])
    else:
        result = OneNoteSource().collect("nb-fixture", "section-fixture", ["page-good", "page-empty"])
        assert len(result.records) == 1 and "page-good" in result.errors
        assert "fixture-secret-token" not in json.dumps(result.errors)
        if status == 404:
            assert "co onenote source pages --help" in result.errors["page-good"]
            assert "co auth microsoft" not in result.errors["page-good"]


@pytest.mark.parametrize("retry_after, expected_wait", [
    ("3", 3), ("Thu, 01 Jan 1970 00:16:45 GMT", 5), ("invalid", 1),
])
def test_content_429_then_success_honors_retry_after(graph, monkeypatch, retry_after, expected_wait):
    waits = []
    monkeypatch.setattr("connectonion.useful_tools.onenote_source.time.sleep", waits.append)
    monkeypatch.setattr("connectonion.useful_tools.onenote_source.time.time", lambda: 1000)
    routes, calls = graph
    responses = iter([httpx.Response(429, headers={"Retry-After": retry_after}), HTML])
    routes["/me/onenote/pages/page-good/content"] = lambda: next(responses)
    result = OneNoteSource().collect("nb-fixture", "section-fixture", ["page-good"])
    assert len(result.records) == 1 and not result.errors
    assert waits == [expected_wait]
    assert len([url for _, url, _ in calls if url.endswith("/page-good/content")]) == 2


@pytest.mark.parametrize("status", [429, 503, 504])
def test_content_retry_exhaustion_keeps_valid_pages_and_reports_recovery(graph, monkeypatch, status):
    waits = []
    monkeypatch.setattr("connectonion.useful_tools.onenote_source.time.sleep", waits.append)
    routes, calls = graph
    routes["/me/onenote/pages/page-good/content"] = (status, "private provider body")
    result = OneNoteSource().collect("nb-fixture", "section-fixture", ["page-good", "page-empty"])
    assert len(result.records) == 1 and "page-good" in result.errors
    assert waits == [1, 2]
    assert len([url for _, url, _ in calls if url.endswith("/page-good/content")]) == 3
    error = result.errors["page-good"]
    assert f"HTTP {status}" in error and "retries exhausted" in error
    assert "Wait" in error and "co onenote source sync" in error
    assert "pages --help" not in error and "private provider body" not in error


@pytest.mark.parametrize("retry_after", ["86400", "1e300"])
def test_content_long_retry_after_reports_failure_without_sleeping_or_retrying_early(graph, monkeypatch, retry_after):
    waits = []
    monkeypatch.setattr("connectonion.useful_tools.onenote_source.time.sleep", waits.append)
    routes, calls = graph
    routes["/me/onenote/pages/page-good/content"] = httpx.Response(429, headers={"Retry-After": retry_after})
    result = OneNoteSource().collect("nb-fixture", "section-fixture", ["page-good", "page-empty"])
    assert len(result.records) == 1 and not waits
    assert len([url for _, url, _ in calls if url.endswith("/page-good/content")]) == 1
    assert "automatic wait limit" in result.errors["page-good"]
    assert "Wait" in result.errors["page-good"] and "co onenote source sync" in result.errors["page-good"]


def test_content_refresh_can_recover_without_discarding_page(graph, monkeypatch):
    from connectonion.useful_tools.outlook import Outlook
    refreshed = []
    monkeypatch.setenv("MICROSOFT_REFRESH_TOKEN", "fixture-refresh")
    monkeypatch.setattr(Outlook, "_refresh_via_backend", lambda self, rt: refreshed.append(rt) or "fresh")
    routes, _ = graph
    responses = iter([(401, "private"), HTML])
    routes["/me/onenote/pages/page-good/content"] = lambda: next(responses)
    result = OneNoteSource().collect("nb-fixture", "section-fixture", ["page-good"])
    assert len(result.records) == 1 and not result.errors and refreshed == ["fixture-refresh"]


def test_content_auth_failure_without_refresh_requires_login(graph, monkeypatch):
    """A missing refresh credential is authentication failure, not malformed content."""
    from connectonion.useful_tools.outlook import Outlook
    monkeypatch.delenv("MICROSOFT_REFRESH_TOKEN", raising=False)
    monkeypatch.setattr(Outlook, "_refresh_via_backend",
                        lambda *args: pytest.fail("Must not call the refresh broker without a refresh token"))
    routes, _ = graph
    routes["/me/onenote/pages/page-good/content"] = (401, "fixture-secret-token")
    with pytest.raises(ProviderCredentialError) as error:
        OneNoteSource().collect("nb-fixture", "section-fixture", ["page-good"])
    assert error.value.code == "reauth_required"
    assert error.value.next_command == "co auth microsoft"
    assert "fixture-secret-token" not in str(error.value)


def test_cli_help_and_json_partial_import(graph, tmp_path):
    from typer.testing import CliRunner
    from connectonion.cli.main import app
    runner = CliRunner()
    for command in ([], ["sync"], ["pages"], ["verify"]):
        result = runner.invoke(app, ["onenote", "source", *command, "--help"])
        assert result.exit_code == 0, result.output
    result = runner.invoke(app, ["onenote", "source", "sync", "nb-fixture", "section-fixture",
                                 "page-good", "page-gone", "--output", str(tmp_path), "--json"])
    assert result.exit_code == 2, result.output
    report = json.loads(result.stdout)
    assert report["written"] == 1 and "page-gone" in report["errors"]
    assert Path(report["jsonl"]).is_file()
    assert "fixture-secret-token" not in result.output
    assert not result.stderr


@pytest.mark.parametrize("invalid", ["[]", "null", "42", '"scalar"', "{broken"])
def test_corrupted_daily_storage_returns_json_error_and_never_appends(graph, tmp_path, invalid):
    from typer.testing import CliRunner
    from connectonion.cli.main import app
    initial = sync_onenote(OneNoteSource(), "nb-fixture", "section-fixture", ["page-good"], tmp_path)
    target = Path(initial["jsonl"])
    target.write_text(invalid + "\n", encoding="utf-8")
    result = CliRunner().invoke(app, ["onenote", "source", "sync", "nb-fixture", "section-fixture",
                                    "page-good", "--output", str(tmp_path), "--json"])
    assert result.exit_code == 1, result.output
    assert "corrupted at line 1" in json.loads(result.stdout)["error"]
    assert target.read_text(encoding="utf-8") == invalid + "\n"


def test_changed_and_new_pages_append_versions_without_fetching_other_bodies(graph, tmp_path):
    routes, _ = graph
    initial = sync_onenote(OneNoteSource(), "nb-fixture", "section-fixture", ["page-good"], tmp_path)
    metadata = "/me/onenote/pages/page-good"
    routes[metadata] = {**routes[metadata], "lastModifiedDateTime": "2026-10-03T01:00:00Z"}
    routes["/me/onenote/pages/page-good/content"] = "<html><body>Changed fixture</body></html>"
    selection = ["page-good", "page-empty"]
    changed = sync_onenote(OneNoteSource(), "nb-fixture", "section-fixture", selection, tmp_path)
    repeated = sync_onenote(OneNoteSource(), "nb-fixture", "section-fixture", selection, tmp_path)
    assert changed["written"] == 2 and repeated["written"] == 0 and repeated["skipped"] == 2
    rows = [json.loads(line) for line in Path(initial["jsonl"]).read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 3 and rows[0]["id"] == rows[1]["id"]
    assert rows[1]["text"] == "Changed fixture"


@pytest.mark.parametrize("failure", ["daily", "source.yaml"])
def test_incremental_retry_matches_uninterrupted_even_on_another_day(graph, tmp_path, monkeypatch, failure):
    from connectonion.rem import files
    from connectonion.useful_tools import onenote_storage

    reference, retry = tmp_path / "reference", tmp_path / "retry"
    jira = tmp_path / "jira" / ".state" / "checkpoint.json"
    jira.parent.mkdir(parents=True)
    jira.write_text('{"sentinel": true}', encoding="utf-8")

    def run(path):
        return sync_onenote(OneNoteSource(), "nb-fixture", "section-fixture", ["page-good"], path)

    expected = Path(run(reference)["jsonl"])
    write = files.atomic_write

    def fail(path, text):
        if (failure == "daily" and path.suffix == ".jsonl") or path.name == failure:
            raise OSError("fixture interruption")
        write(path, text)

    with monkeypatch.context() as patch:
        patch.setattr(files, "atomic_write", fail)
        patch.setattr(onenote_storage, "atomic_write", fail)
        with pytest.raises(OSError, match="fixture interruption"):
            run(retry)

    original_target = onenote_storage.prepare_import

    def next_day(path, mode, export_id):
        return path / "daily/2099/01/01.jsonl" if path == retry else original_target(path, mode, export_id)

    monkeypatch.setattr(onenote_storage, "prepare_import", next_day)
    assert run(retry)["written"] == (1 if failure == "daily" else 0)
    assert (retry / "source.yaml").is_file()
    files_written = list(retry.glob("daily/*/*/*.jsonl"))
    assert len(files_written) == 1
    expected_row = json.loads(expected.read_text(encoding="utf-8"))
    actual_row = json.loads(files_written[0].read_text(encoding="utf-8"))
    for row in (expected_row, actual_row):
        row.pop("fetched")
        row["extensions"].pop("ingestion")
    assert expected_row == actual_row
    assert jira.read_text(encoding="utf-8") == '{"sentinel": true}'

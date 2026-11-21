"""Normal REM consumption of selected, local Jira imports; no remote service."""
import copy
import json
from datetime import datetime, timezone

import pytest
import yaml

from connectonion.rem.config import prepare
from connectonion.rem.files import Notebook, RemError, read_json, state_path
from connectonion.rem import service
from connectonion.useful_tools.adapter import append_daily_jsonl, jira_issues_to_records, resolve_reference


@pytest.fixture
def imported(tmp_path, monkeypatch):
    monkeypatch.setattr(service, "mail_available", lambda _: False)
    root = tmp_path / "rem"
    prepare(root)
    for name in ("codex", "claude-code", "gmail", "outlook", "whatsapp"):
        service.toggle_source(root, name, False)
    now = datetime.now(timezone.utc).isoformat()
    records = jira_issues_to_records([{"key": "DEMO-1", "fields": {
        "summary": "Implement sign in", "description": "Login work remains pending.",
        "created": now, "updated": now, "status": {"name": "In Progress"},
        "reporter": {"displayName": "Sam Lee", "accountId": "sam-1"},
    }}], "https://jira.example.invalid").records
    directory = root / "docs/jira"
    append_daily_jsonl(records, directory, keep_versions=True)
    (directory / "source.yaml").write_text(yaml.safe_dump({"driver": "jira",
        "account": records[0]["account"], "scope": {"projects": ["DEMO"], "issues": ["DEMO-1"]}}))
    return root, directory, records


def chosen(root):
    service.toggle_source(root, "jira", True)
    return service.subscriptions(root)["jira"]


def approve_and_map(root):
    from connectonion.rem.map import build_map
    service.approve_sources(root)
    return build_map(root, service.subscriptions(root), {}, skill_directories=[])


def test_jira_is_opt_in_and_dry_run_does_not_open_records(imported, monkeypatch):
    root, directory, _ = imported
    assert not service.subscriptions(root)["jira"]["enabled"]
    chosen(root)
    for path in directory.rglob("*.jsonl"):
        path.write_text("not JSON")
    result = service.run_sync(root, source="jira", dry_run=True)
    assert result["sources"]["jira"]["body_reads"] is False
    assert not state_path(root, "consent.json").exists()


def test_unapproved_collection_never_opens_body(imported):
    from connectonion.rem.jira_imports import collect_jira
    root, directory, _ = imported
    sub = chosen(root)
    for path in directory.rglob("*.jsonl"):
        path.write_text("not JSON")
    assert collect_jira(root, sub, {}, 10, 80000).items == []
    with pytest.raises(RemError, match="authorized"):
        service.run_sync(root, source="jira")


def test_first_repeat_changed_and_old_reference(imported):
    root, directory, records = imported
    chosen(root)
    approve_and_map(root)
    calls = []
    def runner(notebook, items, config, kind=""):
        calls.append((kind, items))
        return {}
    assert service.run_sync(root, source="jira", runner=runner)["items"] == 1
    original = calls[0][1][0]
    assert calls[0][0] == "jira"
    assert json.loads(original["text"])["extensions"]["status"] == "In Progress"
    assert service.run_sync(root, source="jira", runner=runner)["items"] == 0
    changed = copy.deepcopy(records[0])
    changed["extensions"]["status"] = "Done"
    append_daily_jsonl([changed], directory, keep_versions=True)
    assert service.run_sync(root, source="jira", runner=runner)["items"] == 1
    assert resolve_reference(original["source"].removeprefix("adapter:"), root)["extensions"]["status"] == "In Progress"


@pytest.mark.parametrize("damage", ["json", "account", "scope", "symlink", "metadata"])
def test_invalid_or_replaced_source_preserves_progress(imported, damage, tmp_path):
    root, directory, records = imported
    chosen(root)
    service.approve_sources(root)
    path = next(directory.rglob("*.jsonl"))
    if damage == "json":
        path.write_text("broken")
    elif damage == "symlink":
        outside = tmp_path / "outside.jsonl"
        outside.write_bytes(path.read_bytes())
        path.unlink()
        path.symlink_to(outside)
    elif damage == "metadata":
        source = directory / "source.yaml"
        source.write_text(source.read_text().replace("DEMO-1", "DEMO-2"))
    else:
        bad = copy.deepcopy(records[0])
        bad["account" if damage == "account" else "external_id"] = "foreign" if damage == "account" else "OTHER-1"
        path.write_text(json.dumps(bad) + "\n")
    result = service.run_sync(root, source="jira", runner=lambda *a, **kw: pytest.fail("model ran"))
    assert result["outcome"] == "failed"
    assert "jira" not in read_json(state_path(root, "progress.json"), {})


def test_runner_failure_does_not_consume_evidence(imported):
    root, _, _ = imported
    chosen(root)
    approve_and_map(root)
    def failed(*a, **kw):
        raise RemError("test model unavailable")
    assert service.run_sync(root, source="jira", runner=failed)["outcome"] == "failed"
    assert "jira" not in read_json(state_path(root, "progress.json"), {})


def test_budget_never_truncates_or_skips_oversize_evidence(imported):
    from connectonion.rem.jira_imports import collect_jira
    root, _, _ = imported
    chosen(root)
    service.approve_sources(root)
    sub = service.subscriptions(root)["jira"]
    with pytest.raises(RemError, match="budget"):
        collect_jira(root, sub, {}, 10, 10)


def test_normal_map_investigate_and_exact_identity_routing(imported):
    from connectonion.rem.map import build_map
    from connectonion.rem.investigate import gather
    from connectonion.rem.leads import page_leads
    root, _, _ = imported
    chosen(root)
    # An unapproved map must not read Jira records.
    assert not build_map(root, service.subscriptions(root), {}, skill_directories=[]) ["projects"]
    service.approve_sources(root)
    report = build_map(root, service.subscriptions(root), {}, skill_directories=[])
    assert len(report["projects"]) == len(report["people"]) == 1
    person = report["people"][0]["record"]
    project = report["projects"][0]["record"]
    notebook = Notebook(root)
    notebook.stub_person("people/other-sam.md", "Sam Lee")
    items, coverage = gather("Sam Lee", ["Sam Lee"], days=60, clients={},
        subscriptions=service.subscriptions(root), archive_root=root, record=person)
    assert len(items) == 1
    assert set(page_leads(notebook, items)) == {person, project}
    assert "people/other-sam.md" not in page_leads(notebook, items)
    assert any("jira" in line and "1" in line for line in coverage)
    authored = notebook.read(project) + "\nManual note to preserve.\n"
    notebook.write(project, authored)
    again = build_map(root, service.subscriptions(root), {}, skill_directories=[])
    assert again["projects"][0]["record"] == project
    assert notebook.read(project) == authored


def test_new_identity_is_not_consumed_before_mapping(imported):
    root, directory, records = imported
    chosen(root)
    approve_and_map(root)
    changed = copy.deepcopy(records[0])
    changed["extensions"].update(assignee="New Person", people={"reporter": "sam-1", "assignee": "new-person"})
    append_daily_jsonl([changed], directory, keep_versions=True)
    result = service.run_sync(root, source="jira", runner=lambda *a, **kw: pytest.fail("model ran"))
    assert result["outcome"] == "failed"
    assert "jira" not in read_json(state_path(root, "progress.json"), {})
    approve_and_map(root)
    assert service.run_sync(root, source="jira", runner=lambda *a, **kw: {})["items"] == 1


def test_cooling_preserves_pending_version_and_exact_citation_counts_as_read(imported):
    from connectonion.rem.leads import remember_no_change, nothing_new
    from connectonion.rem.jira_imports import collect_jira
    root, _, _ = imported
    chosen(root)
    report = approve_and_map(root)
    for row in report["people"] + report["projects"]:
        remember_no_change(root, row["record"], True)
    with pytest.raises(RemError, match="cooling"):
        service.run_sync(root, source="jira")
    assert "jira" not in read_json(state_path(root, "progress.json"), {})
    material = collect_jira(root, service.subscriptions(root)["jira"], {}, 1, 80000).items
    notebook = Notebook(root)
    page = report["projects"][0]["record"]
    assert not nothing_new(notebook, page, material)
    notebook.write(page, notebook.read(page).replace("- (none yet)", "- [1] " + material[0]["source"]))
    assert nothing_new(notebook, page, material)


@pytest.mark.parametrize("description", ["", " — 2026-11-06", " – issue snapshot"])
def test_imported_citations_and_coverage_are_not_hollow(imported, description):
    from connectonion.rem.queue import _stamped_from_nothing, _material_read
    from connectonion.rem.jira_imports import collect_jira
    root, _, _ = imported
    chosen(root)
    report = approve_and_map(root)
    material = collect_jira(root, service.subscriptions(root)["jira"], {}, 1, 80000).items
    notebook = Notebook(root)
    page = notebook.read(report["people"][0]["record"])
    import re
    page = re.sub(r"Investigation:.*", "Investigation: investigated 2026-11-06", page)
    page = page.replace("- (none yet)", "- [1] " + material[0]["source"] + description)
    assert not _stamped_from_nothing(page)
    assert _material_read(["jira: selected local snapshots for this identity in window, 1 read; no remote polling"]) == 1


def test_new_identical_snapshot_updates_rank_and_preserves_first_citation(imported):
    from connectonion.rem.jira_imports import snapshot_rows
    from connectonion.useful_tools.adapter import write_export
    root, directory, records = imported
    a = copy.deepcopy(records[0])
    a["fetched"] = "2026-11-01T00:00:00Z"
    path = next(directory.rglob("*.jsonl"))
    path.write_text(json.dumps(a) + "\n")
    a["fetched"] = "2026-11-03T00:00:00Z"
    path.write_text(path.read_text() + json.dumps(a) + "\n")
    b = copy.deepcopy(a)
    b.update(title="Older conflicting observation", fetched="2026-11-02T00:00:00Z")
    write_export([b], directory, "older", {"projects": ["DEMO"], "issues": ["DEMO-1"]})
    chosen(root)
    service.approve_sources(root)
    rows = snapshot_rows(root, service.subscriptions(root)["jira"])
    assert rows[0][0]["title"] == records[0]["title"]
    assert "/daily/" in rows[0][1]


def test_v2_project_scope_is_accepted_and_replacement_needs_reapproval(imported):
    root, directory, records = imported
    path = directory / "source.yaml"
    doc = {"schema_version": 2, "driver": "jira", "account": records[0]["account"],
           "authorised_identity": {"accountId": "owner-1"},
           "canonical_scope": {"type": "project", "project": "DEMO"}}
    path.write_text(yaml.safe_dump(doc))
    chosen(root)
    approve_and_map(root)
    doc["authorised_identity"]["accountId"] = "owner-2"
    path.write_text(yaml.safe_dump(doc))
    assert service.run_sync(root, source="jira", runner=lambda *a, **kw: {})["outcome"] == "failed"
    chosen(root)
    assert not service.subscriptions(root)["jira"]["consented"]


def test_daily_budget_must_cover_all_jira_target_pages(imported, monkeypatch):
    root, _, _ = imported
    chosen(root)
    approve_and_map(root)
    original_status = service.status
    monkeypatch.setattr(service, "status", lambda *a, **kw: {**original_status(*a, **kw), "runner_attempts_today": 49})
    with pytest.raises(RemError, match="source progress was not advanced"):
        service.run_sync(root, source="jira")
    assert "jira" not in read_json(state_path(root, "progress.json"), {})


def test_normal_page_dispatch_updates_existing_pages_after_new_snapshot(imported, monkeypatch):
    from connectonion.rem import runner
    root, directory, records = imported
    chosen(root)
    report = approve_and_map(root)
    expected = {row["record"] for row in report["people"] + report["projects"]}
    calls = []
    def model(notebook, items, config, kind="", **options):
        target = next(item["record"] for item in items if item.get("role") == "page")
        material = [item for item in items if item.get("source_kind") == "jira"]
        assert kind == "jira" and all(target in item["target_records"] for item in material)
        calls.append(target)
        # Substitute only the paid model boundary; exercise normal per-page routing.
        text = notebook.read(target)
        for item in material:
            text += "\n- [" + str(len(calls)) + "] " + item["source"] + "\n"
        notebook.write(target, text)
        return {"changed": [target]}
    monkeypatch.setattr(runner, "run_stage", model)
    assert set(service.run_sync(root, source="jira")["changed"]) == expected
    assert set(calls) == expected
    assert service.run_sync(root, source="jira")["items"] == 0
    changed = copy.deepcopy(records[0])
    changed["extensions"]["status"] = "Done"
    append_daily_jsonl([changed], directory, keep_versions=True)
    calls.clear()
    assert set(service.run_sync(root, source="jira")["changed"]) == expected
    assert set(calls) == expected


def test_normal_cli_init_maps_jira_without_installing_schedule(imported):
    from typer.testing import CliRunner
    from connectonion.cli.main import app
    root, _, _ = imported
    chosen(root)
    empty = root / "empty-skills"
    empty.mkdir()
    result = CliRunner().invoke(app, ["rem", "--root", str(root), "--json", "init", "--yes",
        "--no-investigate", "--no-start", "--no-mail-archive", "--no-translate", "--skills-dir", str(empty)])
    assert result.exit_code == 0, result.output
    assert len(read_json(state_path(root, "map.json"), {})["projects"]) == 1
    assert not state_path(root, "worker.json").exists()


@pytest.mark.parametrize("description", ["", " — 2026-11-06", " – selected issue snapshot"])
@pytest.mark.parametrize("adapter_prefix", [True, False])
def test_claim_audit_uses_canonical_fields_not_reader_excerpt(imported, description, adapter_prefix):
    from connectonion.rem.jira_imports import collect_jira
    from connectonion.rem.project_claim_review import packet
    root, _, _ = imported
    chosen(root)
    report = approve_and_map(root)
    originals = collect_jira(root, service.subscriptions(root)["jira"], {}, 1, 80000).items
    source = originals[0]["source"] if adapter_prefix else originals[0]["source"].removeprefix("adapter:")
    page = "# DEMO\n\nStatus: In Progress [1]\n\n## Sources\n- [1] " + source + description + "\n"
    for material in (originals, []):
        data, missing = packet(Notebook(root), page, report["projects"][0]["record"], material)
        assert not missing
        context = data["sources"][0]["context"]
        canonical = json.loads(context["excerpt"])
        assert canonical["extensions"]["status"] == "In Progress"
        assert not context.get("truncated")


def test_corrupt_per_source_progress_is_actionable(imported):
    from connectonion.rem.jira_imports import collect_jira
    root, _, _ = imported
    chosen(root)
    service.approve_sources(root)
    with pytest.raises(RemError, match="Invalid Jira source progress"):
        collect_jira(root, service.subscriptions(root)["jira"], [], 1, 80000)


def test_full_batch_does_not_serialize_next_oversized_issue(imported):
    from connectonion.rem.jira_imports import collect_jira
    from connectonion.useful_tools.adapter import make_record
    root, directory, records = imported
    large = make_record("jira", records[0]["account"], "DEMO-2", "issue", text="x" * 81000)
    append_daily_jsonl([large], directory, keep_versions=True)
    doc = yaml.safe_load((directory / "source.yaml").read_text())
    doc["scope"]["issues"].append("DEMO-2")
    (directory / "source.yaml").write_text(yaml.safe_dump(doc))
    chosen(root)
    service.approve_sources(root)
    sub = service.subscriptions(root)["jira"]
    first = collect_jira(root, sub, {}, 1, 150000)
    assert len(first.items) == 1
    with pytest.raises(RemError, match="too long"):
        collect_jira(root, sub, first.progress, 1, 150000)


def test_jira_map_with_owner_does_not_treat_imports_as_coding_sessions(imported):
    from connectonion.rem.map import build_map
    root, _, _ = imported
    chosen(root)
    service.approve_sources(root)
    report = build_map(root, service.subscriptions(root), {}, skill_directories=[],
                       mine=['owner@example.invalid'], name='Synthetic Owner')
    assert len(report['projects']) == 1 and report['projects'][0]['import_id']
    owner = Notebook(root).read(report['owner']['record'])
    assert 'Coding sessions in the same window' not in owner
    again = build_map(root, service.subscriptions(root), {}, skill_directories=[],
                      mine=['owner@example.invalid'], name='Synthetic Owner')
    assert again['projects'][0]['record'] == report['projects'][0]['record']

"""Normal, approved local note evidence reaches existing REM/Reader paths."""
import copy
import json
from datetime import datetime, timezone
import pytest
import yaml
from connectonion.rem import service
from connectonion.rem.config import prepare
from connectonion.rem.files import Notebook, RemError, read_json, state_path
from connectonion.useful_tools.adapter import append_daily_jsonl, make_record, resolve_reference

KIND = "onenote"

@pytest.mark.parametrize("configured", [False, True])
def test_disabled_onenote_summary_and_fingerprint_never_read_bodies(tmp_path, monkeypatch, configured):
    from connectonion.rem import remote_sources
    from connectonion.rem.files import write_json
    from connectonion.useful_tools.onenote_source import OneNoteSource
    root = tmp_path / "rem"
    prepare(root)
    monkeypatch.setattr(service, "mail_available", lambda _: False)
    monkeypatch.setattr(OneNoteSource, "__init__", lambda _: pytest.fail("credentials loaded"))
    monkeypatch.setattr(remote_sources, "require_saved", lambda *a: pytest.fail("credentials required"))
    declared = {"account": "synthetic-account", "scope": {"notebook": "book", "section": "section", "pages": ["page"]}}
    connection = {"selection": declared["scope"]}
    if configured:
        write_json(state_path(root, "subscriptions.json"), {KIND: {
            "id": KIND, "kind": KIND, "enabled": False, "consented": True,
            "import_identity": declared, "remote": connection}})
        directory = root / "docs/onenote"
        directory.mkdir(parents=True)
        (directory / "source.yaml").write_text("invalid: [")
    summary = service.consent_summary(root)["sources"][KIND]
    assert summary["state"] == "unsubscribed"
    assert len(service.summary_fingerprint(root)) == 64
    assert remote_sources.refresh(root, service.subscriptions(root)[KIND]) is None
    if configured:
        assert summary["import_identity"] == declared
        assert summary["remote"] == connection


def test_enabled_unapproved_onenote_keeps_selection_without_body_reads(imported, monkeypatch):
    from connectonion.rem import remote_sources
    root, directory, _ = imported
    choose(root)
    next(directory.rglob("*.jsonl")).write_text("not readable evidence")
    sub = service.subscriptions(root)[KIND]
    assert not sub["consented"]
    summary = service.consent_summary(root)["sources"][KIND]
    assert summary["import_identity"] == sub["import_identity"]
    assert remote_sources.refresh(root, sub) is None
    assert service.run_sync(root, source=KIND, dry_run=True)["sources"][KIND]["body_reads"] is False

@pytest.fixture
def imported(tmp_path, monkeypatch):
    monkeypatch.setattr(service, "mail_available", lambda _: False)
    root = tmp_path / "rem"
    prepare(root)
    for name in ("codex", "claude-code", "gmail", "outlook", "whatsapp"):
        service.toggle_source(root, name, False)
    now = datetime.now(timezone.utc).isoformat()
    scope = {"notebook": "book-1", "section": "section-1", "pages": ["page-1"]} if KIND == "onenote" else {"folder_id": "folder-1", "limit": 2}
    ext = {"scope": scope} if KIND == "onenote" else {"folder_id": "folder-1", "summary_kind": "generated_summary"}
    row = make_record(KIND, "test-account", "page-1", "page" if KIND == "onenote" else "meeting_note", title="Design discussion", text="The fictional Atlas project needs a review. The deadline is not agreed.", at=now, updated=now, fetched=now, url="https://example.invalid/notes/1", extensions=ext)
    directory = root / "docs" / KIND
    append_daily_jsonl([row], directory, keep_versions=True)
    (directory / "source.yaml").write_text(yaml.safe_dump({"driver": KIND, "account": "test-account", "scope": scope, "media_policy": "metadata_only", "complete": True}))
    return root, directory, row

def choose(root):
    service.toggle_source(root, KIND, True)

def mapped(root):
    from connectonion.rem.map import build_map
    choose(root)
    service.approve_sources(root)
    return build_map(root, service.subscriptions(root), {}, skill_directories=[])

def test_opt_in_and_no_unapproved_body_reads(imported):
    root, directory, _ = imported
    assert not service.subscriptions(root)[KIND]["enabled"]
    choose(root)
    next(directory.rglob("*.jsonl")).write_text("broken")
    assert service.run_sync(root, source=KIND, dry_run=True)["sources"][KIND]["body_reads"] is False
    with pytest.raises(RemError, match="authorized"):
        service.run_sync(root, source=KIND)


@pytest.mark.parametrize("row_pages", ["absent", [], ["other"], None, ["page-1", "outside"]])
def test_normal_adapter_parent_scope_preserves_selected_page_boundary(imported, row_pages):
    from connectonion.rem.onenote_imports import collect_onenote
    from connectonion.useful_tools.adapter import onenote_pages_to_records
    root, directory, _ = imported
    scope = {"notebook": "book-1", "section": "section-1"}
    row = onenote_pages_to_records([{"id": "page-1", "title": "ATLAS", "text": "ATLAS project discussion", "scope": scope}], "test-account").records[0]
    assert row["extensions"]["scope"] == scope
    if row_pages != "absent":
        row["extensions"]["scope"]["pages"] = row_pages
    next(directory.rglob("*.jsonl")).write_text(json.dumps(row) + "\n")
    mapped(root)
    if row_pages != "absent":
        with pytest.raises(RemError, match="out-of-scope"):
            collect_onenote(root, service.subscriptions(root)[KIND], {}, 1, 80000)
        return
    batch = collect_onenote(root, service.subscriptions(root)[KIND], {}, 1, 80000)
    assert len(batch.items) == 1
    assert json.loads(batch.items[0]["text"])["text"] == row["text"]

def test_map_gather_repeat_update_and_reader_reference(imported):
    from connectonion.rem.investigate import gather
    from connectonion.rem.source_links import source_record_context
    root, directory, row = imported
    report = mapped(root)
    assert report["projects"] == []
    Notebook(root).stub_project("projects/atlas.md", "Atlas")
    assert report["people"] == []
    items, coverage = gather("Atlas", ["Atlas"], days=60, clients={}, subscriptions=service.subscriptions(root), archive_root=root, record="projects/atlas.md")
    assert len(items) == 1
    assert "target_records" not in items[0]
    assert json.loads(items[0]["text"])["text"] == row["text"]
    calls=[]
    def runner(notebook, items, config, kind=""):
        calls.append((kind, items))
        return {}
    assert service.run_sync(root, source=KIND, runner=runner)["items"] == 1
    assert calls[0][0] == KIND
    old = items[0]["source"].removeprefix("adapter:")
    assert resolve_reference(old, root)["text"] == row["text"]
    assert source_record_context(root, old)["status"] == "resolved"
    assert service.run_sync(root, source=KIND, runner=runner)["items"] == 0
    changed = copy.deepcopy(row)
    changed["text"] = "Review completed; release remains pending."
    append_daily_jsonl([changed], directory, keep_versions=True)
    assert service.run_sync(root, source=KIND, runner=runner)["items"] == 1
    assert resolve_reference(old, root)["text"] == row["text"]
    assert source_record_context(root, old)["status"] == "resolved"

@pytest.mark.parametrize("damage", ["json", "account", "scope", "symlink", "declaration"])
def test_invalid_evidence_preserves_progress(imported, damage, tmp_path):
    root, directory, row = imported
    mapped(root)
    path=next(directory.rglob("*.jsonl"))
    if damage == "json": path.write_text("broken")
    elif damage == "symlink":
        outside=tmp_path / "outside.jsonl"
        outside.write_bytes(path.read_bytes())
        path.unlink()
        path.symlink_to(outside)
    elif damage == "declaration":
        doc=yaml.safe_load((directory / "source.yaml").read_text())
        doc["account"]="other"
        (directory / "source.yaml").write_text(yaml.safe_dump(doc))
    else:
        bad=copy.deepcopy(row)
        if damage == "account": bad["account"]="foreign"
        elif KIND == "onenote": bad["extensions"]["scope"]["pages"]=["other"]
        else: bad["extensions"]["folder_id"]="other"
        path.write_text(json.dumps(bad)+"\n")
    result=service.run_sync(root, source=KIND, runner=lambda *a, **kw: pytest.fail("model called"))
    assert result["outcome"] == "failed"
    assert KIND not in read_json(state_path(root, "progress.json"), {})

def test_runner_failure_does_not_consume(imported):
    root, _, _=imported
    mapped(root)
    def fail(*a, **kw): raise RemError("model unavailable")
    assert service.run_sync(root, source=KIND, runner=fail)["outcome"] == "failed"
    assert KIND not in read_json(state_path(root, "progress.json"), {})


def test_changed_note_is_found_via_old_citation_without_title_match(imported):
    from importlib import import_module
    from datetime import timedelta
    root, directory, row = imported
    mapped(root)
    mod=import_module("connectonion.rem."+KIND+"_imports")
    old=mod.collect_onenote(root, service.subscriptions(root)[KIND], {}, 1, 80000).items[0]["source"]
    Notebook(root).write("knowledge/review.md", "# A title never in the note\n\n## Sources\n- [1] "+old+" — snapshot\n")
    changed=copy.deepcopy(row)
    changed["text"]="New discussion with no project or title label."
    append_daily_jsonl([changed], directory, keep_versions=True)
    now=datetime.now(timezone.utc)
    items=mod.investigation_items(root, service.subscriptions(root)[KIND], "knowledge/review.md", now-timedelta(days=60), now+timedelta(days=1))
    assert len(items)==1
    assert json.loads(items[0]["text"])["text"]==changed["text"]
    assert items[0]["source"] != old

def test_complete_canonical_claim_packet(imported):
    from importlib import import_module
    from connectonion.rem.project_claim_review import packet
    root, _, row=imported
    mapped(root)
    mod=import_module("connectonion.rem."+KIND+"_imports")
    material=mod.collect_onenote(root, service.subscriptions(root)[KIND], {}, 1, 80000).items
    candidate="# Atlas\n\nReview remains open [1].\n\n## Sources\n- [1] "+material[0]["source"]+"\n"
    result, _=packet(Notebook(root), candidate, items=material)
    assert result["sources"]
    assert json.loads(result["sources"][0]["context"]["excerpt"])["extensions"] == row["extensions"]

def test_budget_is_not_silently_truncated(imported):
    from importlib import import_module
    root, _, _=imported
    mapped(root)
    collect=getattr(import_module("connectonion.rem."+KIND+"_imports"), "collect_"+KIND)
    with pytest.raises(RemError, match="budget"):
        collect(root, service.subscriptions(root)[KIND], {}, 1, 10)
    assert collect(root, service.subscriptions(root)[KIND], {}, 0, 10).items==[]

@pytest.mark.parametrize("protection", ["writer", "cooling"])
def test_free_form_promotion_preserves_existing_page_protections(imported, tmp_path, protection):
    from connectonion.rem.runner import _promote_maintenance
    from connectonion.rem.leads import remember_no_change
    root, _, _=imported
    mapped(root)
    book=Notebook(root)
    record="projects/protected.md"
    book.stub_project(record, "Protected", paths=["/work/protected"] if protection=="writer" else [])
    if protection=="cooling": remember_no_change(root, record, True)
    before={p:book.read(p) for p in book.list()}
    working=Notebook(tmp_path/"working")
    for path, text in before.items(): working.write(path, text)
    working.write(record, working.read(record)+"\nUnsupported overwrite\n")
    trial=tmp_path/"trial"
    trial.mkdir()
    result=_promote_maintenance(book, working, before, [{"source_kind":KIND,"role":"original","source":"test","text":"evidence"}], trial, None, False)
    assert result and result[0]["record"]==record
    assert book.read(record)==before[record]
    assert (trial/"refused"/record).exists()

def test_reader_context_and_alias_remove_internal_identity(imported):
    from importlib import import_module
    from connectonion.rem.reader import snapshot, render
    from connectonion.rem.source_links import source_record_context
    root, _, _=imported
    mapped(root)
    mod=import_module("connectonion.rem."+KIND+"_imports")
    item=mod.collect_onenote(root, service.subscriptions(root)[KIND], {}, 1, 80000).items[0]
    Notebook(root).write("knowledge/review.md", "# Review\n\nReview is not agreed [1].\n\n## Sources\n- [1] "+item["source"]+" — dated snapshot\n")
    context=source_record_context(root, item["source"])
    assert context["status"]=="resolved"
    assert context["url"]=="https://example.invalid/notes/1"
    data=snapshot(root, local=True)
    html=render(root, local=True)
    assert "Review is not agreed" in html
    assert item["source"] not in html
    assert KIND+":test-account:page-1" not in html


def test_same_content_export_does_not_repeat_model_work(imported):
    root, directory, row=imported
    mapped(root)
    assert service.run_sync(root, source=KIND, runner=lambda *a, **kw: {})["items"]==1
    copyrow=copy.deepcopy(row)
    copyrow["extensions"]["ingestion"]={"mode":"export","path":"exports/repeated/records.jsonl"}
    export=directory/"exports/repeated/records.jsonl"
    export.parent.mkdir(parents=True)
    export.write_text(json.dumps(copyrow)+"\n")
    assert service.run_sync(root, source=KIND, runner=lambda *a, **kw: pytest.fail("duplicate model call"))["items"]==0


def test_inline_free_form_source_is_normalized_for_reader(imported):
    from importlib import import_module
    from connectonion.rem.reader_model import source_references
    root, _, _=imported
    mapped(root)
    mod=import_module("connectonion.rem."+KIND+"_imports")
    item=getattr(mod,"collect_"+KIND)(root,service.subscriptions(root)[KIND],{},1,80000).items[0]
    text="# Learning\n\nUseful lesson [1].\n\nSources: [1] "+item["source"]+" (2026-11-06)\n"
    canonical=mod.canonical_sources(text)
    assert source_references(canonical)==[("1",item["source"])]
    assert "Useful lesson [1]." in canonical


@pytest.mark.parametrize("source_heading", ["## Source", "Source:", "Sources:", "## Sources"])
def test_actual_model_source_heading_reaches_reader_popup(imported,tmp_path,source_heading):
    from importlib import import_module
    from connectonion.rem.runner import _promote_maintenance
    from connectonion.rem.reader import snapshot
    from onenote_reader_fixtures import _run
    root,_,_=imported
    mapped(root)
    notebook=Notebook(root)
    mod=import_module("connectonion.rem."+KIND+"_imports")
    item=getattr(mod,"collect_"+KIND)(root,service.subscriptions(root)[KIND],{},1,80000).items[0]
    before={page:notebook.read(page) for page in notebook.list()}
    working=Notebook(tmp_path/"candidate-notebook")
    for page,text in before.items():working.write(page,text)
    working.stub_topic("knowledge/review.md", "Review")
    text = working.read("knowledge/review.md").replace("## What it is\n- Unknown — not investigated yet", "## What it is\nUseful dated knowledge [1].")
    text = text.replace("## Sources\n- Unknown — not investigated yet", source_heading+"\n- [1] "+item["source"])
    import re
    text = re.sub(r"(?m)^Investigation:.*\n?", "", text)
    working.write("knowledge/review.md", text)
    trial=tmp_path/"trial";trial.mkdir()
    assert not _promote_maintenance(notebook,working,before,[item],trial,None,False)
    result=_run("const COMMENT=/<!--[\\s\\S]*?-->/g,UNKNOWN_TEXT=/^Unknown$/,CITES={from:'',sources:{}},ENTRY=new WeakMap();const entryBody=r=>r.text;const record=listedRecords()[0];console.log(JSON.stringify({count:sourceList(record).length,id:citationId(record,'1')}));",snapshot(root,local=True),("sourceList","rawSection","listItems","sourceId","citationId","citationSource","entryOf","entryModel","entryParse","entryNumbers"))
    assert result["count"]==1
    assert result["id"].startswith("source-ref:")


def test_imported_notes_keep_customer_global_notes_and_activity_behavior(imported,tmp_path):
    from importlib import import_module
    from connectonion.rem.runner import _promote_maintenance
    from connectonion.rem.reader import snapshot
    from onenote_reader_fixtures import _run
    root,_,_=imported
    mapped(root)
    notebook=Notebook(root)
    mod=import_module("connectonion.rem."+KIND+"_imports")
    item=getattr(mod,"collect_"+KIND)(root,service.subscriptions(root)[KIND],{},1,80000).items[0]
    before={page:notebook.read(page) for page in notebook.list()}
    working=Notebook(tmp_path/"candidate-notebook")
    for page,text in before.items():working.write(page,text)
    working.write("notes/open-reflection.md","# Open reflection\n\nAn unresolved reflection about the source discussion [1].\n\n## Sources\n- [1] "+item["source"]+"\n")
    trial=tmp_path/"trial";trial.mkdir()
    assert not _promote_maintenance(notebook,working,before,[item],trial,None,False)
    assert notebook.exists("notes/open-reflection.md")
    result=_run("const shelf=activityShelf('AI notes',REM.records.filter(r=>r.category==='notes'));console.log(JSON.stringify({memory:listedRecords().length,links:walk(shelf).filter(n=>n.tag==='a').map(n=>n.attrs.href)}));",snapshot(root,local=True),("activityShelf",))
    assert result["memory"]==0
    assert "#r=notes%2Fopen-reflection.md" in result["links"]

def test_customer_org_investigation_still_gathers_relevant_imports(imported):
    from importlib import import_module
    from datetime import timedelta
    root,_,_=imported
    mapped(root)
    Notebook(root).stub_org("orgs/atlas.md","Atlas")
    now=datetime.now(timezone.utc)
    mod=import_module("connectonion.rem."+KIND+"_imports")
    assert len(mod.investigation_items(root,service.subscriptions(root)[KIND],"orgs/atlas.md",now-timedelta(days=60),now+timedelta(days=1)))==1

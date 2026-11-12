"""Sprint 1: native investigation priority, final audits and bounded input coverage."""

import json
from pathlib import Path

import pytest

from connectonion.rem import daily, native, native_round, project_claim_review, project_pages, quota, runner, service
from connectonion.rem.config import default_config, prepare, read_config, set_config
from connectonion.rem.files import Notebook, RemError, read_json, state_path, write_json
from connectonion.rem.project_material import mark_written, page_state

pytestmark = pytest.mark.usefixtures("rem_clock")


@pytest.fixture
def notebook(tmp_path, monkeypatch):
    prepare(tmp_path)
    set_config(tmp_path, ["schedule.timezone", "UTC"])
    write_json(state_path(tmp_path, "subscriptions.json"), {})
    write_json(state_path(tmp_path, "consent.json"), {"authorized_at": service.now().isoformat()})
    monkeypatch.setattr(quota, "read", lambda config: {"unknown": "fixture"})
    monkeypatch.setattr(daily, "_clients", lambda sources: {})
    monkeypatch.setattr(runner, "run_task", lambda *a, **kw: pytest.fail("No child model"))
    monkeypatch.setattr(runner, "run_claim_task", lambda *a, **kw: pytest.fail("No child audit"))
    return tmp_path


def save_round(root, jobs, **extra):
    cursor = native_round.prepare(root, read_config(root), scheduled=False)
    cursor.update(batch={"done": True}, jobs=jobs, summaries=[], **extra)
    write_json(state_path(root, "round.json"), cursor)
    return cursor


def audit_notes(task):
    directory = Path(task["material"])
    packet = read_json(directory / "audit-material.json", {})
    lines = []
    for row in packet["sources"]:
        parts = row["context"]["excerpt"].replace('"', '\n').splitlines()
        excerpt = max(parts, key=len)[:80]
        lines.append(f'[{row["citation"]}] PASS — excerpt: "{excerpt}"\n')
    (directory / "notes.md").write_text("".join(lines))


def accept(root, task):
    result = native.submit(root, task["id"])
    if result.get("stage") == "claim-audit":
        audit_notes(result)
        Path(result["candidate"]).write_text('{"verdict":"PASS","findings":[]}')
        result = native.submit(root, task["id"])
    return result


def test_native_limits_default_to_eight_pages_and_two_hundred_calls():
    limits = default_config()["limits"]
    assert limits["runner_calls_per_day"] == 200
    assert limits["quota_floor_percent"] == 90


def test_native_offers_jobs_before_summaries(notebook, monkeypatch):
    cursor = save_round(notebook, [{"record": "people/fern.md", "kind": "person"}])
    Notebook(notebook).stub_project("projects/session.md", "Session")
    cursor["summaries"] = [{"record": "projects/session.md", "key": "session"}]
    monkeypatch.setattr(native_round, "_prepare_job", lambda *a: {"stage": "investigate"})
    monkeypatch.setattr(native_round.sessions, "prepare", lambda *a, **kw: {})
    assert native_round.prepare_task(notebook, cursor, read_config(notebook), notebook)["stage"] == "investigate"


def test_native_queues_at_most_five_summaries(notebook, monkeypatch):
    monkeypatch.setattr(native_round.sessions, "_summary_candidates", lambda root, limit: list(range(limit)))
    cursor = native_round.prepare(notebook, read_config(notebook), scheduled=False)
    assert len(cursor["summaries"]) == 5


@pytest.mark.parametrize("own_page", [False, True])
def test_native_submit_hashes_only_its_own_pages(notebook, own_page):
    from connectonion.rem import reflections
    book, record, other = Notebook(notebook), "people/fern.md", "people/robin.md"
    book.stub_person(record, "Fern Vale", ["fern@example.test"], email="fern@example.test")
    book.stub_person(other, "Robin Lake", ["robin@example.test"], email="robin@example.test")
    row = reflections.add(notebook, record, "Fern requested a pilot review.", author="Casey Reed",
                          basis="Original request", kind="correction")
    task = native.next_task(notebook)
    text = book.read(record).replace("## Who they are\n- Unknown — not investigated yet",
                                    "## Who they are\n- Fern requested a pilot review. [1]")
    Path(task["candidate"]).write_text(text.replace("## Sources\n", f"## Sources\n- [1] reflection:{row['id']}\n"))
    book.path(record if own_page else other).write_text(book.read(record if own_page else other) + "\nExternal edit.\n")
    if own_page:
        with pytest.raises(RemError, match="Task input changed"):
            native.submit(notebook, task["id"])
    else:
        assert accept(notebook, task)["outcome"] == "accepted"


def test_native_audit_packet_excludes_carried_claims_before_model_call(notebook):
    before = "# Fern\n\n## Work\nFern requested a review. [1]\n\n## Sources\n- [1] codex:old\n"
    after = before.replace("## Sources", "Fern requested a demo. [2]\n\n## Sources") + "- [2] codex:new\n"
    items = [{"source": "codex:old", "text": "Please review."}, {"source": "codex:new", "text": "Please demo."}]
    task = project_claim_review.prepare(Notebook(notebook), after, items=items, carried=before,
                                        native=True, directory=notebook)
    packet = read_json(notebook / "audit-material.json", {})
    assert "Fern requested a review." not in packet["candidate"]
    assert "Fern requested a demo." in packet["candidate"]
    assert [row["source_id"] for row in packet["sources"]] == ["codex:new"]
    assert "Fern requested a review." not in (notebook / "audit-material.md").read_text()


@pytest.mark.parametrize("verdict", ["PASS", "FAIL"])
def test_native_multi_round_page_has_one_final_audit_and_no_early_promotion(notebook, monkeypatch, verdict):
    book, record = Notebook(notebook), "orgs/fern-lab.md"
    book.stub_org(record, "Fern Lab", ["fern.example.test"], [])
    original = book.read(record)
    items = [{"role": "user", "source": "codex:fern:1", "text": "Please review the Fern Lab pilot."}]
    state = {"record": record, "parts": [items, [{"role": "user", "source": "codex:fern:2", "text": "Please continue the review."}]], "context": [],
             "page": {"role": "page", "record": record, "source": "investigation:page", "text": original},
             "number": 1, "multi": True, "edited": False, "ledgers": [], "leads": [], "changed": [],
             "refused_sources": [], "refused_rounds": [], "searched": [], "repository_items": [], "session_items": []}
    monkeypatch.setattr(native_round, "_prepare_investigation", lambda *a: state)
    monkeypatch.setattr(native_round.investigate, "record_result", lambda *a, **kw: None)
    save_round(notebook, [{"record": record, "kind": "org"}])
    audits = 0
    for index in range(8):
        task = native.next_task(notebook)
        assert task["outcome"] == "task", task
        candidate = Path(task["candidate"])
        if index == 0:
            candidate.write_text(original.replace("## Sources\n", "## Sources\n- [1] codex:fern:1\n")
                                 .replace("## Who they are\n", "## Who they are\n- A pilot review was requested. [1]\n"))
        result = native.submit(notebook, task["id"])
        assert book.read(record) == original
        if result.get("stage") == "claim-audit":
            audits += 1
            assert index >= 2, "Investigation rounds must finish before the audit"
            decision = {"verdict": verdict, "findings": [] if verdict == "PASS" else [{
                "claim": "A pilot review was requested.", "issue": "Synthetic failure", "evidence": "Fixture",
                "required_correction": "Correct the claim"}]}
            audit_notes(result)
            Path(result["candidate"]).write_text(json.dumps(decision))
            result = native.submit(notebook, task["id"])
            assert result["outcome"] == ("accepted" if verdict == "PASS" else "refused")
            break
        assert result["outcome"] == "accepted", result.get("reason", result)
    assert audits == 1
    assert (book.read(record) != original) == (verdict == "PASS")
    if verdict == "PASS":
        cursor = read_json(state_path(notebook, "round.json"), {})
        cursor["investigation_left"] = 0
        write_json(state_path(notebook, "round.json"), cursor)
        assert native.next_task(notebook)["outcome"] == "done"


@pytest.mark.parametrize("changed,report", [(False, ""), (False, "NO CHANGE"), (False, "NO CHANGE:"),
                                            (True, "Read the supplied input."),
                                            (False, "NO CHANGE: this asks about a different project.")])
def test_native_project_coverage_moves_only_for_changed_accepted_candidate(notebook, monkeypatch, changed, report):
    book, record = Notebook(notebook), "projects/fern.md"
    book.stub_project(record, "Fern")
    original = book.read(record)
    seeded = notebook / "seed.md"
    seeded.write_text(original.replace("## What it is\n", "## What it is\n- The owner requested a prototype. [1]\n")
                      .replace("## Sources\n", "## Sources\n- [1] codex:fern:1\n"))
    runner._promote_candidate(book, record, seeded, original,
                              [{"role": "user", "source": "codex:fern:1", "text": "Please build a prototype."}],
                              notebook, None)
    before = book.read(record)
    old, new = "2026-10-01T00:00:00Z", "2026-10-02T00:00:00Z"
    mark_written(notebook, record, old, inputs_read=1, inputs_available=1)
    item = {"role": "user", "source": "codex:fern:2", "timestamp": new, "text": "Please review the pilot."}
    monkeypatch.setattr(project_pages, "material", lambda *a, **kw: ([
        {"role": "page", "record": record, "source": "investigation:page", "text": before}, item], new))
    monkeypatch.setattr(project_pages, "pending", lambda *a: ([item], "update"))
    save_round(notebook, [{"record": record, "kind": "project"}])
    task = native.next_task(notebook)
    if changed:
        Path(task["candidate"]).write_text(before.replace("## What it is\n", "## What it is\n- A pilot review was requested. [2]\n")
                                           .replace("## Sources\n", "## Sources\n- [2] codex:fern:2\n"))
    (Path(task["material"]) / "report.md").write_text(report)
    result = accept(notebook, task)
    if not changed and report in ("", "NO CHANGE", "NO CHANGE:"):
        assert result["outcome"] == "refused", result
        assert "inputs newer than the page's written_through" in result["reason"]
        assert "new inputs must be read" in result["reason"]
    else:
        assert result["outcome"] == "accepted", result
        for _ in range(3):
            following = native.next_task(notebook)
            if following["outcome"] == "done":
                break
            assert accept(notebook, following)["outcome"] == "accepted"
    assert page_state(notebook, record)["written_through"] == (new if changed else old)
    assert page_state(notebook, record)["last_page_coverage"]["inputs_read"] == 1


@pytest.mark.parametrize('before,after,expected', [
    ('## A\nUnknown.\n\n## B\nThe owner approved launch. [1]',
     '## A\nThe owner approved launch. [1]\n\n## B\nThe owner approved launch. [1]',
     '## A\nThe owner approved launch. [1]'),
    ('## Work\nAvery agreed. [1]\n\nAvery agreed. [1] Blake declined. [2]',
     '## Work\nAvery agreed. [1]\n\nAvery agreed. [1] Blake declined. [2] Casey approved launch. [3]',
     'Casey approved launch. [3]'),
])
def test_native_carried_filter_preserves_new_sections_and_overlapping_claims(before, after, expected):
    sources = '\n\n## Sources\n- [1] codex:first\n- [2] codex:second\n- [3] codex:third\n'
    filtered = project_claim_review._changed_candidate('# Fixture\n\n' + after + sources,
                                                       '# Fixture\n\n' + before + sources)
    assert expected in filtered
    assert filtered.count('The owner approved launch.') == (1 if '## A' in before else 0)


def test_project_draft_at_a_spent_portion_is_kept_while_translation_takes_its_turn(notebook, monkeypatch):
    # rc62 stopped the turn here ("investigation portion cap reached"); D-104 hands the turn to
    # translation and keeps the project draft for when investigation resumes.
    monkeypatch.setattr(native_round, 'prepare_translation', lambda *a: {'stage': 'translate'})
    monkeypatch.setattr(native_round, 'translation_share', lambda root: 4)
    cursor = save_round(notebook, [{'record': 'projects/fern.md', 'kind': 'project'}],
                        project_quote={'draft': 'Private draft'}, investigation_left=0)
    result = native_round.prepare_task(notebook, cursor, read_config(notebook), notebook)
    assert result == {'stage': 'translate'} and cursor['translation_left'] == 3
    assert cursor['job_index'] == 0 and not cursor.get('done')
    assert cursor['project_quote']['draft'] == 'Private draft'


def test_native_project_missing_candidate_is_a_repairable_refusal(notebook):
    book, record = Notebook(notebook), 'projects/fern.md'
    book.stub_project(record, 'Fern')
    candidate = notebook / 'missing.md'
    task = {'root': str(notebook), 'record': record, 'directory': str(notebook), 'candidate': str(candidate),
            'before': {record: book.read(record)}, 'items': [], 'config': read_config(notebook)}
    with pytest.raises(runner.RunFailed, match='Investigation did not write candidate.md'):
        project_pages.check(task, {}, native=True)


@pytest.mark.parametrize('included', [False, True])
def test_native_hashes_owner_page_only_when_material_includes_it(notebook, included):
    book, owner = Notebook(notebook), 'people/casey.md'
    book.stub_person(owner, 'Casey Reed', ['casey@example.test'])
    write_json(state_path(notebook, 'map.json'), {'owner': {'record': owner}})
    workspace = notebook / 'workspace'
    workspace.mkdir()
    items = [{'role': 'context', 'record': owner, 'text': book.read(owner)}] if included else []
    hashes = native._inputs(notebook, {'before': {}, 'items': items}, workspace, handler='runner')
    assert (str(book.path(owner)) in hashes) == included


def test_native_hashes_original_files_nested_in_evidence_material(notebook):
    source = notebook / 'attachment.txt'
    source.write_text('Original evidence.')
    originals = notebook / 'originals.json'
    write_json(originals, [{'role': 'attachment', 'source': 'file:attachment', 'file': str(source), 'text': 'Original evidence.'}])
    workspace = notebook / 'workspace'
    workspace.mkdir()
    task = {'before': {}, 'items': [{'role': 'original_evidence', 'file': str(originals)}]}
    hashes = native._inputs(notebook, task, workspace, handler='runner')
    assert str(source) in hashes
    source.write_text('Changed evidence.')
    assert not native._input_matches(notebook, {'task': task}, source, hashes[str(source)])


@pytest.mark.parametrize('changed', [False, True])
def test_legacy_project_completion_never_marks_unchanged_inputs_read(notebook, monkeypatch, changed):
    book, record = Notebook(notebook), 'projects/fern.md'
    book.stub_project(record, 'Fern')
    before = book.read(record)
    old, new = '2026-10-01T00:00:00Z', '2026-10-02T00:00:00Z'
    mark_written(notebook, record, old)
    if changed:
        book.path(record).write_text(before + '\nA previously audited update.\n')
    items = [{'role': 'user', 'timestamp': new, 'source': 'codex:fern:2', 'text': 'Please review.'}]
    monkeypatch.setattr(project_pages, 'pending', lambda *a: (items, 'update'))
    cursor = {'project_quote': {'before': {record: before}, 'items': items, 'through': new}, 'job_index': 0}
    assert native_round._project_task(notebook, cursor, read_config(notebook), notebook, record) is None
    assert page_state(notebook, record)['written_through'] == (new if changed else old)
    assert cursor['job_index'] == 1

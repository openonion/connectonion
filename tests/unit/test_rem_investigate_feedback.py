"""Explicit investigation must distinguish new feedback from an empty raw window."""

import pytest

from connectonion.rem import investigate as inv, reflections, reviews
from connectonion.rem.config import prepare
from connectonion.rem.files import Notebook


@pytest.mark.parametrize("kind", ["reflection", "review"])
def test_empty_raw_window_still_considers_fresh_targeted_feedback(tmp_path, monkeypatch, kind):
    prepare(tmp_path)
    book = Notebook(tmp_path)
    page = "people/fixture.md"
    book.stub_person(page, "Fixture Person", [], email="fixture@example.test")
    book.note_investigation(page, "synthetic old source")
    before = book.read(page)
    if kind == "reflection":
        row = reflections.add(tmp_path, page, "The role is not established.", author="Synthetic auditor",
                              basis="Retained original only asks a question", kind="correction")
        source = "reflection:" + row["id"]
    else:
        row = reviews.propose(tmp_path, "question", [page], "Was the role established?", "Synthetic original")
        reviews.decide(tmp_path, row["id"], "answer", author="Synthetic reviewer", response="Not established")
        source = "review:" + row["id"]
    monkeypatch.setattr(inv, "gather", lambda *a, **kw: ([], ["synthetic source: 0 matched"]))
    calls = []
    def maintain(notebook, items, config, stage):
        assert next(i["record"] for i in items if i.get("role") == "page") == page
        assert source in {i.get("source") for i in items}
        calls.append(stage)
        return {"changed": [], "report": "Accepted no-change after assessing attributed assertion"}
    result = inv.investigate(tmp_path, page, "Fixture Person", ["fixture"], days=1,
                             clients={}, subscriptions={}, runner=maintain)
    assert calls, "Fresh pending feedback is material even when no new mail/session was found"
    assert result["changed"] == []
    assert book.read(page) == before, "Feedback-only no-change must not stamp new investigation coverage"


def _fixture(root, monkeypatch):
    prepare(root)
    book = Notebook(root)
    page = "people/fixture.md"
    book.stub_person(page, "Fixture Person", [], email="fixture@example.test")
    book.note_investigation(page, "synthetic old source")
    row = reflections.add(root, page, "Role remains disputed.", author="Synthetic auditor", basis="Original")
    monkeypatch.setattr(inv, "gather", lambda *a, **kw: ([], ["synthetic source: 0 matched"]))
    return book, page, "reflection:" + row["id"]


def test_feedback_only_acceptance_is_not_rebought_and_keeps_raw_counts_zero(tmp_path, monkeypatch):
    from connectonion.rem import feedback
    from connectonion.rem.files import read_json, state_path
    book, page, source = _fixture(tmp_path, monkeypatch)
    def assess(notebook, items, config, stage):
        assert stage == "maintain"
        return {"changed": [], "usage": {"input_tokens": 11}}
    result = inv.investigate(tmp_path, page, "Fixture", [], days=1, clients={}, subscriptions={}, runner=assess)
    assert result["mode"] == "feedback_only" and result["items"] == result["items_available"] == 0
    assert result["usage_by_stage"] == {"maintain": {"input_tokens": 11}}
    progress = read_json(state_path(tmp_path, "progress.json"), {})
    assert source in progress["rem_local_material"]
    assert feedback.plan(tmp_path, progress)[0] == []
    with pytest.raises(inv.NothingNew):
        inv.investigate(tmp_path, page, "Fixture", [], days=1, clients={}, subscriptions={},
                        runner=lambda *a, **kw: pytest.fail("Accepted feedback rebought"))


@pytest.mark.parametrize("options", [{"max_calls": 0}, {"read_before": "2026-01-01"}])
def test_no_budget_or_historical_deepen_does_not_consume_current_feedback(tmp_path, monkeypatch, options):
    from connectonion.rem.files import RemError, read_json, state_path
    book, page, source = _fixture(tmp_path, monkeypatch)
    before = book.read(page)
    with pytest.raises(RemError):
        inv.investigate(tmp_path, page, "Fixture", [], days=1, clients={}, subscriptions={},
                        runner=lambda *a, **kw: pytest.fail("No eligible current feedback turn"), **options)
    assert book.read(page) == before
    assert source not in read_json(state_path(tmp_path, "progress.json"), {}).get("rem_local_material", [])


def test_native_feedback_turn_refuses_stale_selected_page_before_model(tmp_path, monkeypatch):
    from connectonion.rem import runner
    from connectonion.rem.files import read_json, state_path
    book, page, source = _fixture(tmp_path, monkeypatch)
    def concurrent_change(notebook, items, config, stage):
        notebook.write(page, notebook.read(page) + "\nConcurrent accepted note.\n")
        return runner.run_stage(notebook, items, config, stage=stage)
    monkeypatch.setattr(runner, "run_task", lambda *a, **kw: pytest.fail("Stale page must not enter model"))
    with pytest.raises(runner.RunFailed, match="changed before"):
        inv.investigate(tmp_path, page, "Fixture", [], days=1, clients={}, subscriptions={}, runner=concurrent_change)
    assert "Concurrent accepted note" in book.read(page)
    assert source not in read_json(state_path(tmp_path, "progress.json"), {}).get("rem_local_material", [])


def test_native_no_change_cannot_ack_a_page_changed_during_model(tmp_path, monkeypatch):
    from connectonion.rem import runner
    from connectonion.rem.files import read_json, state_path
    book, page, source = _fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(runner, "check_skill", lambda *a: None)
    monkeypatch.setattr(runner.run_stage, "preflight", lambda: None)
    def concurrent(*args, **kwargs):
        book.write(page, book.read(page) + "\nConcurrent accepted note.\n")
        return {"result": "NO CHANGE"}
    monkeypatch.setattr(runner, "run_task", concurrent)
    with pytest.raises(runner.RunFailed, match="changed during"):
        inv.investigate(tmp_path, page, "Fixture", [], days=1, clients={}, subscriptions={})
    assert "Concurrent accepted note" in book.read(page)
    progress = read_json(state_path(tmp_path, "progress.json"), {})
    assert source not in progress.get("rem_local_material", [])
    from connectonion.rem import feedback
    feedback.plan(tmp_path, progress)
    assert source not in progress.get("rem_local_material", []), "No recovery proof for rejected no-change"


def test_explicit_manual_retry_can_override_old_feedback_refusal(tmp_path, monkeypatch):
    from connectonion.rem.runner import RunFailed
    book, page, source = _fixture(tmp_path, monkeypatch)
    calls = []
    def assess(*args, **kwargs):
        calls.append(1)
        if len(calls) == 1:
            raise RunFailed("Synthetic refusal")
        return {"changed": []}
    with pytest.raises(RunFailed):
        inv.investigate(tmp_path, page, "Fixture", [], days=1, clients={}, subscriptions={}, runner=assess)
    inv.investigate(tmp_path, page, "Fixture", [], days=1, clients={}, subscriptions={}, runner=assess,
                    retry_refused=True)
    assert calls == [1, 1]


def test_feedback_stage_and_structured_run_fields_survive_cli_logging(tmp_path, monkeypatch):
    from connectonion.cli.commands.rem_commands import _logged
    from connectonion.rem.files import read_json, state_path
    book, page, source = _fixture(tmp_path, monkeypatch)
    stages = []
    def work(update):
        def stage(name, *counts):
            stages.append(name)
            update(name, *counts)
        return inv.investigate(tmp_path, page, "Fixture", [], days=1, clients={}, subscriptions={},
                                runner=lambda *a, **kw: {"changed": []}, stage_progress=stage)
    _logged(tmp_path, page, "investigate", work, quiet=True)
    rows = [read_json(path, {}) for path in state_path(tmp_path, "runs").glob("*.json")]
    assert len(rows) == 1 and rows[0]["mode"] == "feedback_only"
    assert rows[0]["feedback_items"] == 1 and rows[0]["feedback_deferred"] == []
    assert "processing attributed feedback" in stages


@pytest.mark.parametrize("target", ["initial", "org", "project"])
@pytest.mark.parametrize("has_feedback", [False, True])
def test_other_empty_entry_branches_preserve_raw_research_status(tmp_path, monkeypatch, target, has_feedback):
    from connectonion.rem.files import state_path, write_json
    prepare(tmp_path)
    book = Notebook(tmp_path)
    if target == "org":
        page = "orgs/fixture.md"
        book.stub_org(page, "Fixture", domains=["fixture.test"])
        book.note_investigation(page, "synthetic old source")
        monkeypatch.setattr(inv, "website_items", lambda *a, **kw: ([], ["synthetic website: none"]))
    elif target == "project":
        page = "projects/fixture.md"
        folder = tmp_path / "project"
        folder.mkdir()
        book.stub_project(page, "Fixture", paths=[str(folder)])
        book.note_investigation(page, "synthetic old source")
        monkeypatch.setattr(inv, "project_file_inventory", lambda *a, **kw: [])
        monkeypatch.setattr(inv, "project_file_texts", lambda *a, **kw: [])
        monkeypatch.setattr(inv, "checkout_state", lambda *a, **kw: None)
        monkeypatch.setattr("connectonion.rem.project_pages.current_line", lambda *a: None)
        write_json(state_path(tmp_path, "projects/fixture/file-inventory.json"), {"provided_sources": []})
    else:
        page = "people/fixture.md"
        book.stub_person(page, "Fixture", [], email="fixture@example.test")
    before = book.read(page)
    if has_feedback:
        reflections.add(tmp_path, page, "Disputed assertion.", author="Synthetic auditor", basis="Original")
    monkeypatch.setattr(inv, "gather", lambda *a, **kw: ([], ["synthetic source: 0 matched"]))
    calls = []
    def assess(*a, **kw):
        calls.append(1)
        return {"changed": []}
    if has_feedback:
        assert inv.investigate(tmp_path, page, "Fixture", [], days=1, clients={}, subscriptions={},
                               runner=assess)["mode"] == "feedback_only"
        assert calls == [1]
    else:
        with pytest.raises(inv.NothingFound):
            inv.investigate(tmp_path, page, "Fixture", [], days=1, clients={}, subscriptions={}, runner=assess)
        assert calls == []
    assert book.read(page) == before

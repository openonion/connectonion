"""Fresh attributed feedback must reach its declared page before being consumed."""

import pytest

from connectonion.rem import reflections, reviews, service
from connectonion.rem.config import prepare, set_config
from connectonion.rem.files import Notebook, read_json, state_path, write_json
from connectonion.rem.leads import remember_no_change
from connectonion.rem.runner import RunFailed


def _ready(root):
    prepare(root)
    write_json(state_path(root, "subscriptions.json"),
               {k: {"kind": k, "enabled": False} for k in ("codex", "claude-code", "gmail", "outlook")})
    service.approve_sources(root)
    return Notebook(root)


def test_new_feedback_is_not_consumed_by_an_older_no_change_cooldown(tmp_path, monkeypatch):
    book = _ready(tmp_path)
    page = "people/alice.md"
    book.stub_person(page, "Alice Fixture", ["alice"], email="alice@example.test")
    remember_no_change(tmp_path, page, True)
    correction = reflections.add(tmp_path, page, "Alice Fixture did not approve that request.",
                                  author="Synthetic auditor", basis="The original states a question only.",
                                  kind="correction")
    attempted = []
    def maintain(notebook, items, config, **options):
        attempted.append(next(item["record"] for item in items if item.get("role") == "page"))
        return {"changed": [], "report": "Accepted no-change after reading correction"}
    monkeypatch.setattr("connectonion.rem.runner.run_stage", maintain)
    monkeypatch.setattr("connectonion.rem.quota.read", lambda _config: None)
    service.run_sync(tmp_path)
    assert attempted == [page], "Fresh local feedback must not be treated as yesterday's no-change"


def test_refused_answered_question_is_not_acknowledged_as_processed(tmp_path, monkeypatch):
    book = _ready(tmp_path)
    page = "people/alice.md"
    book.stub_person(page, "Alice Fixture", ["alice"], email="alice@example.test")
    question = reviews.propose(tmp_path, "question", [page], "Did Alice Fixture approve?", "Original asks only")
    reviews.decide(tmp_path, question["id"], "answer", author="Synthetic reviewer", response="Not established")
    def refused(notebook, items, config, **options):
        assert next(item["record"] for item in items if item.get("role") == "page") == page
        raise RunFailed("Synthetic refusal")
    monkeypatch.setattr("connectonion.rem.runner.run_stage", refused)
    monkeypatch.setattr("connectonion.rem.quota.read", lambda _config: None)
    result = service.run_sync(tmp_path)
    assert result["refused"] == 1
    progress = read_json(state_path(tmp_path, "progress.json"), {})
    source = "review:" + question["id"]
    assert source not in progress.get("rem_local_material", []), "Refused review answer must remain pending"
    assert source not in progress.get("rem_seen_source_ids", [])


@pytest.mark.parametrize("daily_budget", [20, 1])
def test_page_and_daily_limits_do_not_ack_unattempted_feedback(tmp_path, monkeypatch, daily_budget):
    book = _ready(tmp_path)
    set_config(tmp_path, ["limits.runner_calls_per_day", str(daily_budget), "limits.items_per_batch", "20"])
    rows = {}
    for number in range(6):
        page = f"people/fixture-{number}.md"
        name = f"Fixture Person {number}"
        book.stub_person(page, name, [], email=f"fixture-{number}@example.test")
        correction = reflections.add(tmp_path, page, f"{name}: the request proves intent only.",
                                      author="Synthetic auditor", basis="Original is a question", kind="correction")
        rows[page] = "reflection:" + correction["id"]
    attempted = []
    def maintain(notebook, items, config, **options):
        attempted.append(next(item["record"] for item in items if item.get("role") == "page"))
        return {"changed": [], "report": "Accepted no-change"}
    monkeypatch.setattr("connectonion.rem.runner.run_stage", maintain)
    monkeypatch.setattr("connectonion.rem.quota.read", lambda _config: None)
    service.run_sync(tmp_path)
    assert len(attempted) == min(5, daily_budget)
    progress = read_json(state_path(tmp_path, "progress.json"), {})
    for page, source in rows.items():
        assert (source in progress.get("rem_local_material", [])) == (page in attempted)


def test_partial_write_failure_cannot_ack_an_unattempted_target(tmp_path, monkeypatch):
    book = _ready(tmp_path)
    for page, name in (("people/a.md", "Alice Fixture"), ("people/b.md", "Brenda Fixture")):
        book.stub_person(page, name, [], email=page[7:-3] + "@example.test")
        reflections.add(tmp_path, page, name + " requested review only.",
                        author="Synthetic auditor", basis="Original", kind="correction")
    waiting = reflections.context(tmp_path, "people/b.md")[0]["source"]
    attempted = []
    def maintain(notebook, items, config, **options):
        page = next(item["record"] for item in items if item.get("role") == "page")
        attempted.append(page)
        if page == "people/b.md":
            raise RuntimeError("Synthetic interruption after another target committed")
        notebook.write(page, notebook.read(page) + "\nSynthetic accepted correction.\n")
        return {"changed": [page], "report": "Saved"}
    monkeypatch.setattr("connectonion.rem.runner.run_stage", maintain)
    monkeypatch.setattr("connectonion.rem.quota.read", lambda _config: None)
    result = service.run_sync(tmp_path)
    assert attempted == ["people/a.md", "people/b.md"]
    assert result["outcome"] == "failed" and result["changed"] == ["people/a.md"]
    progress = read_json(state_path(tmp_path, "progress.json"), {})
    assert waiting not in progress.get("rem_local_material", [])
    assert waiting not in progress.get("rem_seen_source_ids", [])


def test_accepted_no_change_feedback_is_not_rebought(tmp_path, monkeypatch):
    book = _ready(tmp_path)
    page = "people/alice.md"
    book.stub_person(page, "Alice Fixture", [], email="alice@example.test")
    correction = reflections.add(tmp_path, page, "Alice Fixture is still unverified.",
                                  author="Synthetic auditor", basis="No supporting original", kind="correction")
    attempted = []
    def maintain(notebook, items, config, **options):
        attempted.append(next(item["record"] for item in items if item.get("role") == "page"))
        return {"changed": [], "report": "Accepted no-change after checking assertion"}
    monkeypatch.setattr("connectonion.rem.runner.run_stage", maintain)
    monkeypatch.setattr("connectonion.rem.quota.read", lambda _config: None)
    service.run_sync(tmp_path)
    assert service.run_sync(tmp_path)["outcome"] == "no_change"
    assert attempted == [page]
    assert "reflection:" + correction["id"] in read_json(state_path(tmp_path, "progress.json"), {}).get("rem_local_material", [])


def test_summary_revision_cannot_repeat_already_accepted_rows(tmp_path, monkeypatch):
    book = _ready(tmp_path)
    page = "people/alice.md"
    book.stub_person(page, "Alice Fixture", [], email="alice@example.test")
    for number in range(3):
        reflections.add(tmp_path, page, f"Alice Fixture assertion {number} remains qualified.",
                        author="Synthetic auditor", basis="Retained original", kind="correction")
    attempted = []
    def maintain(notebook, items, config, **options):
        attempted.append(page)
        notebook.write(page, notebook.read(page) + "\nSynthetic accepted update.\n")
        return {"changed": [page], "report": "Saved"}
    monkeypatch.setattr("connectonion.rem.runner.run_stage", maintain)
    monkeypatch.setattr("connectonion.rem.quota.read", lambda _config: None)
    service.run_sync(tmp_path)
    reflections.compress(tmp_path, page)
    assert reflections.context(tmp_path, page)[0]["role"] == "reflection-summary"
    service.run_sync(tmp_path)
    assert attempted == [page], "A compact representation is not new user feedback"


def test_explicit_feedback_reaches_a_folder_backed_project(tmp_path, monkeypatch):
    book = _ready(tmp_path)
    page = "projects/atlas.md"
    book.stub_project(page, "Atlas Fixture", paths=[str(tmp_path / "repo")])
    reflections.add(tmp_path, page, "The disputed request was not completed.",
                    author="Synthetic auditor", basis="No completion evidence", kind="correction")
    attempted = []
    def maintain(notebook, items, config, **options):
        attempted.append(next(item["record"] for item in items if item.get("role") == "page"))
        return {"changed": [], "report": "Accepted no-change"}
    monkeypatch.setattr("connectonion.rem.runner.run_stage", maintain)
    monkeypatch.setattr("connectonion.rem.quota.read", lambda _config: None)
    service.run_sync(tmp_path)
    assert attempted == [page]


def test_multi_subject_review_only_retries_its_unaccepted_page(tmp_path, monkeypatch):
    from connectonion.rem import refusals
    book = _ready(tmp_path)
    pages = ["people/a.md", "people/b.md"]
    for page in pages:
        book.stub_person(page, "Fixture " + page, [], email=page[7:-3] + "@example.test")
    row = reviews.propose(tmp_path, "link", pages, "Do these refer to the same constraint?", "Synthetic question")
    reviews.decide(tmp_path, row["id"], "no", author="Synthetic reviewer", response="Different contexts")
    calls = []
    def maintain(notebook, items, config, **options):
        page = next(item["record"] for item in items if item.get("role") == "page")
        calls.append(page)
        if calls.count("people/b.md") == 1 and page == "people/b.md":
            raise RunFailed("Synthetic refusal")
        return {"changed": [], "report": "Accepted no-change"}
    monkeypatch.setattr("connectonion.rem.runner.run_stage", maintain)
    monkeypatch.setattr("connectonion.rem.quota.read", lambda _config: None)
    service.run_sync(tmp_path)
    source = "review:" + row["id"]
    assert source not in read_json(state_path(tmp_path, "progress.json"), {}).get("rem_local_material", [])
    monkeypatch.setattr(refusals, "due_for_retry", lambda root: refusals.refused_pages(root))
    service.run_sync(tmp_path)
    assert calls == [*pages, "people/b.md"]
    assert source in read_json(state_path(tmp_path, "progress.json"), {}).get("rem_local_material", [])


def test_refused_feedback_stops_all_pending_and_does_not_repeat_immediately(tmp_path, monkeypatch):
    book = _ready(tmp_path)
    page = "people/alice.md"
    book.stub_person(page, "Alice Fixture", [], email="alice@example.test")
    reflections.add(tmp_path, page, "A qualified assertion.", author="Synthetic auditor", basis="Original")
    calls = []
    def refused(*args, **options):
        calls.append(1)
        assert len(calls) == 1, "Same refused feedback was immediately rebought"
        raise RunFailed("Synthetic refusal")
    monkeypatch.setattr("connectonion.rem.runner.run_stage", refused)
    monkeypatch.setattr("connectonion.rem.quota.read", lambda _config: None)
    assert service.run_sync(tmp_path, all_pending=True)["outcome"] == "deferred"
    assert service.run_sync(tmp_path, all_pending=True)["outcome"] == "deferred"
    assert calls == [1]


def test_feedback_retry_uses_existing_refusal_cap(tmp_path, monkeypatch):
    from connectonion.rem import refusals
    book = _ready(tmp_path)
    page = "people/alice.md"
    book.stub_person(page, "Alice Fixture", [], email="alice@example.test")
    reflections.add(tmp_path, page, "An assertion awaiting assessment.", author="Synthetic auditor", basis="Original")
    calls = []
    def refused(*args, **options):
        calls.append(1)
        raise RunFailed("Synthetic refusal")
    # Simulate the time window having elapsed, while retaining the real retry cap.
    monkeypatch.setattr(refusals, "due_for_retry", lambda root: {
        page: row for page, row in refusals.refused_pages(root).items()
        if row.get("retries", 0) < refusals.MAX_RETRIES})
    monkeypatch.setattr("connectonion.rem.runner.run_stage", refused)
    monkeypatch.setattr("connectonion.rem.quota.read", lambda _config: None)
    for _ in range(refusals.MAX_RETRIES + 3):
        service.run_sync(tmp_path)
    assert len(calls) == 1 + refusals.MAX_RETRIES


def test_content_revision_is_not_hidden_by_an_old_global_consumed_id(tmp_path, monkeypatch):
    book = _ready(tmp_path)
    page = "people/alice.md"
    book.stub_person(page, "Alice Fixture", [], email="alice@example.test")
    row = reflections.add(tmp_path, page, "First assertion", author="Synthetic auditor", basis="Original")
    calls = []
    def maintain(*args, **options):
        calls.append(1)
        return {"changed": [], "report": "Accepted no-change"}
    monkeypatch.setattr("connectonion.rem.runner.run_stage", maintain)
    monkeypatch.setattr("connectonion.rem.quota.read", lambda _config: None)
    service.run_sync(tmp_path)
    # The public add API is immutable. This simulates a changed imported revision
    # or externally altered retained file: an old ID must not attest to new text.
    write_json(state_path(tmp_path, "reflections/" + row["id"] + ".json"),
               {**row, "statement": "Different text must be assessed separately"})
    service.run_sync(tmp_path)
    assert calls == [1, 1]


def test_legacy_consumed_summary_does_not_replay_its_exact_retained_rows(tmp_path, monkeypatch):
    book = _ready(tmp_path)
    page = "people/alice.md"
    book.stub_person(page, "Alice Fixture", [], email="alice@example.test")
    for n in range(3):
        reflections.add(tmp_path, page, f"Assertion {n}", author="Synthetic auditor", basis="Original")
    reflections.compress(tmp_path, page)
    source = reflections.context(tmp_path, page)[0]["source"]
    assert source.startswith("reflection-summary:")
    write_json(state_path(tmp_path, "progress.json"), {"rem_local_material": [source]})
    monkeypatch.setattr("connectonion.rem.runner.run_stage", lambda *a, **kw: pytest.fail("Legacy replay"))
    assert service.run_sync(tmp_path)["outcome"] == "no_change"


def test_feedback_packets_are_target_specific_and_never_lossily_extracted(tmp_path, monkeypatch):
    book = _ready(tmp_path)
    set_config(tmp_path, ["limits.items_per_batch", "1"])
    pages = ["people/a.md", "people/b.md"]
    for page in pages:
        book.stub_person(page, page, [], email=page[7:-3] + "@example.test")
        reflections.add(tmp_path, page, "Only about " + page, author="Synthetic auditor", basis="Original")
    calls = []
    def maintain(notebook, items, config, **options):
        page = next(i["record"] for i in items if i.get("role") == "page")
        assert [i["record"] for i in items if i.get("role") == "reflection"] == [page]
        calls.append(page)
        return {"changed": []}
    monkeypatch.setattr("connectonion.rem.runner.run_stage", maintain)
    monkeypatch.setattr("connectonion.rem.extract.run_extract", lambda *a, **kw: pytest.fail("Lossy feedback extraction"))
    monkeypatch.setattr("connectonion.rem.quota.read", lambda _config: None)
    service.run_sync(tmp_path, all_pending=True)
    assert calls == pages


def test_new_revision_bypasses_exhausted_old_revision_refusal(tmp_path, monkeypatch):
    from connectonion.rem import refusals
    book = _ready(tmp_path)
    page = "people/alice.md"
    book.stub_person(page, "Alice", [], email="alice@example.test")
    row = reflections.add(tmp_path, page, "Old assertion", author="Synthetic auditor", basis="Original")
    monkeypatch.setattr("connectonion.rem.runner.run_stage", lambda *a, **kw: {"refused": "Synthetic refusal"})
    monkeypatch.setattr("connectonion.rem.quota.read", lambda _config: None)
    service.run_sync(tmp_path)
    ledger = refusals.refused_pages(tmp_path)
    ledger[page]["retries"] = refusals.MAX_RETRIES
    write_json(state_path(tmp_path, refusals.REFUSED), ledger)
    write_json(state_path(tmp_path, "reflections/" + row["id"] + ".json"), {**row, "statement": "Revised assertion"})
    calls = []
    def maintain(*a, **kw):
        calls.append(1)
        return {"changed": []}
    monkeypatch.setattr("connectonion.rem.runner.run_stage", maintain)
    service.run_sync(tmp_path)
    assert calls == [1]


def test_daily_retry_records_feedback_receipt_before_next_sync(tmp_path, monkeypatch):
    from connectonion.rem import daily, refusals
    from connectonion.rem.config import read_config
    book = _ready(tmp_path)
    page = "people/alice.md"
    book.stub_person(page, "Alice", [], email="alice@example.test")
    reflections.add(tmp_path, page, "Assertion", author="Synthetic auditor", basis="Original")
    monkeypatch.setattr("connectonion.rem.runner.run_stage", lambda *a, **kw: {"refused": "Synthetic refusal"})
    monkeypatch.setattr("connectonion.rem.quota.read", lambda _config: None)
    service.run_sync(tmp_path)
    calls = []
    def maintain(*a, **kw):
        calls.append(1)
        return {"changed": []}
    monkeypatch.setattr("connectonion.rem.runner.run_stage", maintain)
    daily._maintain_again(tmp_path, page, refusals.refused_for(tmp_path, page), read_config(tmp_path))
    service.run_sync(tmp_path)
    assert calls == [1], "Daily acceptance must not be bought a second time by sync"


def test_oversized_feedback_does_not_starve_capture_queue(tmp_path, monkeypatch):
    book = _ready(tmp_path)
    set_config(tmp_path, ["limits.input_chars_per_batch", "100000"])
    page = "people/alice.md"
    book.stub_person(page, "Alice", [], email="alice@example.test")
    reflections.add(tmp_path, page, "x" * 200000, author="Synthetic auditor", basis="Original")
    captured = {"source": "codex:fixture:1", "timestamp": "2026-10-20T00:00:00Z", "text": "Ordinary capture"}
    write_json(state_path(tmp_path, "capture-queue/fixture.json"), captured)
    calls = []
    def maintain(book, items, config, **kw):
        calls.extend(item["source"] for item in items)
        return {"changed": []}
    monkeypatch.setattr("connectonion.rem.quota.read", lambda _config: None)
    result = service.run_sync(tmp_path, runner=maintain)
    assert calls == [captured["source"]]
    assert result["feedback_deferred"]


def test_overwritten_legacy_summary_is_deferred_without_replaying_old_rows(tmp_path, monkeypatch):
    book = _ready(tmp_path)
    page = "people/alice.md"
    book.stub_person(page, "Alice", [], email="alice@example.test")
    for n in range(3):
        reflections.add(tmp_path, page, f"Old {n}", author="Synthetic auditor", basis="Original")
    reflections.compress(tmp_path, page)
    old = reflections.context(tmp_path, page)[0]["source"]
    write_json(state_path(tmp_path, "progress.json"), {"rem_local_material": [old]})
    reflections.add(tmp_path, page, "New assertion", author="Synthetic auditor", basis="Original")
    reflections.compress(tmp_path, page)
    monkeypatch.setattr("connectonion.rem.runner.run_stage", lambda *a, **kw: pytest.fail("Uncertain legacy replay"))
    result = service.run_sync(tmp_path)
    assert result["outcome"] == "deferred"
    assert any("legacy" in r["reason"].lower() for r in result["feedback_deferred"])


@pytest.mark.parametrize("save", [False, True])
def test_native_promotion_recovery_requires_exact_saved_postimage(tmp_path, monkeypatch, save):
    from connectonion.rem import feedback, runner
    book = _ready(tmp_path)
    page = "people/alice.md"
    book.stub_person(page, "Alice", [], email="alice@example.test")
    reflections.add(tmp_path, page, "Assertion", author="Synthetic auditor", basis="Original")
    items, _ = feedback.plan(tmp_path, {})
    real_write = Notebook.write
    def interrupted(notebook, record, text):
        if save:
            real_write(notebook, record, text)
        raise RuntimeError("Synthetic process loss at promotion")
    monkeypatch.setattr(Notebook, "write", interrupted)
    with pytest.raises(RuntimeError):
        runner._write_page(book, page, book.read(page) + "\nAccepted synthetic text.\n", items)
    monkeypatch.setattr(Notebook, "write", real_write)
    eligible, _ = feedback.plan(tmp_path, {})
    assert bool(eligible) is not save


def test_native_accepted_no_change_recovers_before_sync_callback(tmp_path, monkeypatch):
    from connectonion.rem import feedback
    book = _ready(tmp_path)
    page = "people/alice.md"
    book.stub_person(page, "Alice", [], email="alice@example.test")
    reflections.add(tmp_path, page, "Assertion", author="Synthetic auditor", basis="Original")
    monkeypatch.setattr("connectonion.rem.runner.run_task", lambda *a, **kw: {"result": "NO CHANGE"})
    monkeypatch.setattr("connectonion.rem.quota.read", lambda _config: None)
    real_finish = feedback.finish
    def interrupted(*a, **kw):
        raise RuntimeError("Synthetic interruption before callback receipt")
    monkeypatch.setattr(feedback, "finish", interrupted)
    assert service.run_sync(tmp_path)["outcome"] == "failed"
    monkeypatch.setattr(feedback, "finish", real_finish)
    monkeypatch.setattr("connectonion.rem.runner.run_task", lambda *a, **kw: pytest.fail("Accepted turn rebought"))
    assert service.run_sync(tmp_path)["outcome"] == "no_change"
    assert service.run_sync(tmp_path)["outcome"] == "no_change"

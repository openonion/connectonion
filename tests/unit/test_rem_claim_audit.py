"""A cited-claim failure must not replace the owner's accepted page."""

import json
import importlib
from types import SimpleNamespace

import pytest

from connectonion.rem import claim_audit, runner
from connectonion.rem.files import Notebook
from connectonion.rem.config import prepare


def test_provider_dates_reject_a_wrong_source_day_and_next_day_wording():
    packet = {"candidate": "Corrected the next day [8][10].\n\n## Sources\n", "sources": [
        {"citation": "8", "definition": "- [8] gmail:first — 2026-08-12",
         "context": {"time": "2026-08-12T01:34:42+00:00"}},
        {"citation": "10", "definition": "- [10] gmail:correction — 2026-08-13",
         "context": {"time": "2026-08-12T01:36:40+00:00"}},
    ]}
    findings = claim_audit.date_findings(packet, "Australia/Sydney")
    assert len(findings) == 2
    assert "Source [10] date" in findings[0]["issue"]
    assert "next-day" in findings[1]["issue"]


def test_a_future_event_is_not_mistaken_for_a_next_day_correction():
    packet = {"candidate": "Meeting scheduled for the next day [8][10].\n\n## Sources\n", "sources": [
        {"citation": "8", "definition": "- [8] gmail:invite — 2026-08-12",
         "context": {"time": "2026-08-12T01:34:42+00:00"}},
        {"citation": "10", "definition": "- [10] gmail:confirmation — 2026-08-12",
         "context": {"time": "2026-08-12T01:36:40+00:00"}},
    ]}
    assert claim_audit.date_findings(packet, "Australia/Sydney") == []


def test_missing_cited_original_never_reaches_the_model(tmp_path):
    prepare(tmp_path)
    candidate = "# Mia\n\nMia leads the team [1].\n\n## Sources\n- [1] gmail:missing — 2026-08-12\n"

    def should_not_run(*args):
        raise AssertionError("No model call without the cited original")

    report, usage = claim_audit.review(Notebook(tmp_path), candidate, [], "Australia/Sydney",
                                       {}, tmp_path, should_not_run)
    assert report == {"verdict": "insufficient", "findings": [], "missing_citations": ["1"]}
    assert usage == {}


def test_failed_claim_review_preserves_the_previous_person_page(tmp_path, monkeypatch):
    prepare(tmp_path)
    notebook = Notebook(tmp_path)
    record = "people/mia.md"
    notebook.stub_person(record, "Mia", ["mia@example.org"], email="mia@example.org")
    before = notebook.read(record)
    revised = (before.replace("- Unknown — not investigated yet", "- Unknown")
               .replace("## Who they are\n- Unknown", "## Who they are\n- Mia leads the team [1].")
               .replace("- (none yet)", "- [1] gmail:message — 2026-08-12"))
    candidate = tmp_path / "candidate.md"
    candidate.write_text(revised)

    def rejected(*args):
        return {"verdict": "fail", "findings": [{"issue": "The cited mail does not prove that role"}]}, {
            "input_tokens": 100, "output_tokens": 20}

    monkeypatch.setattr(claim_audit, "review", rejected)
    config = {"schedule": {"timezone": "Australia/Sydney"}}
    items = [{"role": "page", "record": record, "text": before},
             {"source": "gmail:message", "text": "A message"}]
    with pytest.raises(runner.RunFailed) as raised:
        runner._promote_candidate(notebook, record, candidate, before, items, tmp_path, {"input_tokens": 200},
                                  claim_config=config)
    assert notebook.read(record) == before
    assert raised.value.usage == {"input_tokens": 300, "output_tokens": 20}
    assert json.loads((tmp_path / "claim-review.json").read_text())["verdict"] == "fail"
    assert json.loads((tmp_path / "review.json").read_text())["factual_quality"] == "bounded citation audit failed"


def test_audit_protocol_error_leaves_the_previous_page_and_candidate(tmp_path, monkeypatch):
    prepare(tmp_path)
    notebook = Notebook(tmp_path)
    record = "people/mia.md"
    notebook.stub_person(record, "Mia", ["mia@example.org"], email="mia@example.org")
    before = notebook.read(record)
    candidate = tmp_path / "candidate.md"
    candidate.write_text(before.replace("- Unknown — not investigated yet", "- Unknown")
                         .replace("## Who they are\n- Unknown", "## Who they are\n- Mia leads the team [1].")
                         .replace("- (none yet)", "- [1] gmail:message — 2026-08-12"))

    def bad_protocol(*args):
        raise ValueError("audit returned malformed JSON")

    monkeypatch.setattr(claim_audit, "review", bad_protocol)
    items = [{"role": "page", "record": record, "text": before},
             {"source": "gmail:message", "text": "A message"}]
    with pytest.raises(ValueError, match="malformed JSON"):
        runner._promote_candidate(notebook, record, candidate, before, items, tmp_path, {},
                                  claim_config={"schedule": {"timezone": "Australia/Sydney"}})
    assert notebook.read(record) == before
    assert candidate.is_file()


def test_codex_audit_sends_private_sources_over_stdin(tmp_path, monkeypatch):
    codex = importlib.import_module("connectonion.useful_tools.codex")

    monkeypatch.setattr(codex, "_base_command", lambda: ["codex", "app-server"])
    seen = {}

    def completed(command, **kwargs):
        seen.update(command=command, input=kwargs["input"])
        (tmp_path / "claim-answer.json").write_text('{"verdict":"FAIL","findings":[]}')
        event = {"type": "turn.completed", "usage": {"input_tokens": 42, "output_tokens": 4}}
        return SimpleNamespace(returncode=0, stdout=json.dumps(event), stderr="")

    monkeypatch.setattr(runner.subprocess, "run", completed)
    config = {"runner": "codex", "model": "gpt-6-luna", "limits": {"timeout_seconds": 600}}
    result = runner.run_claim_task(tmp_path, "PRIVATE SOURCE BODY", config, "claim-audit")
    assert seen["input"] == "PRIVATE SOURCE BODY"
    assert "PRIVATE SOURCE BODY" not in " ".join(seen["command"])
    assert result["usage"] == {"input_tokens": 42, "cached_input_tokens": 0, "output_tokens": 4}


def test_coai_audit_reads_its_packet_without_putting_sources_in_the_prompt(tmp_path, monkeypatch):
    def read_packet(workspace, prompt, config, stage):
        assert stage == "claim-audit"
        assert "PRIVATE SOURCE BODY" not in prompt
        assert (workspace / "claim-input.txt").read_text() == "PRIVATE SOURCE BODY"
        return {"result": '{"verdict":"PASS","findings":[]}', "usage": {"input_tokens": 12}}

    monkeypatch.setattr(runner, "run_task", read_packet)
    result = runner.run_claim_task(tmp_path, "PRIVATE SOURCE BODY", {"runner": "coai"}, "claim-audit")
    assert json.loads(result["result"])["verdict"] == "PASS"

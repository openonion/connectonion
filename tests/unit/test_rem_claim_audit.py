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


def test_same_day_after_a_correction_is_not_read_as_the_day_after():
    packet = {"candidate": "Corrected it minutes later on the same day after checking [8][10].\n\n## Sources\n",
              "sources": [
                  {"citation": "8", "definition": "- [8] gmail:first — 2026-08-12",
                   "context": {"time": "2026-08-12T01:34:42+00:00"}},
                  {"citation": "10", "definition": "- [10] gmail:correction — 2026-08-12",
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


@pytest.mark.parametrize("cited", [False, True])
def test_person_audit_supplies_the_original_mail_envelope(tmp_path, monkeypatch, cited):
    prepare(tmp_path)
    context = {"gmail:pilot": {"excerpt": "We signed a pilot.", "truncated": False}} if cited else {}
    monkeypatch.setattr(claim_audit, "cited_context", lambda *_args, **_kwargs: context)
    mail = {"role": "other", "source": "gmail:pilot", "text": "We signed a pilot.",
            "speaker": "Ada <ada@example.org>",
            "participants": {"from": "Ada <ada@example.org>", "to": "owner@example.org", "cc": []},
            "subject": "Pilot", "timestamp": "2026-10-01T00:00:00+00:00"}
    page = "# Ada\n\nAda reported a pilot [1].\n\n## Sources\n- [1] gmail:pilot — 2026-10-01\n"

    material, missing = claim_audit.packet(Notebook(tmp_path), page, [mail])

    assert missing == []
    context = material["sources"][0]["context"]
    assert context["sender"] == mail["speaker"]
    assert context["participants"] == mail["participants"]
    assert context["subject"] == "Pilot"


def test_person_audit_can_review_a_source_packet_above_the_old_100kb_limit(tmp_path, monkeypatch):
    material = {'candidate': '# Person\n\nA finding [1].\n\n## Sources\n- [1] codex:session — 2026-10-03',
                'sources': [{'citation': '1', 'definition': '- [1] codex:session — 2026-10-03',
                             'context': {'excerpt': 'source text ' * 11_000, 'truncated': False}}],
                'linked_pages': []}
    monkeypatch.setattr(claim_audit, 'packet', lambda *_args: (material, []))
    called = []

    def approved(_workspace, prompt, _config, _stage):
        called.append(len(prompt.encode()))
        return {'result': '{"verdict":"PASS","findings":[]}', 'usage': {'input_tokens': 42}}

    report, usage = claim_audit.review(Notebook(tmp_path), material['candidate'], [],
                                       'Australia/Sydney', {}, tmp_path, approved)
    assert called[0] > 100_000
    assert report['verdict'] == 'pass'
    assert usage == {'input_tokens': 42}


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


def test_coai_audit_is_one_tool_free_call_with_private_evidence_in_the_api_body(tmp_path, monkeypatch):
    from connectonion.core import llm
    from connectonion.core.usage import TokenUsage

    seen = {}

    def complete(messages, tools):
        seen.update(messages=messages, tools=tools)
        return SimpleNamespace(content='{"verdict":"PASS","findings":[]}',
                               usage=TokenUsage(input_tokens=12, output_tokens=4, cost=0.001))

    def create(model):
        seen["model"] = model
        return SimpleNamespace(complete=complete)

    monkeypatch.setattr(llm, "create_llm", create)
    result = runner.run_claim_task(tmp_path, "PRIVATE SOURCE BODY",
                                   {"runner": "coai", "model": "co/gemini-3.8-flash"}, "claim-audit")
    assert json.loads(result["result"])["verdict"] == "PASS"
    assert seen["messages"] == [{"role": "user", "content": "PRIVATE SOURCE BODY"}]
    assert seen["model"] == "co/gemini-3.8-flash"
    assert seen["tools"] is None
    assert not (tmp_path / "claim-input.txt").exists()
    assert result["usage"]["input_tokens"] == 12

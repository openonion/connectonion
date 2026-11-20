"""What one audited day of real runs cost, and the rule each cost became (#3083)."""

import json

from connectonion.rem import project_claim_review, refusals, runner
from connectonion.rem.config import prepare
from connectonion.rem.files import Notebook

# ---------------------------------------------- the runner and the auditor agree on a contact the runner removed

NOTICE = ("Hi all,\nPlease see the notice below about the shared office.\n\n"
          "For more information contact Pat Lee, Facilities Manager\nPh 0491 570 156\n")
REMOVED_RULE = ("runner_removed lists contact values code took off this page before you saw it, because no "
                "original shows them to be this person's own. Their absence, and a contact field that says "
                "Unknown in their place, is not a finding; never ask for one of them to be restored. ")


def person_candidate(tmp_path):
    prepare(tmp_path)
    notebook = Notebook(tmp_path)
    notebook.stub_person("people/mia.md", "Mia Chen", ["mia.chen@harbour.example"], email="mia.chen@harbour.example")
    original = notebook.read("people/mia.md")
    candidate = tmp_path / "candidate.md"
    candidate.write_text(original.replace("## Who they are\n- Unknown — not investigated yet",
                                          "## Who they are\n- Forwarded the shared office notice. [1]")
                         .replace("- Phone: Unknown", "- Phone: 0491 570 156 [1]")
                         .replace("- (none yet)", "- [1] gmail:n1 — 2026-02-03")
                         .replace("- Unknown — not investigated yet", "- Unknown"), encoding="utf-8")
    items = [{"role": "other", "speaker": "Mia Chen <mia.chen@harbour.example>", "source": "gmail:n1",
              "timestamp": "2026-02-03T01:00:00+00:00", "subject": "Shared office", "text": NOTICE}]
    return notebook, original, candidate, items


def test_the_audit_packet_names_the_contact_the_runner_removed(tmp_path):
    """One page was parked six times in a day: the candidate's phone was removed before the audit,
    the auditor read the same mail, and failed the page for calling the phone unknown."""
    notebook, original, candidate, items = person_candidate(tmp_path)
    audit = runner._promote_candidate(notebook, "people/mia.md", candidate, original, items, tmp_path, None,
                                      claim_config={}, native=True)
    material = json.loads((tmp_path / "audit-material.json").read_text())
    assert "0491 570 156" not in material["candidate"]
    assert material["runner_removed"] == ["0491 570 156"]
    assert REMOVED_RULE in audit["needs_review"]
    assert "runner_removed" in (tmp_path / "audit-material.md").read_text()


def test_a_finding_that_asks_for_a_removed_contact_back_is_not_a_finding(tmp_path):
    candidate = ("# Mia Chen\n\nMia forwarded the notice [1].\n\n## Facts\n- Phone: Unknown\n\n"
                 "## Sources\n- [1] gmail:n1\n")
    items = [{"source": "gmail:n1", "text": NOTICE}]
    task = project_claim_review.prepare(Notebook(tmp_path), candidate, record="people/mia.md", items=items,
                                        removed=["0491 570 156 [1]"])
    restore = {"claim": "Phone: Unknown", "issue": "The original establishes a phone",
               "evidence": "Ph 0491 570 156", "required_correction": "Set Phone to 0491570156"}
    other = {"claim": "Mia forwarded the notice.", "issue": "Unsupported", "evidence": "none",
             "required_correction": "Remove it"}
    report, _ = project_claim_review.check(task, {"result": json.dumps({"verdict": "FAIL", "findings": [restore]})})
    assert report["verdict"] == "pass" and report["findings"] == []
    assert report["runner_removed_findings"] == [restore]
    report, _ = project_claim_review.check(task, {"result": json.dumps({"verdict": "FAIL",
                                                                         "findings": [restore, other]})})
    assert report["verdict"] == "fail" and report["findings"] == [other]


def test_a_packet_with_nothing_removed_says_nothing_about_removal(tmp_path):
    candidate = "# Mia Chen\n\nMia forwarded the notice [1].\n\n## Sources\n- [1] gmail:n1\n"
    task = project_claim_review.prepare(Notebook(tmp_path), candidate, record="people/mia.md",
                                        items=[{"source": "gmail:n1", "text": NOTICE}])
    assert task["material"]["runner_removed"] == [] and REMOVED_RULE not in task["prompt"]


# ---------------------------------------------- a parked page waits for new material, not for the next night

def test_a_page_parked_again_for_the_same_reason_on_the_same_material_waits_for_new_material(tmp_path):
    from datetime import datetime, timedelta, timezone
    later = datetime.now(timezone.utc) + timedelta(hours=refusals.RETRY_HOURS + 1)
    why = "parked: refused twice for the same reason: Cited-claim audit did not pass: Phone: Unknown"
    refusals.remember_refusal(tmp_path, "people/a.md", ["gmail:1"], why, stage="parked", parked=True)
    assert "people/a.md" in refusals.due_for_retry(tmp_path, now=later)
    refusals.mark_retried(tmp_path, "people/a.md")
    refusals.remember_refusal(tmp_path, "people/a.md", ["gmail:1"], why, stage="parked", parked=True)
    assert "people/a.md" not in refusals.due_for_retry(tmp_path, now=later)
    assert "people/a.md" in refusals.waiting_for_material(tmp_path)
    # New material, or a different reason, is a new question.
    refusals.remember_refusal(tmp_path, "people/a.md", ["gmail:1", "gmail:2"], why, stage="parked", parked=True)
    assert "people/a.md" in refusals.due_for_retry(tmp_path, now=later)
    assert "people/a.md" not in refusals.waiting_for_material(tmp_path)


def test_a_page_out_of_retries_is_not_listed_again_until_something_new_arrives(tmp_path, monkeypatch, rem_clock):
    """Past its retries a parked page left the retry list and came straight back through its own queue."""
    from datetime import datetime, timedelta, timezone
    from connectonion.rem import daily, native_round, service
    prepare(tmp_path)
    monkeypatch.setattr(daily, "_clients", lambda sources: {})
    monkeypatch.setattr(daily, "_owner_due", lambda root: [])
    monkeypatch.setattr("connectonion.rem.people_pages.correspondents_since", lambda *a, **k: {"records": []})
    monkeypatch.setattr("connectonion.rem.project_pages.queue", lambda root, **kw: [])
    monkeypatch.setattr(daily, "unfinished_by_recency", lambda root: [])
    record = "people/fern.md"
    Notebook(tmp_path).stub_person(record, "Fern Vale", ["fern@example.test"], email="fern@example.test")
    row = {"record": record, "mode": "full", "last_activity": (service.now() - timedelta(days=2)).isoformat()}
    monkeypatch.setattr("connectonion.rem.people_pages.queue", lambda *a, **kw: [row])
    listed = lambda: {job["record"] for job in native_round._jobs(tmp_path, False, [], {})}  # noqa: E731
    assert record in listed()
    refusals.remember_refusal(tmp_path, record, ["gmail:1"], "parked: refused 4 times: x", stage="parked", parked=True)
    for _ in range(refusals.MAX_RETRIES):
        refusals.mark_retried(tmp_path, record)
    monkeypatch.setattr(refusals, "parked_waiting", lambda root, **kw: {})  # a later night
    assert record not in listed()
    row["last_activity"] = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    assert record in listed()


# ---------------------------------------------- a native worker is given what fits, and one file to read when it does not

SMALL = [{"role": "user", "source": "codex:abc:1", "text": "shipped the reader", "timestamp": "2026-09-24"}]


def test_a_native_worker_is_given_material_that_fits(tmp_path):
    """In 56 native turns the worker read material.md 320 times, material.json 318 times, the SKILL.md
    it already had 57 times and instructions.md 35 times: the inline branch was only for co ai."""
    prompt = runner.task_prompt(tmp_path, SMALL, "maintain", "codex", native=True)
    assert "<material>" in prompt and "shipped the reader" in prompt and "<instructions>" in prompt
    assert "Read all source material" not in prompt
    assert ("Do not reread this task's instructions.md, additional-instructions.md, "
            "material.md or material.json; their content is already inline.") in prompt
    assert "do not open its SKILL.md" in prompt and "already loaded" not in prompt
    assert "already loaded" in runner.task_prompt(tmp_path, SMALL, "maintain", "codex")   # co ai expands the Skill


def test_a_native_prompt_counts_the_skill_it_carries(tmp_path):
    """Native prepends the stage Skill to the same argv string, so the Skill is part of what must fit."""
    core = len((runner.useful_skills_dir() / "rem-maintain/SKILL.md").read_bytes())
    additions = len(runner.instructions("maintain", "codex").encode()) - core
    # Room for the additions and the material, and for half the Skill but not all of it.
    items = [{**SMALL[0], "text": "x " * ((runner.INLINE_LIMIT - additions - core // 2) // 2)}]
    assert "<material>" in runner.task_prompt(tmp_path, items, "maintain", "codex")
    assert "<material>" not in runner.task_prompt(tmp_path, items, "maintain", "codex", native=True)


def test_native_material_too_big_to_give_names_one_file(tmp_path):
    """The same content in two formats was read twice: 320 reads of one, 318 of the other."""
    big = [{**SMALL[0], "text": "x " * runner.INLINE_LIMIT}]
    prompt = runner.task_prompt(tmp_path, big, "maintain", "codex", native=True)
    assert str(tmp_path / "material.md") in prompt and "material.json" not in prompt
    assert "the check ignores where its lines wrap" in prompt
    assert (tmp_path / "material.json").is_file()                                    # still written, for the audit
    assert str(tmp_path / "material.json") in runner.task_prompt(tmp_path, big, "maintain", "codex")

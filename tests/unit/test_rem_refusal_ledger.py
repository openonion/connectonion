"""Every refused page reaches the one ledger, with the material it was refused for.

The 2026-10-10 notebook refused eight pages and its ledger held one (callum):
two skill pages, three sync maintenance turns and two investigation rounds
went nowhere, and nothing retried them.
"""

import pytest

from connectonion.rem import investigate as inv
from connectonion.rem.config import default_config, prepare
from connectonion.rem.files import Notebook, RemError
from connectonion.rem.refusals import due_for_retry, forget_refusal, mark_retried, refused_for, remember_refusal
from connectonion.rem.runner import RunFailed


def test_an_accepted_turn_clears_only_what_it_read(tmp_path):
    remember_refusal(tmp_path, "people/a.md", ["gmail:1", "gmail:2"], "Candidate rejected: x", stage="maintain",
                     material=[{"source": "gmail:1", "text": "one"}, {"source": "gmail:2", "text": "two"}])
    forget_refusal(tmp_path, "people/a.md", ["gmail:1"])
    entry = refused_for(tmp_path, "people/a.md")
    assert entry["sources"] == ["gmail:2"] and entry["material"] == [{"source": "gmail:2", "text": "two"}]
    forget_refusal(tmp_path, "people/a.md", ["gmail:2"])
    assert refused_for(tmp_path, "people/a.md") == {}


def test_a_refused_page_is_retried_once_a_day(tmp_path):
    remember_refusal(tmp_path, "people/a.md", ["gmail:1"], "Candidate rejected: x", stage="investigate")
    assert due_for_retry(tmp_path) == {}
    from datetime import datetime, timedelta, timezone
    tomorrow = datetime.now(timezone.utc) + timedelta(hours=21)
    assert list(due_for_retry(tmp_path, now=tomorrow)) == ["people/a.md"]
    mark_retried(tmp_path, "people/a.md")
    assert due_for_retry(tmp_path, now=datetime.now(timezone.utc) + timedelta(hours=2)) == {}


def test_a_refused_round_inside_an_accepted_investigation_is_ledgered(tmp_path, monkeypatch):
    """Corin Marsh's round 2 (2026-10-10) and Briar's (10-12) were refused inside accepted
    investigations: the run said accepted, and the round's mail was never read again."""
    root = tmp_path / "rem"
    prepare(root)
    Notebook(root).stub_person("people/rowan.md", "Rowan Ashdown", ["rowan"])
    items = [{"text": f"message {i}: " + "x" * 30_000, "source": f"outlook:{i}", "role": "other",
              "timestamp": f"2026-09-{i + 1:02d}T00:00:00Z"} for i in range(12)]
    monkeypatch.setattr(inv, "gather", lambda *a, **kw: (items, ["outlook: 12 matched"]))
    turns = []

    def write(notebook, material, config, **kw):
        turns.append([i["source"] for i in material if i.get("source", "").startswith("outlook:")])
        if len(turns) == 2:
            raise RunFailed("Candidate rejected: Missing or duplicate citation: 22", {"input_tokens": 1})
        page = notebook.path("people/rowan.md")
        page.write_text(page.read_text() + f"\nRound {len(turns)}.\n")
        return {"changed": ["people/rowan.md"], "usage": {"input_tokens": 5}}

    out = inv.investigate(root, "people/rowan.md", "Rowan", ["me@x.y"], days=7, clients={}, subscriptions={},
                          extractor=lambda *a: pytest.fail("no digest"), runner=write)
    assert out["refused_rounds"] == ["Candidate rejected: Missing or duplicate citation: 22"]
    entry = refused_for(root, "people/rowan.md")
    assert entry["sources"] == sorted(turns[1]) and entry["stage"] == "investigation round"


def test_a_refused_skill_page_is_ledgered(tmp_path, monkeypatch):
    """job-followup and x-reply were refused at init and nothing recorded it."""
    from connectonion.rem.skill_runs import investigate_skill_page
    source = tmp_path / "SKILL.md"
    source.write_text("Follow up on job applications.")
    root = tmp_path / "rem"
    record = "skills/catalog/job-followup.md"
    Notebook(root).stub_skill(record, "job-followup", str(source))

    def refused(*args, **kwargs):
        raise RunFailed("Candidate rejected, kept at x: Finding has unresolved citations in Open threads: [5]")
    monkeypatch.setattr("connectonion.rem.runner.run_stage", refused)
    with pytest.raises(RunFailed):
        investigate_skill_page(root, record, [])
    entry = refused_for(root, record)
    assert entry["stage"] == "skill" and any(s.startswith("skill-source:") for s in entry["sources"])

    monkeypatch.setattr("connectonion.rem.runner.run_stage", lambda *a, **k: {"changed": []})
    investigate_skill_page(root, record, [])
    assert refused_for(root, record) == {}


def _page(sources: int, filler: int = 1500) -> str:
    lines = "\n".join(f"- Finding {n} about the project, with detail enough to matter. [{n}]" for n in range(1, sources + 1))
    return (f"# browser\n\n## What it is\n{lines}\n" + "x" * filler + "\n\n## Sources\n"
            + "\n".join(f"- [{n}] codex:s{n}:1 — 2026-10-01" for n in range(1, sources + 1)) + "\n")


def _maintain(tmp_path, monkeypatch, rewrite):
    from connectonion.rem.service import _maintain_pages
    root = tmp_path / "rem"
    prepare(root)
    Notebook(root).write("people/b.md", _page(10))

    def one_turn(book, items, config, kind="", stage="maintain", maintenance_lock_held=False):
        record = next(item["record"] for item in items if item.get("role") == "page")
        if rewrite is None:
            raise RunFailed("Candidate rejected, kept at x: Changed page has no numbered evidence references")
        book.write(record, rewrite)
        return {"changed": [record], "usage": {"input_tokens": 3}}
    monkeypatch.setattr("connectonion.rem.runner.run_stage", one_turn)
    material = [{"role": "extract", "text": "notes", "source": "codex:x +1", "sources": ["codex:x:1", "codex:x:9"],
                 "timestamp": "2026-10-14"}]
    return root, _maintain_pages(root, material, default_config(), "codex", ["people/b.md"]), material


@pytest.mark.parametrize("rewrite, why", [(_page(10, 0) + "y" * 50, "shrank the page"),
                                          (_page(3, 3000), "kept 3 of the page's 10 cited sources")],
                         ids=["size", "sources"])
def test_a_maintenance_turn_that_loses_most_of_a_page_keeps_the_old_one(tmp_path, monkeypatch, rewrite, why):
    """projects/connectonion went 14,356 -> 4,132 and 9,610 -> 3,112 in one-page
    turns the validator accepted, because nothing they dropped was invalid."""
    root, result, _ = _maintain(tmp_path, monkeypatch, rewrite)
    assert Notebook(root).read("people/b.md") == _page(10)
    assert result["changed"] == [] and why in result["refusals"][0]["errors"][0]


def test_a_sync_holds_a_refused_page_s_material_from_every_source(tmp_path, monkeypatch):
    """browser, handoff and startup were refused in a sync's maintenance; the
    codex cursor moved on and they never saw that material again (#2041 audit)."""
    from connectonion.rem.service import _hold_for_refused
    root, result, material = _maintain(tmp_path, monkeypatch, None)
    _hold_for_refused(root, result, material)
    entry = refused_for(root, "people/b.md")
    assert entry["stage"] == "maintain" and entry["material"] == material
    assert entry["sources"] == ["codex:x +1", "codex:x:1", "codex:x:9"]


def test_the_daily_round_retries_a_refused_page_from_its_held_material(tmp_path, monkeypatch):
    from connectonion.rem import daily
    root, result, material = _maintain(tmp_path, monkeypatch, None)
    from connectonion.rem.service import _hold_for_refused
    _hold_for_refused(root, result, material)
    seen = []

    def accepted(book, items, config, kind="", stage="maintain", maintenance_lock_held=False):
        seen.append((kind, [item.get("text") for item in items if item.get("role") != "page"]))
        return {"changed": [], "usage": {"input_tokens": 3}}
    monkeypatch.setattr("connectonion.rem.runner.run_stage", accepted)
    daily._retry(root, "people/b.md", refused_for(root, "people/b.md"), clients={}, sources={},
                 config=default_config())
    assert seen == [("codex", ["notes"])] and refused_for(root, "people/b.md") == {}


def test_a_page_refused_again_on_retry_stays_in_the_ledger(tmp_path, monkeypatch):
    from connectonion.rem import daily
    from connectonion.rem.service import _hold_for_refused
    root, result, material = _maintain(tmp_path, monkeypatch, None)
    _hold_for_refused(root, result, material)
    with pytest.raises(RemError, match="rejected"):
        daily._retry(root, "people/b.md", refused_for(root, "people/b.md"), clients={}, sources={},
                     config=default_config())
    assert refused_for(root, "people/b.md")["material"] == material
    assert due_for_retry(root) == {}   # refused again just now: tomorrow, not on the next run


def test_a_page_refused_again_on_the_same_material_stops_being_retried(tmp_path):
    from datetime import datetime, timedelta, timezone
    from connectonion.rem import refusals
    later = datetime.now(timezone.utc) + timedelta(days=30)
    refusals.remember_refusal(tmp_path, 'people/a.md', ['gmail:1'], 'too long', stage='investigate')
    for _ in range(refusals.MAX_RETRIES):
        assert 'people/a.md' in refusals.due_for_retry(tmp_path, now=later)
        refusals.mark_retried(tmp_path, 'people/a.md')
        refusals.remember_refusal(tmp_path, 'people/a.md', ['gmail:1'], 'too long', stage='investigate')
    assert 'people/a.md' not in refusals.due_for_retry(tmp_path, now=later)
    refusals.remember_refusal(tmp_path, 'people/a.md', ['gmail:2'], 'too long', stage='investigate')
    assert 'people/a.md' in refusals.due_for_retry(tmp_path, now=later)

"""Context over control: what code can resolve or repair is not a refusal.

Each test is the shape of a real refusal from the v192b3 and v193q1 trials
(2026-10-10, 2026-10-15), anonymised.
"""

import hashlib
import json
import subprocess
from pathlib import Path

from typer.testing import CliRunner

from connectonion.rem import facts
from connectonion.rem.config import default_config, prepare
from connectonion.rem.files import Notebook
from connectonion.rem.mail_archive import retain_message
from connectonion.rem.page_review import (archived, clear_placeholders, drop_unresolved, fold_history,
                                          normalize_numbered_sources, repair_run_citations, resolve_sources,
                                          single_title, validate)
from connectonion.rem.store import refresh


def _mail(root, native, sender, date, body, thread="t-1", subject="Coaching terms"):
    row = {"id": native, "from": sender, "to": ["owner@example.org"], "cc": [], "date": date,
           "subject": subject, "thread_id": thread}
    retain_message(root, "outlook", row, f"From: {sender}\nSubject: {subject}\n\n--- Email Body ---\n{body}",
                   fetched_at=date)
    return "outlook:" + hashlib.sha256(native.encode()).hexdigest()[:12]


def _person(root, name="Nina"):
    notebook = Notebook(root)
    notebook.stub_person("people/nina.md", name, ["nina@uni.example"], email="nina@uni.example")
    return notebook, notebook.read("people/nina.md")


# ------------------------------------------- 2. a citation that resolves is kept


def test_mail_the_turn_was_not_handed_but_rem_holds_is_a_real_citation(tmp_path):
    """v192b3 investigate-oe0cfbv0: 2.04M tokens refused for [27][28], real
    mail in .state/mail that supported the claim. Made-up ids still go."""
    prepare(tmp_path)
    reply = _mail(tmp_path, "AQMkNATIVE27", "nina@uni.example", "2026-10-07T01:41:01Z", "Budget agreed.")
    refresh(tmp_path)
    assert archived(tmp_path, reply) and not archived(tmp_path, "outlook:000000000000")
    notebook, original = _person(tmp_path)
    fake = "project-source:" + "ab" * 32
    candidate = (original.replace("## Who they are\n- Unknown — not investigated yet",
                                  "## Who they are\n- Agreed the budget. [1]\n- Ran a hackathon. [2]")
                 .replace("- (none yet)", f"- [1] {reply} — 2026-10-07\n- [2] {fake} — 2026-10-07"))
    text, dropped = drop_unresolved("people/nina.md", candidate, original, [], root=tmp_path)
    assert dropped["citations"] == ["2"] and "Agreed the budget. [1]" in text and "hackathon" not in text
    assert not [e for e in validate("people/nina.md", text, original, [], root=tmp_path) if "identifiable" in e]


def test_a_raw_graph_id_and_a_backticked_id_are_written_as_the_ids_that_resolve(tmp_path):
    """v192b3: a raw Outlook (Graph) id was rejected, and 7 real git citations
    went only for their backticks."""
    prepare(tmp_path)
    digest = _mail(tmp_path, "AQMkADAwATMwRAW", "nina@uni.example", "2026-09-01T00:00:00Z", "Hello.")
    refresh(tmp_path)
    text = ("# Nina\n\nSaid hello. [1] Ran it. [2]\n\n## Sources\n- [1] outlook:AQMkADAwATMwRAW — 2026-09-01\n"
            "- [2] `git:/work/repo:" + "a" * 40 + ":README.md` — 2026-09-01\n")
    resolved = resolve_sources(tmp_path, "people/nina.md", normalize_numbered_sources(text))
    assert f"- [1] {digest} — 2026-09-01" in resolved
    assert "- [2] git:/work/repo:" + "a" * 40 + ":README.md — 2026-09-01" in resolved


def test_a_short_file_hash_is_pinned_to_the_full_sha256_of_the_same_content(tmp_path):
    """v192b3: 41 `file:…@905fb89` citations dropped, each naming a file as it still is."""
    repo = tmp_path / "skills"
    repo.mkdir()
    skill = repo / "SKILL.md"
    skill.write_text("# Note submit\nUploads the images first.\n")
    for command in (["init", "-q"], ["add", "SKILL.md"],
                    ["-c", "user.name=t", "-c", "user.email=t@e", "commit", "-qm", "skill"]):
        subprocess.run(["git", "-C", str(repo), *command], check=True)
    commit = subprocess.run(["git", "-C", str(repo), "rev-parse", "--short", "HEAD"],
                            capture_output=True, text=True, check=True).stdout.strip()
    full = hashlib.sha256(skill.read_bytes()).hexdigest()
    for cited in (f"file:{skill}@{commit}", f"file:{skill}#sha256={full[:16]}"):
        text = f"# S\n\nUploads images. [1]\n\n## Sources\n- [1] {cited} — 2026-10-10\n"
        assert f"- [1] file:{skill}#sha256:{full} — 2026-10-10" in resolve_sources(tmp_path, "skills/catalog/s.md", text)
    assert f"file:{skill}@{full}" in resolve_sources(tmp_path, "projects/p.md",
                                                     f"# P\n\n## Sources\n- [1] file:{skill}@{commit}\n")
    skill.write_text("# Note submit\nChanged since.\n")       # the commit no longer names the file as it is
    text = f"# S\n\n## Sources\n- [1] file:{skill}@{commit}\n"
    assert resolve_sources(tmp_path, "skills/catalog/s.md", text) == text


# ------------------------------------------- 3. inline ids are numbered before facts are checked


NINA = """# Nina

Nina is a manager at the Founders programme [outlook:3a0992e193d0].

## Facts
- Email: nina@uni.example [outlook:3a0992e193d0]
- Phone: +61 400 000 000 (work) [outlook:3a0992e193d0]
- Role: Senior Manager [outlook:3a0992e193d0]
- How we know them: casual coaching terms [outlook:84e76a8ba655][outlook:29f6fb800f12]
- Last contact: 2026-06-29 by email [outlook:3a0992e193d0]

## Sources
- outlook:3a0992e193d0 — 2026-06-29
- outlook:84e76a8ba655 — 2025-04-07
- outlook:29f6fb800f12 — 2025-04-07

Investigation: mapped 2026-10-15
"""


def test_facts_cited_by_inline_source_id_are_kept():
    """v193q1 investigate-z3qdttxi: seven true Facts fields were stripped as
    uncited because they cited `[outlook:…]` instead of `[1]`."""
    numbered = normalize_numbered_sources(NINA)
    assert facts.drop_uncited("people/nina.md", numbered)[1] == []
    assert "- Role: Senior Manager [1]" in numbered and "casual coaching terms [2][3]" in numbered
    assert "- [1] outlook:3a0992e193d0 — 2026-06-29" in numbered
    assert normalize_numbered_sources(numbered) == numbered


def test_a_project_page_citing_in_parentheses_has_numbered_evidence(tmp_path):
    """v193q1 investigate-v338hnr2: 4.56M tokens refused for "no numbered
    evidence references"; every claim read (`project-source:…`)."""
    source, other = "project-source:" + "f" * 64, "project-source:" + "e" * 64
    page = (f"# Rental agent\n\n## What it is\nA rental business. (`{source}`)\n\n## Try it\n"
            f"- `pnpm run dev` builds it. (`{source}`; `{other}`)\n- See [docs](https://x.example).\n\n"
            "```text\n(`codex:not-a-citation`)\n```\n\n---\n## Sources\n"
            f"- `{source}` — README snapshot\n\nInvestigation: mapped 2026-10-15\n")
    numbered = normalize_numbered_sources(page)
    assert "A rental business. [1]" in numbered and "builds it. [1][2]" in numbered
    assert f"- [1] {source} — README snapshot\n- [2] {other}\n" in numbered
    assert "(`codex:not-a-citation`)" in numbered and "[docs](https://x.example)" in numbered


# ------------------------------------------- 6. shapes code can repair


def test_a_second_title_and_a_leftover_placeholder_are_repaired():
    page = "# Atlas\n\n# Atlas\n\n## Where it stands\n- Unknown — not investigated yet\n\n## Sources\n- [1] x\n"
    repaired = clear_placeholders(single_title(page))
    assert repaired.count("# Atlas") == 1 and "## Where it stands\n- Unknown\n" in repaired


def test_a_history_past_sixteen_folds_its_oldest_years_in_code():
    """Ody's History held 17 lines; the page was refused for the seventeenth."""
    rows = ([f"- 2024-0{m}-01: met about step {m} [1]." for m in range(1, 7)]
            + [f"- 2025-{m:02d}-01: agreed step {m} [2]." for m in range(1, 13)])
    page = "# P\n\n## History\n" + "\n".join(reversed(rows)) + "\n\n## Sources\n- [1] a\n- [2] b\n"
    folded = fold_history(page)
    history = folded.partition("## History\n")[2].partition("\n\n## Sources")[0].splitlines()
    assert len(history) == 13 and history[-1].startswith("- 2024: met about step 6 [1]; met about step 5 [1];")
    assert sum(line.startswith("- 2025-") for line in history) == 12       # the newest year stays a line a thread
    assert fold_history(folded) == folded


def test_a_backticked_run_citation_is_dropped_not_refused():
    """1.9.0: `Investigation coverage belongs in the run report` refused 22
    project pages; `investigation:` items are the run's context, not evidence."""
    page = ("# P\n\n## What it is\nA tool. [1][2]\n- Coverage was partial. [2]\n\n## Sources\n"
            "- [1] codex:s:1 — 2026-10-05\n- [2] `investigation:coverage` — 2026-10-08\n")
    repaired = repair_run_citations("projects/p.md", normalize_numbered_sources(page), "")
    assert "A tool. [1]\n" in repaired and "Coverage was partial" not in repaired
    assert "investigation:coverage" not in repaired


def test_a_project_file_without_a_hash_is_salvageable():
    from connectonion.rem.runner import SALVAGEABLE
    assert "Cited file needs a hash or exact Git commit in a mapped repository: file:/x".startswith(SALVAGEABLE)


# ------------------------------------------- 4. maintenance sees what came after its batch


def test_maintenance_is_handed_the_later_replies_in_its_threads(tmp_path, monkeypatch):
    """10 of 35 bad claims in the audit were stale: an open ask a later reply had closed."""
    from connectonion.rem import runner
    prepare(tmp_path)
    ask = _mail(tmp_path, "native-ask", "nina@uni.example", "2026-09-01T00:00:00Z", "Can you send the form?")
    done = _mail(tmp_path, "native-done", "owner@example.org", "2026-09-03T00:00:00Z", "Form sent, all done.")
    _mail(tmp_path, "native-other", "x@other.example", "2026-09-04T00:00:00Z", "Unrelated.", thread="t-2")
    refresh(tmp_path)
    tails = runner.thread_tails(tmp_path, [{"source": ask}])
    assert [t["source"] for t in tails] == [done] and "Form sent" in tails[0]["text"]
    notebook, _ = _person(tmp_path)
    seen = {}

    def run(directory, prompt, config, stage):
        seen["prompt"], seen["material"] = prompt, (Path(directory) / "material.json").read_text()
        raise runner.RunFailed("stop here", None)

    monkeypatch.setattr(runner, "run_task", lambda workdir, prompt, config, stage: run(
        next(Path(workdir).glob("maintain-*")), prompt, config, stage))
    item = {"role": "other", "source": ask, "text": "Can you send the form?", "timestamp": "2026-09-01T00:00:00Z"}
    try:
        runner.run_stage(notebook, [item], default_config(), stage="maintain")
    except runner.RunFailed:
        pass
    assert done in seen["material"] and "thread-tail" in seen["prompt"]
    # Context, not reach: maintenance still writes only inside its workspace.
    assert "workspace-write" in runner.harness_flags({**default_config(), "runner": "codex"}, "maintain")


# ------------------------------------------- 5. the claim audit knows what came later and what code computed


def test_the_claim_audit_reads_later_messages_and_the_runners_contact_dates(tmp_path):
    """v193q1: kupjb5r8 and z3qdttxi failed a true First/Last contact because
    the packet could not prove no other mail; hvcuo9no failed a role in the
    part of a truncated excerpt the packet cut off."""
    from connectonion.rem import project_claim_review
    prepare(tmp_path)
    first = _mail(tmp_path, "native-1", "nina@uni.example", "2026-06-29T00:00:00Z", "Senior Manager, Founders.")
    later = _mail(tmp_path, "native-2", "nina@uni.example", "2026-07-02T00:00:00Z", "Thanks, settled.")
    refresh(tmp_path)
    notebook, _ = _person(tmp_path)
    candidate = f"# Nina\n\n- Last contact: 2026-07-02 [1]\n\n## Sources\n- [1] {first} — 2026-06-29\n"
    facts_item = {"role": "facts", "source": "investigation:facts",
                  "facts": [{"field": "Last contact", "value": "2026-07-02", "source": later}]}
    prompts = []
    project_claim_review.review(notebook, candidate, default_config(), tmp_path,
                                lambda w, prompt, c, s: prompts.append(prompt) or {"result": json.dumps(
                                    {"verdict": "PASS", "findings": []})},
                                record="people/nina.md", items=[facts_item])
    packet = json.loads(prompts[0][prompts[0].index("{\"candidate\""):])
    assert [m["source"] for m in packet["later_messages"]] == [later]
    assert packet["runner_facts"] == [{"field": "Last contact", "value": "2026-07-02", "source": later}]
    assert "not the relationship's first and last contact" in prompts[0]
    assert "left out, not failed" in prompts[0]


# ------------------------------------------- 7. the owner's own request is the retry


def test_naming_a_page_retries_its_refused_material(tmp_path, monkeypatch):
    """A refused page waited for `--retry-refused` even when the owner named it."""
    from connectonion.cli.main import app
    root = tmp_path / "rem"
    prepare(root)
    Notebook(root).stub_person("people/vern.md", "Vern", ["vern@example.org"], email="vern@example.org")
    calls = []
    monkeypatch.setattr("connectonion.cli.commands.rem_commands._investigate_page",
                        lambda root, notebook, record, **kw: calls.append(kw["retry_refused"]) or {"record": record})
    result = CliRunner().invoke(app, ["rem", "--root", str(root), "--json", "investigate", "people/vern.md"])
    assert result.exit_code == 0, result.output
    assert calls == [True]


# ------------------------------------------- 8. context that does not fit is trimmed, not fatal


def test_reflections_past_the_budget_are_trimmed_not_a_failed_turn():
    from connectonion.rem.runner import _with_additions
    items = [{"source": "outlook:a", "text": "x" * 800}]
    additions = [{"source": f"reflection:{n}", "text": "y" * 300} for n in range(5)]
    kept = _with_additions(items, additions, budget=1_800)
    assert kept[0] == items[0] and 1 < len(kept) < 6
    assert len(json.dumps(kept)) <= 1_800


# ------------------------------------------- 9. the owner reads their own labelled mail, locally


def test_labelled_mail_shows_in_the_local_reader_and_never_in_the_shared_view(tmp_path):
    from connectonion.rem.reader import snapshot
    prepare(tmp_path)
    private = _mail(tmp_path, "native-p", "nina@uni.example", "2026-09-01T00:00:00Z",
                    "My surgery is on Friday [sensitive].")
    refresh(tmp_path)
    notebook, original = _person(tmp_path)
    notebook.write("people/nina.md", original.replace("- (none yet)", f"- [1] {private} — 2026-09-01"))
    local, shared = snapshot(tmp_path, local=True), snapshot(tmp_path)
    assert "surgery" in local["source_context"][private]["excerpt"] and not local["shared"]
    assert private not in shared["source_context"] and shared["shared"]
    assert "surgery" not in json.dumps(shared["conversations"])


# ------------------------------------------- 10. skills agree with the code


def test_the_person_skill_and_the_code_keep_the_same_history_limit():
    from connectonion.rem.page_review import HISTORY_LIMIT
    from connectonion.skills_catalog import useful_skills_dir
    text = (useful_skills_dir() / "rem-page-person/SKILL.md").read_text()
    assert f"at most {HISTORY_LIMIT} milestones" in text and "at most 8" not in text
    project = (useful_skills_dir() / "rem-page-project/SKILL.md").read_text()
    assert "Do not search" not in project and "Search the repo for evidence" in project
    maintain = (useful_skills_dir() / "rem-maintain/SKILL.md").read_text()
    assert "today's date, which the task states" in maintain
    abstract = (useful_skills_dir() / "rem-abstract/SKILL.md").read_text()
    assert "already a\nprinciple, written by `rem-maintain`" in abstract


# ------------------------------------------- 11. what code removed is recorded, and refused work kept


def test_maintenance_records_what_it_dropped_and_scrub_keeps_refused_pages(tmp_path):
    from connectonion.rem.runner import _promote_maintenance, scrub_task
    root, work = tmp_path / "rem", tmp_path / "work"
    prepare(root)
    prepare(work)
    notebook, working = Notebook(root), Notebook(work)
    for nb in (notebook, working):
        nb.stub_person("people/ann.md", "Ann", [])
        nb.stub_person("people/bob.md", "Bob", [])
    before = {r: notebook.read(r) for r in notebook.list()}
    items = [{"role": "user", "source": "codex:abc:1", "text": "x", "timestamp": "2026-09-24T00:00:00+00:00"}]
    ann = before["people/ann.md"].replace("## Who they are\n- Unknown — not investigated yet",
                                          "## Who they are\n- Ships the agent. [1]\n- Owns a boat. [2]").replace(
        "- (none yet)", "- [1] codex:abc:1 — 2026-09-24\n- [2] skill-record:" + "c" * 64 + " — 2026-09-24")
    bob = before["people/bob.md"].replace("## Who they are\n- Unknown — not investigated yet",
                                          "## Who they are\n- Invented. [1]").replace(
        "- (none yet)", "- [1] Outlook message 39.")
    working.write("people/ann.md", ann)
    working.write("people/bob.md", bob)
    directory = tmp_path / "maintain-x"
    directory.mkdir()
    _promote_maintenance(notebook, working, before, items, directory, None, False)
    review = json.loads((directory / "review.json").read_text())
    assert review["repairs"]["people/ann.md"]["citations_dropped"] == ["2"]
    assert "Owns a boat" not in notebook.read("people/ann.md")
    (directory / "material.json").write_text("{}")
    scrub_task(directory)
    assert (directory / "refused/people/bob.md").read_text() == bob and not (directory / "material.json").exists()

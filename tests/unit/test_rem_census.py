"""One count for the reader and co rem status, and the status fixes (#2008)."""

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from connectonion.rem.config import prepare
from connectonion.rem.files import Notebook, state_path, write_json


def _notebook(root):
    prepare(root)
    notebook = Notebook(root)
    notebook.stub_person("people/ody.md", "Ody Zhou", ["ody@example.org"], email="ody@example.org")
    notebook.write("people/ody.md", notebook.read("people/ody.md").replace(
        "not investigated yet", "investigated 2026-09-27").replace(
        "## Who they are\n", "## Who they are\nPartner. Last contact: 2026-09-20. [1]\n"))
    notebook.stub_person("people/tam.md", "Tamara", ["tam@example.org"], email="tam@example.org")
    notebook.stub_person("people/apple.md", "Apple", ["appleid@id.apple.com"], email="appleid@id.apple.com")
    notebook.stub_project("projects/atlas.md", "Atlas", ["/repo/atlas"])
    notebook.write("projects/atlas.md", notebook.read("projects/atlas.md") + "- Last seen: 2026-08-02\n")
    notebook.stub_skill("skills/catalog/demo.md", "demo", "/s/demo/SKILL.md", "Does a demo")  # a description is not writing
    return notebook


def test_one_census_counts_written_pages_and_leaves_services_out(tmp_path):
    from connectonion.rem.census import counts, pages
    _notebook(tmp_path)
    found = pages(tmp_path)
    assert counts(tmp_path, found) == {"people": {"mapped": 2, "written": 1}, "projects": {"mapped": 1, "written": 0},
                                       "orgs": {"mapped": 0, "written": 0}, "skills": {"mapped": 1, "written": 0},
                                       "sessions": {"mapped": 0, "written": 0}}
    assert found["people/apple.md"]["service"]
    # Each page's own last activity, never the mtime a map just gave every file.
    assert found["people/ody.md"]["last"] == "2026-09-20"      # last contact, not the day it was investigated
    assert found["projects/atlas.md"]["last"] == "2026-08-02"


def test_the_reader_and_status_share_the_census(tmp_path):
    from connectonion.cli.commands.rem_status import notebook
    from connectonion.rem.reader import snapshot
    _notebook(tmp_path)
    data = snapshot(tmp_path)
    assert data["counts"] == notebook(tmp_path)
    records = {record["path"]: record for record in data["records"]}
    assert records["people/apple.md"]["service"] and not records["people/ody.md"]["service"]
    assert records["skills/catalog/demo.md"]["written"] is False
    assert records["projects/atlas.md"]["last_activity"] == "2026-08-02"


def test_explicit_project_activity_is_not_replaced_by_older_mapped_last_seen():
    from connectonion.rem.census import last_activity
    page = ("# Atlas\n\n## Facts\n- Last activity: 2026-09-26 [1]\n\n"
            "## Paths\n- Last seen: 2026-08-15\n\n"
            "Investigation: mapped 2026-10-01 · written 2026-10-02\n")
    assert last_activity(page) == "2026-09-26"
    # A newer workspace input can concern another project; keep the explicit scoped date.
    assert last_activity(page.replace("Last activity: 2026-09-26", "Last activity: 2026-08-01")) == "2026-08-01"


def test_a_run_whose_process_is_gone_reads_interrupted_at_once(tmp_path, monkeypatch):
    import socket
    from connectonion.rem import service
    monkeypatch.setattr(service, "_alive", lambda pid: False)
    record = {"outcome": "running", "pid": 4242, "host": socket.gethostname()}
    assert service.seen_outcome(record) == "interrupted"
    assert service.seen_outcome({**record, "host": "another-machine"}) == "running"
    monkeypatch.setattr(service, "_alive", lambda pid: True)
    assert service.seen_outcome(record) == "running"


def _run(root, name, started, **fields):
    write_json(state_path(root, f"runs/run_{name * 32}.json"),
               {"id": f"run_{name * 32}", "started_at": started, "outcome": "completed", "changed": [], **fields})


def test_today_sums_every_run_with_usage_and_counts_the_ones_without(tmp_path, monkeypatch):
    from connectonion.rem import service
    prepare(tmp_path)
    monkeypatch.setattr(service, "now", lambda: datetime(2026, 10, 1, 9, tzinfo=timezone.utc))
    _run(tmp_path, "a", "2026-10-01T08:00:00+00:00", runner_attempts=2, usage={"input_tokens": 500, "output_tokens": 5})
    _run(tmp_path, "b", "2026-10-01T08:10:00+00:00", phase="investigate", runner_attempts=0,
         usage={"input_tokens": 1500, "output_tokens": 9})               # a manual investigation's tokens count
    _run(tmp_path, "c", "2026-10-01T08:20:00+00:00", runner_attempts=1, usage=None)
    usage = service.status(tmp_path)["usage_today"]
    assert usage["input_tokens"] == 2000 and usage["runs_without_usage"] == 1


def test_the_last_run_is_in_the_notebooks_zone(tmp_path):
    from connectonion.cli.commands.rem_status import _last_run
    line = _last_run({"started_at": "2026-09-30T20:02:59+00:00", "phase": "sync", "outcome": "completed"},
                     ZoneInfo("Australia/Sydney"))
    assert "2026-10-01 06:02" in line and "20:02" not in line


def test_status_next_is_the_first_thing_to_write(tmp_path):
    from connectonion.cli.commands.rem_status import status_next
    _notebook(tmp_path)
    write_json(state_path(tmp_path, "map.json"), {"owner": {"record": "people/tam.md", "addresses": []}})
    value = {"configured": True, "root": str(tmp_path), "state": "Running in background (launchd)"}
    assert status_next(value) == ["investigate", "me"]


def test_a_progress_line_prints_above_the_spinner_not_over_it():
    from io import StringIO
    from rich.console import Console
    from connectonion.cli.commands import rem_look
    live = Console(file=StringIO(), force_terminal=True, color_system=None, width=80)
    rem_look.LIVE = live
    try:
        rem_look.line("  gmail: to 2026-09-17, 40 mails", err=True)
    finally:
        rem_look.LIVE = None
    assert live.file.getvalue() == "  gmail: to 2026-09-17, 40 mails\n"


def test_a_folder_named_copy_joins_the_skill_it_copies(tmp_path):
    from connectonion.rem.skill_map import scan_skills
    for folder, root, text in (("nonfiction-refine", "agents", "---\ndescription: Refine\n---\nBody A"),
                               ("changxing-nonfiction-refine", "codex", "---\ndescription: Refine\n---\nBody B"),
                               ("linkedin-post", "codex", "---\ndescription: Posts\n---\nC"),
                               ("post", "agents", "---\ndescription: Other\n---\nD")):
        (tmp_path / root / folder).mkdir(parents=True)
        (tmp_path / root / folder / "SKILL.md").write_text(text)
    names = sorted({row["name"] for row in scan_skills([tmp_path / "agents", tmp_path / "codex"])["skills"]})
    assert names == ["linkedin-post", "nonfiction-refine", "post"]


def test_structured_thread_direction_wins_over_words_in_the_body():
    from connectonion.rem.census import direction
    for owner in ("The user", "the user", "THE USER", "you", "You", "Aaron"):
        assert direction(f"{owner} owes Mara: she promised the deck.", "Aaron") == "mine"
        assert direction(f"{owner} asked Mara: you promised to review her answer.", "Aaron") == "theirs"
        assert direction(f"Mara owes {owner}: you promised to review her answer.", "Aaron") == "theirs"
    assert direction("- The user owes Mara: an answer.") == "mine"
    assert direction("Yu at Heidi Health owes Ody A$123.38; you asked about it.") == "third"
    assert direction("Yu owes Ody: the user promised to check.") == "third"
    assert direction("Dr. Yu owes Ody the expense reimbursement.") == "third"
    assert direction("Yu (Heidi Health, Inc.) owes Ody the reimbursement.") == "plain"
    assert direction("The user needs to reply to Mara") == "mine"
    assert direction("Aaron asked Adi to arrange a call", "Aaron") == "theirs"
    assert direction("Mara promised the deck") == "theirs"
    assert direction("Scope to decide together") == "plain"


def test_calm_thread_lines_do_not_become_open_context():
    from connectonion.rem.census import threads
    page = "# Atlas\n\n## Open threads\n" + "\n".join("- " + text for text in (
        "No work is confirmed pending as of 2026-10-16.", "No confirmed pending work.",
        "No known pending work.", "**None identified.**", "Nothing outstanding.",
        "The user owes Mara: an answer."))
    assert threads(page) == ["The user owes Mara: an answer."]


def test_shared_thread_census_excludes_third_parties_skills_and_quiet(tmp_path):
    from datetime import date
    from connectonion.rem.census import open_threads
    prepare(tmp_path)
    book = Notebook(tmp_path)
    records = {
        "people/me.md": "# Aaron Xie\n",
        "people/mara.md": "# Mara\n\n## Open threads\n"
        "- The user owes Mara: reply since 2026-10-15.\n"
        "- The user asked Mara: answer since 2026-08-17.\n"  # exactly 60 days stays active
        "- Mara owes the user: deck since 2026-08-16.\n"
        "- Yu owes Ody: funds since 2026-10-15.\n"
        "- The user owes Mara: contract since 2026-08-01, due 2026-10-17.\n"
        "- The user owes Mara: old answer since 2026-08-01, due 2026-10-16.\n"
        "- No work is confirmed pending.\n",
        "orgs/fern.md": "# Fern\n\n## Open threads\n- waiting on them for terms.\n",
        "projects/atlas.md": "# Atlas\n\n## Open threads\n- Scope not settled.\n"
        "- Old scope since 2026-08-01.\n",
        "skills/catalog/demo.md": "# Demo\n\n## Open threads\n- You owe a review.\n",
        "people/held.md": "# Held\n\n## Open threads\n- You owe an answer.\n",
    }
    for record, text in records.items():
        book.write(record, text)
    write_json(state_path(tmp_path, "map.json"), {"owner": {"record": "people/me.md"}})
    found = {record: {"category": record.split('/')[0], "held": record == "people/held.md",
                      "service": False, "duplicate": False} for record in records}
    assert open_threads(tmp_path, found, as_of=date(2026, 10, 16)) == {
        "mine": 2, "theirs": 2, "other": 1, "quiet": 3, "open": 5}



def test_shared_thread_census_groups_copied_letter_of_support(tmp_path):
    from datetime import date
    from connectonion.rem.census import open_threads

    prepare(tmp_path)
    book = Notebook(tmp_path)
    quote = "I'll come back to you shortly with a draft and a couple of questions about the contribution details."
    longer = "We're preparing the letter and supporting documents now, and " + quote
    records = [("people/cc-one.md", "Copied One", "7", quote),
               ("people/cc-two.md", "Copied Two", "W5", longer),
               ("people/weiwei.md", "Weiwei Lei", "3", quote.replace("'", "’")),
               ("people/me.md", "Aaron Xie", "3", longer)]
    for record, title, n, words in records:
        sources_heading = "## sources " if n == "W5" else "## Sources"
        book.write(record, f"# {title}\n\n## Open threads\n"
                   f'- The user owes [Weiwei Lei](../people/weiwei.md): a Letter of Support draft; “{words}” [{n}].\n'
                   f"\n{sources_heading}\n- [{n}] gmail:27472b21b17e — letter; observed 2026-10-15\n")
    record = "people/cc-one.md"
    book.write(record, book.read(record).replace("\n## Sources",
               '- The user owes Copied One: the invoice; "I will send the invoice tomorrow." [7].\n'
               f'- The user owes Copied One: another draft; “{quote}” [8].\n\n## Sources')
               + "- [8] gmail:other-mail — another promise\n")
    write_json(state_path(tmp_path, "map.json"), {"owner": {"record": "people/me.md"}})
    found = {record: {"category": "people", "held": False, "service": False, "duplicate": False}
             for record, *_ in records}
    assert open_threads(tmp_path, found, as_of=date(2026, 10, 16)) == {
        "mine": 3, "theirs": 0, "other": 0, "quiet": 0, "open": 3}


def test_thread_groups_are_transitive_and_require_resolved_shared_sources():
    from connectonion.rem.census import _thread_groups

    def item(text, sources):
        return ({"path": "people/a.md", "title": "A"}, text, sources)

    items = [item('First promise “send the draft” [1].', {"1": "gmail:a"}),
             item('Second promise "send the questions" [W2].', {"W2": "gmail:b"}),
             item('Bridge “send the draft and send the questions” [3][4].', {"3": "gmail:a", "4": "gmail:b"}),
             item('First promise “send the draft” [1].', {"1": "gmail:other"}),
             item('First promise “send the draft” [99].', {}),
             item('THE USER owes a reply! [5].', {"5": "gmail:plain"}),
             item('The user owes a reply [W7]', {"W7": "gmail:plain"})]
    assert _thread_groups(items) == [items[:3], [items[3]], [items[4]], items[5:]]


def test_shared_thread_census_uses_the_named_counterparts_state(tmp_path):
    from datetime import date
    from connectonion.rem.census import open_threads

    prepare(tmp_path)
    book = Notebook(tmp_path)
    records = [("people/cc.md", "Copied One", "2026-10-15"),
               ("people/weiwei.md", "Weiwei Lei", "2026-07-01")]
    for path, title, since in records:
        book.write(path, f"# {title}\n\n## Open threads\n"
                   '- The user owes Weiwei Lei: a draft to discuss with [Copied One](../people/cc.md); '
                   f'“I will send the Letter of Support draft”; since {since} [1].\n'
                   '\n## Sources\n- [1] gmail:letter\n')
    found = {path: {"category": "people", "held": False, "service": False, "duplicate": False}
             for path, *_ in records}
    # The newer copied page cannot override the counterpart's quiet state,
    # and a later link in the description does not name the counterpart.
    assert open_threads(tmp_path, found, as_of=date(2026, 10, 16)) == {
        "mine": 0, "theirs": 0, "other": 0, "quiet": 1, "open": 0}


def test_a_thread_last_moved_recently_is_not_quiet():
    from datetime import date
    from connectonion.rem.census import _quiet
    assert not _quiet("The user owes Mara: asked 2026-07-01; last moved on 2026-10-15.", date(2026, 10, 16))
    assert _quiet("The user owes Mara: asked 2026-07-01; last moved: 2026-08-01.", date(2026, 10, 16))


def test_direction_only_treats_short_name_phrases_as_debt_prefixes():
    from connectonion.rem.census import direction

    assert direction("You said you would send what Weiwei owes the bank") != "third"
    assert direction("Mara said that Weiwei owes the bank; you promised a reply") != "third"
    assert direction("The detailed discussion about sending what Weiwei owes the bank") != "third"
    assert direction("weiwei owes the bank") == "plain"
    assert direction("Yu at Heidi Health owes Ody the reimbursement") == "third"
    assert direction("Weiwei owes you the draft") == "theirs"

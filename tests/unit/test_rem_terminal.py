"""What `co rem` prints in a terminal, after the UI audit of 2026-10-15.

The audit read the owner's notebook through the CLI: status said 84 of 84
people written while investigate said 4 people unfinished, one of them an
investigated page; the People table was 158 columns of markdown links and
Luma relays; status never said what waited on the owner; `investigate all
--list` printed "0 s" and led with 0-session projects; `list projects` printed
file paths; and the CLI said "Organizations" where the reader said
"Organisations".
"""

import json
from datetime import date, timedelta

from rich.text import Text
from typer.testing import CliRunner

from connectonion.cli.main import app
from connectonion.rem.config import prepare
from connectonion.rem.files import Notebook, state_path, write_json


def invoke(root, *args):
    return CliRunner().invoke(app, ["rem", "--root", str(root), *args])


def _stamp(notebook, record, day):
    """Mark a page investigated on `day`, its Unknowns left as they are."""
    notebook.write(record, notebook.read(record).replace("not investigated yet\n", f"investigated {day} (gmail)\n"))


# ------------------------------------------------ #3: one census for status and investigate


def _projects(root):
    """Three projects: one never written, one written long ago with Unknowns left, one written today."""
    prepare(root)
    notebook = Notebook(root)
    for slug in ("atlas", "boreal", "cirrus"):
        notebook.stub_project(f"projects/{slug}.md", slug.title(), [f"/repo/{slug}"])
    _stamp(notebook, "projects/boreal.md", "2026-01-02")
    _stamp(notebook, "projects/cirrus.md", date.today().isoformat())
    write_json(state_path(root, "map.json"), {"people": [], "orgs": [], "projects": [
        {"record": f"projects/{slug}.md", "sessions": sessions}
        for slug, sessions in (("atlas", 0), ("boreal", 2), ("cirrus", 40))]})
    return notebook


def test_investigate_counts_what_status_counts_and_not_this_weeks_pages_as_unfinished(tmp_path):
    from connectonion.cli.commands.rem_status import notebook
    _projects(tmp_path)
    result = invoke(tmp_path, "--json", "investigate")
    assert result.exit_code == 0, result.output
    projects = json.loads(result.stdout)["data"]["projects"]
    census = notebook(tmp_path)["projects"]
    assert (projects["written"], projects["mapped"]) == (census["written"], census["mapped"]) == (2, 3)
    # Boreal is written and due another pass; Cirrus was read today and is neither.
    assert projects["to_refresh"] == 1
    assert projects["next"] == ["projects/boreal.md", "projects/atlas.md"]
    text = invoke(tmp_path, "investigate").output
    assert "Unfinished" not in text and "To refresh: 1" in text and "Written: 2" in text


def test_an_investigated_person_with_new_mail_is_to_refresh_not_unwritten(tmp_path):
    prepare(tmp_path)
    notebook = Notebook(tmp_path)
    notebook.stub_person("people/ody.md", "Ody Zhou", ["ody@example.org"], email="ody@example.org")
    _stamp(notebook, "people/ody.md", (date.today() - timedelta(days=2)).isoformat())
    write_json(state_path(tmp_path, "map.json"), {"orgs": [], "projects": [], "people": [
        {"record": "people/ody.md", "address": "ody@example.org", "addresses": ["ody@example.org"],
         "mails": 274, "sent": 9, "last": date.today().isoformat(), "classification": "unassessed"}]})
    people = json.loads(invoke(tmp_path, "--json", "investigate").stdout)["data"]["people"]
    assert people["next"] == ["people/ody.md"]
    assert (people["written"], people["mapped"], people["to_refresh"]) == (1, 1, 1)


def test_status_names_only_pages_its_command_would_write(tmp_path):
    """The owner's own company is never investigated as an org: "1 page not written → investigate orgs" did nothing."""
    from connectonion.cli.commands.rem_status import next_to_write, notebook
    prepare(tmp_path)
    book = Notebook(tmp_path)
    book.stub_person("people/me.md", "Me", ["me@acme.test"], email="me@acme.test")
    book.write("people/me.md", book.read("people/me.md").replace("not investigated yet\n", "investigated 2026-10-01\n"))
    book.stub_org("orgs/acme.md", "Acme", ["acme.test"], [])
    book.stub_skill("skills/catalog/demo.md", "demo", "/s/demo/SKILL.md")
    write_json(state_path(tmp_path, "map.json"), {"owner": {"record": "people/me.md", "addresses": ["me@acme.test"]},
                                                  "people": [], "projects": [], "orgs": []})
    assert notebook(tmp_path)["orgs"] == {"mapped": 1, "written": 0}
    assert next_to_write(tmp_path, notebook(tmp_path)) == ("1 skills page not written", ["investigate", "skills"])


# ------------------------------------------------ #7: the People table


def _row(name, **fields):
    return {"record": f"people/{name.lower()}.md", "name": name, "company": "", "role": "", "phone": "",
            "emails": [], "last_contact": "2026-10-14", "mails": 3, "open_threads": 1, "written": 1, **fields}


def test_the_table_reads_as_words_fits_the_terminal_and_never_shows_a_relay(monkeypatch):
    from connectonion.cli.commands.rem_table import draw
    monkeypatch.setenv("COLUMNS", "100")
    rows = [_row("Ody Zhou", company="[OpenOnion](../orgs/openonion.md)", role="Co-founder",
                 emails=["usr-fixture0000000@user.luma-mail.com", "ody.zhou@example.com"]),
            _row("Sohum Mogale", company="[University of New South Wales](../orgs/unsw.md)",
                 role="Project owner, Group P115 of COMP3900 at UNSW", emails=["s.lee@student.unsw.edu.au"],
                 phone="0491570159 [sensitive]"),
            _row("Luma Guest", emails=["usr-abc@user.luma-mail.com"])]
    lines = Text.from_markup(draw(rows)).plain.splitlines()
    assert all(len(line) <= 100 for line in lines), lines
    assert "Status" not in lines[0] and "written" not in "\n".join(lines)   # the same on every row
    ody = next(line for line in lines if line.startswith("Ody Zhou"))
    assert "OpenOnion" in ody and "](" not in ody and "[" not in ody
    assert "ody.zhou@" in ody and "luma-mail" not in "\n".join(lines)


def test_the_table_keeps_status_when_rows_differ(monkeypatch):
    from connectonion.cli.commands.rem_table import draw
    monkeypatch.setenv("COLUMNS", "200")
    lines = Text.from_markup(draw([_row("Ody"), _row("Tam", written=0)])).plain.splitlines()
    assert "Status" in lines[0] and any(line.rstrip().endswith("mapped") for line in lines)


# ------------------------------------------------ #5: list prints names


def test_list_projects_prints_titles_with_the_path_beside_them(tmp_path):
    notebook = _projects(tmp_path)
    notebook.write("projects/atlas.md", notebook.read("projects/atlas.md").replace("# Atlas", "# Atlas Platform"))
    lines = invoke(tmp_path, "list", "projects").output.splitlines()
    atlas = next(line for line in lines if "projects/atlas.md" in line)
    assert atlas.startswith("Atlas Platform") and atlas.index("Atlas Platform") < atlas.index("projects/atlas.md")
    assert json.loads(invoke(tmp_path, "--json", "list", "projects").stdout)["data"][0].startswith("projects/")


# ------------------------------------------------ #10: what waits on you, the budget, the last run


THREADS = ("## Open threads\n- Aaron owes Ody the signed contract by 2026-10-20. [1]\n"
           "- Ody promised the deck. [2]\n- Unknown — not investigated yet\n\n")


def test_open_threads_are_counted_as_the_reader_counts_them(tmp_path):
    from connectonion.rem.census import direction, open_threads
    prepare(tmp_path)
    book = Notebook(tmp_path)
    book.stub_person("people/me.md", "Aaron Xie", ["me@example.org"], email="me@example.org")
    book.stub_person("people/ody.md", "Ody Zhou", ["ody@example.org"], email="ody@example.org")
    page = book.read("people/ody.md")
    book.write("people/ody.md", page.replace(page[page.index("## Open threads"):page.index("## ", page.index(
        "## Open threads") + 3)], THREADS))
    write_json(state_path(tmp_path, "map.json"), {"owner": {"record": "people/me.md", "addresses": []}})
    assert open_threads(tmp_path) == {"open": 2, "mine": 1}
    assert direction("The user needs to reply to Mara") == "mine"
    assert direction("None identified") == "plain"


def test_status_leads_with_what_waits_on_you_and_keeps_budget_to_two_lines(tmp_path, monkeypatch):
    from connectonion.cli.commands import rem_status
    for name in ("_notebook", "_today", "_mailboxes", "_archive"):
        monkeypatch.setattr(rem_status, name, lambda *a, **k: [])
    monkeypatch.setattr(rem_status, "_header", lambda *a: ["co rem status"])
    monkeypatch.setattr("connectonion.rem.census.open_threads", lambda root, found=None: {"open": 159, "mine": 31})
    value = {"investigation_quota": {"spent_points": 0.1, "budget_points": 35},
             "codex_week": "0% used on pro; resets Thu 22 Oct 17:24"}
    plain = Text.from_markup(rem_status.dashboard(tmp_path, value, lambda arguments: "")).plain.splitlines()
    assert plain[2] == "Waiting on you   31 of 159 open threads"
    budget = plain.index(next(line for line in plain if line.startswith("Budget")))
    assert plain[budget + 1].strip() == "Codex week 0% used on pro · resets Thu 22 Oct 17:24"
    assert plain[budget + 2] == ""
    verbose = Text.from_markup(rem_status.dashboard(tmp_path, value, lambda arguments: "", verbose=True)).plain
    assert "1% of your Codex week" in verbose


def test_the_last_run_is_the_last_one_that_finished(tmp_path, monkeypatch):
    from zoneinfo import ZoneInfo
    from connectonion.cli.commands import rem_status
    prepare(tmp_path)
    write_json(state_path(tmp_path, "runs/run_" + "a" * 32 + ".json"), {
        "id": "run_" + "a" * 32, "started_at": "2026-10-15T08:01:43+00:00", "phase": "sync",
        "outcome": "completed", "changed": ["people/ody.md"]})
    write_json(state_path(tmp_path, "runs/run_" + "b" * 32 + ".json"), {
        "id": "run_" + "b" * 32, "started_at": "2026-10-15T08:05:22+00:00", "phase": "daily-update",
        "outcome": "running", "changed": [], "host": "another-machine"})
    monkeypatch.setattr(rem_status, "_zone", lambda root: ZoneInfo("Australia/Sydney"))
    lines = Text.from_markup("\n".join(rem_status._last_runs(tmp_path))).plain.splitlines()
    assert lines[0] == "Last run         sync · completed"
    assert lines[1].strip() == "2026-10-15 19:01 · 1 page changed"
    assert lines[2].strip() == "daily-update running since 19:05"


# ------------------------------------------------ #4: investigate all --list


def test_the_list_ranks_by_evidence_and_gives_a_skill_no_unit(tmp_path):
    _projects(tmp_path)
    Notebook(tmp_path).stub_skill("skills/catalog/demo.md", "demo", "/s/demo/SKILL.md")
    result = invoke(tmp_path, "investigate", "all", "--list")
    assert result.exit_code == 0, result.output
    order = [line.strip() for line in result.output.splitlines() if line.startswith("  ")]
    assert order[0].startswith("projects/cirrus.md  (40 sessions") and order[0].endswith("skipped: this week)")
    assert order.index(next(line for line in order if line.startswith("projects/atlas.md"))) > 0
    assert "skills/catalog/demo.md  (not investigated)" in order and " s," not in result.output
    # A run still takes the pages not read this week, heaviest first.
    data = json.loads(invoke(tmp_path, "--json", "investigate", "all", "--list").stdout)["data"]["order"]
    assert [row["path"] for row in data if not row["recent"]][:2] == ["projects/boreal.md", "projects/atlas.md"]


# ------------------------------------------------ #6: one spelling


def test_the_cli_says_organisations_as_the_reader_does(tmp_path):
    from pathlib import Path
    import connectonion.cli.commands as commands
    prepare(tmp_path)
    status = invoke(tmp_path, "status").output
    assert "Organisations" in status and "Organizations" not in status
    for name in ("rem_help.md", "rem_status.py", "rem_output.py", "rem_commands.py"):
        assert "rganization" not in (Path(commands.__file__).parent / name).read_text(), name
    assert "rganization" not in CliRunner().invoke(app, ["rem", "init", "--help"]).output

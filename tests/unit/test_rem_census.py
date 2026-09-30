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
                                       "orgs": {"mapped": 0, "written": 0}, "skills": {"mapped": 1, "written": 0}}
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

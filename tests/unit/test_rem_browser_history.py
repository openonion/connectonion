"""History is a local visit index; only fetched page text becomes REM evidence."""

import json
import shutil
import sqlite3
from datetime import datetime, timedelta, timezone

import pytest
from typer.testing import CliRunner

from connectonion.cli.main import app
from connectonion.rem import runner
from connectonion.rem.config import default_config
from connectonion.rem.files import Notebook
from connectonion.useful_tools.browser_tools import chrome_cookies as chrome


@pytest.fixture
def history(tmp_path, monkeypatch):
    profile = tmp_path / "chrome" / "Default"
    profile.mkdir(parents=True)
    now = datetime.now(timezone.utc)
    epoch = datetime(1601, 1, 1, tzinfo=timezone.utc)
    with sqlite3.connect(profile / "History") as db:
        db.execute("CREATE TABLE urls (id INTEGER PRIMARY KEY, url TEXT, title TEXT)")
        db.execute("CREATE TABLE visits (id INTEGER PRIMARY KEY, url INTEGER, visit_time INTEGER)")
        db.executemany("INSERT INTO urls VALUES (?, ?, ?)", [
            (1, "https://news.example/rowan", "Rowan Vale joins a research team"),
            (2, "https://team.example/about", "Team"),
            (3, "https://github.com/fiction/lantern", "Lantern repository"),
            (4, "https://unrelated.example/", "Unrelated"),
            (5, "https://team.example.evil.test/", "Unrelated"),
        ])
        visits = [(1, 1, 1), (2, 1, 2), (3, 2, 3), (4, 3, 8 * 24),
                  (5, 4, 4), (6, 1, 31 * 24), (7, 5, 5)]
        db.executemany("INSERT INTO visits VALUES (?, ?, ?)", [
            (key, url, int((now - timedelta(hours=hours) - epoch).total_seconds() * 1_000_000))
            for key, url, hours in visits
        ])
    (profile.parent / "Local State").write_text(json.dumps({
        "profile": {"info_cache": {"Default": {"name": "Research"}}}}))
    monkeypatch.setattr(chrome, "chrome_root", lambda: profile.parent)
    monkeypatch.setattr(chrome, "is_macos", lambda: True)

    def no_browser(*args, **kwargs):
        pytest.fail("history must never contact the browser daemon")

    monkeypatch.setattr("connectonion.cli.commands.browser_commands.handle_browser", no_browser)
    return profile, now


def test_rem_browser_history_cli_counts_visits_like_copied_sqlite(history, tmp_path):
    profile, now = history
    copy = tmp_path / "direct-history"
    shutil.copyfile(profile / "History", copy)
    cutoff = int((now - timedelta(days=1) - datetime(1601, 1, 1, tzinfo=timezone.utc)).total_seconds() * 1_000_000)
    with sqlite3.connect(copy) as db:
        expected = db.execute("SELECT count(*) FROM visits WHERE visit_time >= ?", (cutoff,)).fetchone()[0]

    result = CliRunner().invoke(app, ["browser", "history", "--days", "1", "--json"])

    assert result.exit_code == 0, result.output or str(result.exception)
    rows = json.loads(result.stdout)
    assert len(rows) == expected == 5
    assert sum(row["url"] == "https://news.example/rowan" for row in rows) == 2
    assert all(datetime.fromisoformat(row["time"]).utcoffset() == timedelta(0) for row in rows)


def test_rem_task_includes_subject_history_as_uncited_leads(history, tmp_path):
    notebook = Notebook(tmp_path / "book")
    notebook.write("people/rowan.md", "# Rowan Vale\n\n## Facts\nEmail: rowan@team.example\n")
    directory = tmp_path / "task"
    directory.mkdir()

    prepared = runner.prepare(notebook, [{"role": "page", "record": "people/rowan.md"}],
                              default_config(), stage="investigate", directory=directory, native=True)

    prompt = prepared["prompt"]
    assert "Recently read" in prompt
    assert "https://news.example/rowan" in prompt
    assert "https://team.example/about" in prompt
    assert "https://unrelated.example" not in prompt
    assert "https://team.example.evil.test" not in prompt
    assert "co fetch" in prompt and "web/sources.json" in prompt
    assert "not evidence" in prompt


@pytest.mark.parametrize(("options", "expected"), [
    (["--domain", "https://TEAM.example/about"], ["https://team.example/about"]),
    (["--query", "ROWAN VALE"], ["https://news.example/rowan"] * 2),
    (["--domain", "team.example", "--query", "Rowan"], []),
    (["--query", "%"], []),
    (["--profile", "Research"], ["https://news.example/rowan"] * 2 +
     ["https://team.example/about", "https://unrelated.example/", "https://team.example.evil.test/"]),
])
def test_rem_history_filters_and_profile_names(history, options, expected):
    result = CliRunner().invoke(app, ["browser", "history", *options, "--json"])
    assert result.exit_code == 0, result.output
    assert [row["url"] for row in json.loads(result.stdout)] == expected


@pytest.mark.parametrize("options", [["--days", "0"], ["--days", "-1"], ["--days", "bad"],
                                   ["--days"], ["--unknown"]])
def test_rem_history_invalid_arguments_do_not_start_browser(history, options):
    result = CliRunner().invoke(app, ["browser", "history", *options])
    assert result.exit_code == 2
    assert "usage:" in result.output


def test_rem_history_help_is_local_and_documents_every_flag(tmp_path, monkeypatch):
    from connectonion.cli import audit
    monkeypatch.setattr(chrome, "chrome_root", lambda: pytest.fail("help must not read Chrome"))
    result = CliRunner().invoke(app, ["browser", "history", "--help"])
    assert result.exit_code == 0
    assert not audit.check("co browser history", audit.Page(0, result.stdout), {})
    for flag in ("--days", "--domain", "--query", "--profile", "--json"):
        assert flag in result.stdout
    assert "network requests" in result.stdout
    parent = CliRunner().invoke(app, ["browser", "--help"])
    assert "history" in audit.listed_commands(parent.stdout)


def test_rem_history_reads_live_wal_copy_and_removes_temporary_files(history, monkeypatch):
    from connectonion.cli.commands import browser_history
    profile, now = history
    original_connect = sqlite3.connect
    with original_connect(profile / "History") as writer:
        writer.execute("PRAGMA journal_mode=WAL")
        writer.execute("INSERT INTO urls VALUES (6, 'https://wal.example/', 'Fresh visit')")
        writer.execute("INSERT INTO visits VALUES (8, 6, ?)",
                       ((now - browser_history.EPOCH) // timedelta(microseconds=1),))
        writer.commit()
        before = {path.name: path.read_bytes() for path in profile.glob("History*")}
        copies = []

        def connect(path):
            assert path != profile / "History"
            copies.append(path)
            return original_connect(path)

        monkeypatch.setattr(browser_history.sqlite3, "connect", connect)
        visits = browser_history.read_history(profile, days=1)
        assert len(visits) == 6 and visits[0]["url"] == "https://wal.example/"
        assert before == {path.name: path.read_bytes() for path in profile.glob("History*")}
        assert copies and all(not path.parent.exists() for path in copies)


@pytest.mark.parametrize(("page", "included"), [
    ("# Local checkout\n\n## Facts\n- Repository: https://github.com/fiction/lantern\n", "github.com/fiction/lantern"),
    ("# Local checkout\n\n## Facts\n- Repository: https://github.com/fiction/lantern.git\n", "github.com/fiction/lantern"),
    ("# Local checkout\n\n## Facts\n- Repository: git@github.com:fiction/lantern.git\n", "github.com/fiction/lantern"),
    ("# Research team\n\n## Domains\n- team.example\n", "team.example/about"),
    ("# Other person\n\n## Facts\n- Email: other@gmail.com\n", ""),
])
def test_rem_history_matches_subject_domain_name_or_repo_for_thirty_days(history, page, included):
    from connectonion.rem.browser_history import recently_read
    index = recently_read(page)
    assert (included in index) if included else not index


def test_rem_history_missing_chrome_does_not_block_tasks(tmp_path, monkeypatch):
    from connectonion.rem.browser_history import recently_read
    monkeypatch.setattr(chrome, "chrome_root", lambda: tmp_path / "absent")
    assert recently_read("# Rowan Vale\n") == ""


def test_rem_history_profile_links_do_not_match_every_visit_on_shared_sites(history):
    from connectonion.rem.browser_history import recently_read
    page = "# Someone else\n\n## Facts\n- Links: https://team.example/profile/elsewhere\n"
    assert recently_read(page) == ""


def test_rem_history_index_bounds_distinct_urls_and_keeps_newest_visit(history, monkeypatch):
    from connectonion.rem import browser_history
    visits = [{"time": "2026-11-06T00:00:00+00:00", "title": "Rowan Vale", "url": f"https://news.example/{i}"}
              for i in range(60)]
    visits.append({**visits[0], "time": "2026-11-05T00:00:00+00:00"})
    monkeypatch.setattr(browser_history, "read_history", lambda *args, **kwargs: visits)
    index = browser_history.recently_read("# Rowan Vale\n")
    assert "Newest 50 of 60 matching URLs" in index
    listed = json.loads(index[index.index("[\n"):])
    assert listed == visits[:50]


def test_rem_history_discovered_page_is_fetched_cited_and_retained(history, tmp_path, monkeypatch):
    from connectonion.rem import evidence
    from connectonion.rem.reader_model import cited_context
    from connectonion.useful_tools import page_fetch

    notebook = Notebook(tmp_path / "book")
    record = "people/rowan.md"
    notebook.stub_person(record, "Rowan Vale")
    original = notebook.read(record)
    directory = tmp_path / "capture-task"
    directory.mkdir()
    task = runner.prepare(notebook, [{"role": "page", "record": record}], default_config(),
                          stage="investigate", directory=directory, native=True)
    url = "https://news.example/rowan"
    assert url in task["prompt"]
    assert evidence.research_items(directory) == []  # Visiting is not a capture.
    body = "Rowan Vale leads the research team."
    monkeypatch.setattr(page_fetch, "fetch_page", lambda requested: {
        "url": requested, "title": "Research team", "markdown": body, "redirect": "",
        "status": 200, "content_type": "text/plain"})
    fetched = CliRunner().invoke(app, ["fetch", url])
    assert fetched.exit_code == 0, fetched.output
    web = directory / "web"
    web.mkdir()
    (web / "team.md").write_text(fetched.stdout)
    date = datetime.now(timezone.utc).date().isoformat()
    (web / "sources.json").write_text(json.dumps([{"url": url, "file": "team.md", "date": date}]))
    candidate = directory / "candidate.md"
    text = original.replace("Unknown — not investigated yet", "Unknown")
    text = text.replace("## Who they are\n", f"## Who they are\n“{body}” [1]\n")
    candidate.write_text(text.replace("## Sources\n", f"## Sources\n- [1] {url} — {date}\n"))
    runner._promote_candidate(notebook, record, candidate, original, [], directory, None, native=True)
    saved = notebook.read(record)
    assert body in saved and f"- [1] {url}" in saved
    assert body in cited_context(notebook.root, [{"text": saved}])[url]["excerpt"]

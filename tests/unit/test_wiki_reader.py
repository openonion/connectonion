"""The HTML reader is disposable presentation over the notebook, never a second store."""

import os
import re

import pytest

from connectonion.wiki.config import prepare
from connectonion.wiki.files import Notebook
from connectonion.wiki.reader import open_reader, reader_path, render, write_reader

HOSTILE = "# Alice\n\nSaid: <script>alert(1)</script> and </script><img src=x onerror=alert(2)>\n"


def test_render_embeds_records_and_neutralizes_markup(tmp_path):
    prepare(tmp_path)
    Notebook(tmp_path).write("people/alice.md", HOSTILE)
    Notebook(tmp_path).write("decisions/markdown.md", "# Markdown over a database\n\nSee [Alice](../people/alice.md).")
    page = render(tmp_path)
    assert "people/alice.md" in page and "decisions/markdown.md" in page
    # Note text reaches the page only as JSON data; no raw tag from a note may appear as markup.
    assert "<script>alert(1)" not in page
    assert "<img src=x" not in page
    assert page.count("</script>") == page.count("<script")
    assert "as_of" in page


def test_render_is_self_contained_with_no_remote_assets(tmp_path):
    page = render(tmp_path)
    assert not re.search(r'(src|href)\s*=\s*["\']https?://', page)
    assert "<link" not in page  # styles are inline; a stylesheet would be a fetch
    assert "@import" not in page


def test_render_before_start_shows_not_started_and_creates_nothing(tmp_path):
    root = tmp_path / "wiki"
    page = render(root)
    assert "Not started" in page
    assert not root.exists()


def test_write_reader_lands_outside_the_notebook_and_leaves_notes_untouched(tmp_path):
    prepare(tmp_path)
    note = tmp_path / "notes" / "idea.md"
    Notebook(tmp_path).write("notes/idea.md", "# Idea\n")
    before = sorted((p.relative_to(tmp_path).as_posix(), p.stat().st_mtime_ns)
                    for p in tmp_path.rglob("*") if p.is_file())
    page = write_reader(tmp_path)
    assert page.is_file()
    assert tmp_path not in page.parents  # rendered output is not inside the collected tree
    assert oct(page.stat().st_mode & 0o777) == "0o600"
    after = sorted((p.relative_to(tmp_path).as_posix(), p.stat().st_mtime_ns)
                   for p in tmp_path.rglob("*") if p.is_file())
    assert before == after
    assert note.read_text() == "# Idea\n"
    assert Notebook(tmp_path).list() == ["notes/idea.md"]  # the page is not a record


def test_write_reader_refuses_to_follow_a_planted_symlink(tmp_path, monkeypatch):
    """The page name is predictable, so a symlink planted there must not become a write elsewhere."""
    monkeypatch.setattr("tempfile.gettempdir", lambda: str(tmp_path))
    victim = tmp_path / "victim.txt"
    victim.write_text("keep")
    os.symlink(victim, reader_path(tmp_path / "wiki"))
    with pytest.raises(OSError):
        write_reader(tmp_path / "wiki")
    assert victim.read_text() == "keep"


def test_open_reader_launches_the_file_uri_only_when_asked(tmp_path, monkeypatch):
    opened = []
    monkeypatch.setattr("webbrowser.open", lambda url, *a, **k: opened.append(url) or True)
    page = open_reader(tmp_path, launch=False)
    assert opened == []
    page = open_reader(tmp_path, launch=True)
    assert opened == [page.as_uri()]
    assert opened[0].startswith("file://")

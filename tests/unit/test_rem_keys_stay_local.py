"""Key pages never reach a model stage (#3326).

The owner imported 335 browser logins: one keys/ page each, naming the site and the account (the secret stays in
the Keychain). Translation, tagging, deepening and the page queues each pick pages by category; today none of them
picks keys/. These tests keep it that way, so a new stage can't start sending site-and-account lists to a model.
"""

from datetime import datetime, timezone

from connectonion.rem import keys
from connectonion.rem.files import Notebook

PERSON = ("# Mara Ostrowski\n\nMara runs partnerships at Fernhill Labs [1].\n\n## Facts\n- Company: Fernhill Labs [1]\n"
          "- Email: mara@example.test [1]\n\n## Our relationship\nShe asked for the pilot export [1].\n\n"
          "## Sources\n- [1] gmail:abc — 2026-11-01\n")


def _notebook(tmp_path):
    book = Notebook(tmp_path)
    book.write("people/mara-ostrowski.md", PERSON)
    for i in range(3):
        book.write(f"keys/site-{i}-example-test.md",
                   keys.page(f"site{i}.example.test", f"owner{i}@example.test", purpose="sign in", key=f"site-{i}-example-test"))
    return book


def _paths(rows):
    return [row if isinstance(row, str) else row.get("record") or row.get("path") or "" for row in rows]


def test_translation_never_queues_a_key_page(tmp_path):
    from connectonion.rem.translate import written_pages
    _notebook(tmp_path)
    assert not [p for p in written_pages(tmp_path) if p.startswith("keys/")]


def test_tagging_never_picks_a_key_page(tmp_path):
    from connectonion.rem import tag_stage, tags
    _notebook(tmp_path)
    assert "keys" not in tags.TAGGED_KINDS
    assert not [p for p in tag_stage.candidates(tmp_path) if p.startswith("keys/")]


def test_deepening_never_picks_a_key_page(tmp_path):
    from connectonion.rem import depth
    _notebook(tmp_path)
    assert not [p for p in _paths(depth.candidates(tmp_path)) if p.startswith("keys/")]


def test_tag_pages_never_draw_from_a_key_page(tmp_path):
    from connectonion.rem import tag_nodes
    _notebook(tmp_path)
    assert not [p for p in _paths(tag_nodes.candidates(tmp_path)) if p.startswith("keys/")]
    assert not [p for p in tag_nodes.pages_for_tags(tmp_path) if p.startswith("keys/")]


def test_the_people_and_project_queues_never_hold_a_key_page(tmp_path):
    from connectonion.rem import people_pages, project_pages
    _notebook(tmp_path)
    now = datetime(2026, 11, 22, tzinfo=timezone.utc)
    assert not [p for p in _paths(people_pages.queue(tmp_path, now=now)) if p.startswith("keys/")]
    assert not [p for p in _paths(project_pages.queue(tmp_path, now=now)) if p.startswith("keys/")]

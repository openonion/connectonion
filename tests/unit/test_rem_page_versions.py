"""#3105: an investigation can be undone, and a whole-page rewrite waits for the owner."""

import pytest

from connectonion.rem import page_versions
from connectonion.rem.config import prepare
from connectonion.rem.files import Notebook, RemError

BEFORE = "# Avery\n\n## Who they are\n- Avery leads design. [1]\n\n## Sources\n- [1] gmail:aaaaaaaaaaaa\n"
AFTER = BEFORE.replace("leads design.", "leads design and research.")


@pytest.fixture
def book(tmp_path):
    root = tmp_path / "rem"
    prepare(root)
    notebook = Notebook(root)
    notebook.write("people/avery.md", BEFORE)
    return notebook


def test_undo_puts_back_the_page_from_before_its_last_investigation(book):
    book.write("people/avery.md", AFTER)
    page_versions.keep_previous(book.root, "people/avery.md", BEFORE, AFTER)
    assert page_versions.can_undo(book.root, "people/avery.md")
    page_versions.undo(book.root, "people/avery.md")
    assert book.read("people/avery.md") == BEFORE
    assert not page_versions.can_undo(book.root, "people/avery.md")
    with pytest.raises(RemError, match="Nothing to undo"):
        page_versions.undo(book.root, "people/avery.md")


def test_undo_refuses_once_something_else_changed_the_page(book):
    book.write("people/avery.md", AFTER)
    page_versions.keep_previous(book.root, "people/avery.md", BEFORE, AFTER)
    book.write("people/avery.md", AFTER + "\nA later edit.\n")
    assert not page_versions.can_undo(book.root, "people/avery.md")
    with pytest.raises(RemError, match="changed since"):
        page_versions.undo(book.root, "people/avery.md")
    assert book.read("people/avery.md").endswith("A later edit.\n")


def test_a_rewrite_is_held_as_a_draft_and_the_page_is_put_back(book):
    book.write("people/avery.md", AFTER)  # what the rewrite run left on the page
    held = page_versions.hold_rewrite(book.root, "people/avery.md", BEFORE)
    assert held["changed"] is True
    assert book.read("people/avery.md") == BEFORE
    assert page_versions.waiting_rewrite(book.root, "people/avery.md")["text"] == AFTER
    page_versions.accept_rewrite(book.root, "people/avery.md")
    assert book.read("people/avery.md") == AFTER
    assert page_versions.waiting_rewrite(book.root, "people/avery.md") is None
    page_versions.undo(book.root, "people/avery.md")  # accepting is undoable too
    assert book.read("people/avery.md") == BEFORE


def test_a_rewrite_that_changed_nothing_leaves_no_draft(book):
    held = page_versions.hold_rewrite(book.root, "people/avery.md", BEFORE)
    assert held["changed"] is False
    assert page_versions.waiting_rewrite(book.root, "people/avery.md") is None


def test_a_draft_is_refused_once_the_page_moved_on_and_can_be_discarded(book):
    book.write("people/avery.md", AFTER)
    page_versions.hold_rewrite(book.root, "people/avery.md", BEFORE)
    book.write("people/avery.md", BEFORE + "\nNight update.\n")
    with pytest.raises(RemError, match="changed after the draft"):
        page_versions.accept_rewrite(book.root, "people/avery.md")
    page_versions.discard_rewrite(book.root, "people/avery.md")
    assert page_versions.waiting_rewrite(book.root, "people/avery.md") is None
    with pytest.raises(RemError, match="No rewrite draft"):
        page_versions.accept_rewrite(book.root, "people/avery.md")

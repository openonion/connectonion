"""Masked pages keep their own number, given once in the order they were first masked (#3385). Invented data only."""
import pytest

from connectonion.rem.config import prepare
from connectonion.rem.files import Notebook
from connectonion.rem.masked import number


def page(title, line="A private topic [1]."):
    return f"# {title} [personal]\n\n{line}\n\n## Sources\n- [1] gmail:fixture:aa01\n"


@pytest.fixture
def book(tmp_path):
    prepare(tmp_path)
    return Notebook(tmp_path)


def test_masked_pages_are_numbered_in_the_order_they_were_first_masked(book):
    book.write("knowledge/night-notes.md", page("Night notes"))
    book.write("knowledge/garden-diary.md", page("Garden diary"))
    assert number(book.read("knowledge/night-notes.md")) == 1
    assert number(book.read("knowledge/garden-diary.md")) == 2
    # The number sits under the title, code-owned; the title keeps its mark.
    assert book.read("knowledge/night-notes.md").startswith("# Night notes [personal]\nMasked: 1\n")


def test_a_new_masked_page_never_renumbers_the_others(book):
    book.write("knowledge/night-notes.md", page("Night notes"))
    book.write("knowledge/garden-diary.md", page("Garden diary"))
    book.write("knowledge/aaa-early.md", page("Early"))  # sorts first: an ordinal would shift both
    assert [number(book.read(f"knowledge/{n}.md")) for n in ("night-notes", "garden-diary", "aaa-early")] == [1, 2, 3]


def test_a_rewrite_keeps_its_number_even_when_the_writer_drops_the_line(book):
    book.write("knowledge/night-notes.md", page("Night notes"))
    book.write("knowledge/garden-diary.md", page("Garden diary"))
    book.write("knowledge/garden-diary.md", page("Garden diary", "Rewritten by the night [1]."))
    assert number(book.read("knowledge/garden-diary.md")) == 2
    # Writing the same words again changes nothing on disk.
    assert book.write("knowledge/garden-diary.md", page("Garden diary", "Rewritten by the night [1].")) is False


def test_a_deleted_pages_number_is_never_reused(book):
    book.write("knowledge/night-notes.md", page("Night notes"))
    book.write("knowledge/garden-diary.md", page("Garden diary"))
    book.delete("knowledge/garden-diary.md")
    book.write("knowledge/third.md", page("Third"))
    assert number(book.read("knowledge/third.md")) == 3


def test_unmasked_and_non_knowledge_pages_get_no_number(book):
    book.write("knowledge/heat-storage.md", "# Heat storage\n\nA topic [1].\n")
    book.write("people/mara.md", "# Mara [personal]\n\nA person [1].\n")
    assert number(book.read("knowledge/heat-storage.md")) is None
    assert number(book.read("people/mara.md")) is None

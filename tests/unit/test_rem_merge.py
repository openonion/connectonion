"""Pages that are probably one person, listed for the owner to merge (#2349)."""

from connectonion.rem.config import prepare
from connectonion.rem.files import Notebook
from connectonion.rem.merge import likely_pairs


def notebook(tmp_path):
    prepare(tmp_path)
    return Notebook(tmp_path)


def test_two_pages_sharing_an_address_or_naming_each_other_are_listed_never_merged(tmp_path):
    """A real 1.9.2b2 notebook: Corin had two pages on one Gmail; 子亚 and Zia Tanaka
    shared zia@openonion.ai; Fenwick's page listed the handle of linmu0507@example.com."""
    nb = notebook(tmp_path)
    nb.stub_person("people/corin.md", "Corin", ["zhouodywork@gmail.com", "zhouody@gmail.com", "Corin Marsh"],
                   email="zhouodywork@gmail.com; zhouody@gmail.com")
    nb.stub_person("people/corin-marsh.md", "Corin Marsh", ["zhouodywork@gmail.com"], email="zhouodywork@gmail.com")
    nb.stub_person("people/fenwick.md", "Kim Fenwick", ["larryleework7@gmail.com", "linmu"],
                   email="larryleework7@gmail.com")
    nb.stub_person("people/linmu.md", "linmu0507@example.com", ["linmu0507@example.com"],
                   email="linmu0507@example.com")
    nb.stub_person("people/colin.md", "Colin", ["colin@a.example"], email="colin@a.example")
    nb.stub_person("people/colin-drake.md", "Colin Drake", ["colin.drake@b.example", "Colin"], email="colin.drake@b.example")
    before = {record: nb.read(record) for record in nb.list("people")}
    pairs = {frozenset((p["kept"], p["other"])): p["why"] for p in likely_pairs(nb)}
    assert set(pairs) == {frozenset(("people/corin.md", "people/corin-marsh.md")),
                          frozenset(("people/fenwick.md", "people/linmu.md"))}
    assert "zhouodywork@gmail.com" in pairs[frozenset(("people/corin.md", "people/corin-marsh.md"))]
    assert "linmu" in pairs[frozenset(("people/fenwick.md", "people/linmu.md"))]
    assert {record: nb.read(record) for record in nb.list("people")} == before   # a first name alone pairs nothing


def test_the_page_with_more_written_is_the_one_to_keep(tmp_path):
    nb = notebook(tmp_path)
    nb.stub_person("people/zi.md", "子亚", ["zia@openonion.ai"], email="zia@openonion.ai")
    nb.write("people/zia.md", "# Zia Tanaka\n\n## Facts\n- Email: zia@openonion.ai; zia.tanaka@unsw.edu.au\n\n"
             "## History\n- Brought the ARC Hub to Aaron. [1]\n\n## Sources\n- [1] mail:x\n\n"
             "Investigation: investigated 2026-10-09\n")
    [pair] = likely_pairs(nb)
    assert (pair["kept"], pair["other"]) == ("people/zia.md", "people/zi.md")

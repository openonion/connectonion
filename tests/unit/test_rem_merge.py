"""Pages that are probably one person, listed for the owner to merge (#2349)."""

from connectonion.rem.config import prepare
from connectonion.rem.files import Notebook
from connectonion.rem.merge import likely_pairs


def notebook(tmp_path):
    prepare(tmp_path)
    return Notebook(tmp_path)


def test_two_pages_sharing_an_address_or_naming_each_other_are_listed_never_merged(tmp_path):
    """A real 1.9.2b2 notebook: Ody had two pages on one Gmail; 子明 and Ziming Gong
    shared ziming@openonion.ai; Larry's page listed the handle of liqingyong0507@gmail.com."""
    nb = notebook(tmp_path)
    nb.stub_person("people/ody.md", "Ody", ["zhouodywork@gmail.com", "zhouody@gmail.com", "Ody Zhou"],
                   email="zhouodywork@gmail.com; zhouody@gmail.com")
    nb.stub_person("people/ody-zhou.md", "Ody Zhou", ["zhouodywork@gmail.com"], email="zhouodywork@gmail.com")
    nb.stub_person("people/larry.md", "Lee Larry", ["larryleework7@gmail.com", "liqingyong"],
                   email="larryleework7@gmail.com")
    nb.stub_person("people/liqingyong.md", "liqingyong0507@gmail.com", ["liqingyong0507@gmail.com"],
                   email="liqingyong0507@gmail.com")
    nb.stub_person("people/david.md", "David", ["david@a.example"], email="david@a.example")
    nb.stub_person("people/david-burt.md", "David Burt", ["david.burt@b.example", "David"], email="david.burt@b.example")
    before = {record: nb.read(record) for record in nb.list("people")}
    pairs = {frozenset((p["kept"], p["other"])): p["why"] for p in likely_pairs(nb)}
    assert set(pairs) == {frozenset(("people/ody.md", "people/ody-zhou.md")),
                          frozenset(("people/larry.md", "people/liqingyong.md"))}
    assert "zhouodywork@gmail.com" in pairs[frozenset(("people/ody.md", "people/ody-zhou.md"))]
    assert "liqingyong" in pairs[frozenset(("people/larry.md", "people/liqingyong.md"))]
    assert {record: nb.read(record) for record in nb.list("people")} == before   # a first name alone pairs nothing


def test_the_page_with_more_written_is_the_one_to_keep(tmp_path):
    nb = notebook(tmp_path)
    nb.stub_person("people/zi.md", "子明", ["ziming@openonion.ai"], email="ziming@openonion.ai")
    nb.write("people/ziming.md", "# Ziming Gong\n\n## Facts\n- Email: ziming@openonion.ai; ziming.gong@unsw.edu.au\n\n"
             "## History\n- Brought the ARC Hub to Aaron. [1]\n\n## Sources\n- [1] mail:x\n\n"
             "Investigation: investigated 2026-10-09\n")
    [pair] = likely_pairs(nb)
    assert (pair["kept"], pair["other"]) == ("people/ziming.md", "people/zi.md")

"""Enrichment: the web fills what the sources could not, after the sources."""

import pytest

from connectonion.wiki.config import prepare
from connectonion.wiki.enrich import enrich
from connectonion.wiki.files import Notebook, WikiError


def _investigated(tmp_path):
    root = tmp_path / "wiki"; prepare(root)
    nb = Notebook(root)
    nb.stub_person("people/vern.md", "Vern Chan", ["vern"], email="vern.chan@unsw.edu.au")
    nb.note_investigation("people/vern.md", "outlook, gmail")
    return root, nb


def test_the_web_pass_refuses_a_page_the_sources_have_not_seen(tmp_path):
    root = tmp_path / "wiki"; prepare(root)
    Notebook(root).stub_person("people/vern.md", "Vern Chan", ["vern"])
    with pytest.raises(WikiError) as caught:
        enrich(root, "people/vern.md", runner=lambda *a: pytest.fail("browser run for an uninvestigated page"))
    assert "investigated" in str(caught.value)


def test_a_completed_web_pass_is_recorded_on_the_page_it_changed(tmp_path):
    root, nb = _investigated(tmp_path)

    def browser_run(root, record, timeout):
        text = nb.read(record).replace("- Phone: Unknown", "- Phone: +61 2 9385 1000 [W1]")
        nb.write(record, text)
        return {"outcome": "natural", "result": "filled the phone", "usage": {"input_tokens": 5}}

    out = enrich(root, "people/vern.md", runner=browser_run)
    page = nb.read("people/vern.md")
    assert out["changed"] and "+61 2 9385 1000" in page
    status = [l for l in page.splitlines() if l.startswith("Investigation:")][0]
    assert "investigated" in status and "enriched" in status and status.index("investigated") < status.index("enriched")


def test_a_web_pass_that_changed_nothing_leaves_the_status_line_alone(tmp_path):
    root, nb = _investigated(tmp_path)
    before = nb.read("people/vern.md")
    out = enrich(root, "people/vern.md", runner=lambda *a: {"outcome": "natural", "result": "nothing on the site"})
    assert not out["changed"] and nb.read("people/vern.md") == before


def test_a_failed_browser_run_is_an_error_not_a_silent_no_op(tmp_path):
    root, _ = _investigated(tmp_path)
    with pytest.raises(WikiError) as caught:
        enrich(root, "people/vern.md", runner=lambda *a: {"outcome": "error", "error": "co: not found"})
    assert "not found" in str(caught.value)

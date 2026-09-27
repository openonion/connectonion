"""Where a maintenance batch should start, found without a model."""

from connectonion.wiki.config import prepare
from connectonion.wiki.files import Notebook
from connectonion.wiki.leads import page_leads


def test_the_deepest_project_and_the_people_named_are_the_leads(tmp_path):
    """A real pass ran `rg` over 1,187 pages for six turns to find these, then timed out."""
    prepare(tmp_path)
    notebook = Notebook(tmp_path)
    notebook.stub_project("projects/home.md", "home", ["/Users/x"])
    notebook.stub_project("projects/connectonion.md", "connectonion", ["/Users/x/projects/connectonion"])
    notebook.stub_project("projects/other.md", "other", ["/Users/x/projects/other"])
    notebook.stub_person("people/dora.md", "Dora Chen", ["Dora"], email="dora@example.org")
    notebook.stub_person("people/ody.md", "Ody Zhou", ["欧弟"], email="ody@example.org")
    notebook.stub_person("people/al.md", "Al", [], email="al@example.org")
    items = [{"role": "extract", "project": "/Users/x/projects/connectonion/docs",
              "text": "Dora asked for the CRM export; 欧弟 reviewed it. Also: always test."}]
    leads = page_leads(notebook, items)
    assert leads[0] == "projects/connectonion.md"                 # the deepest, not the home directory
    assert "projects/home.md" not in leads and "projects/other.md" not in leads
    assert {"people/dora.md", "people/ody.md"} <= set(leads)       # by title word and by alias
    assert "people/al.md" not in leads                              # "Al" inside "always" is not Al

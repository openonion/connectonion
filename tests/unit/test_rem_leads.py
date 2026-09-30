"""Where a maintenance batch should start, found without a model."""

from connectonion.rem.config import prepare
from connectonion.rem.files import Notebook
from connectonion.rem.leads import page_leads


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


def test_a_page_already_written_from_what_points_at_it_has_nothing_new(tmp_path):
    """A page turn re-sends the page and the material, about 110k tokens, and two
    of three leads in a measured batch changed nothing (#1846). A page that has
    already read every message pointing at it -- it cites them, or `co rem
    projects write` wrote it from them -- gets no turn; one unread message and it does."""
    import json
    from connectonion.rem.files import state_path
    from connectonion.rem.leads import nothing_new
    from connectonion.rem.project_material import mark_written
    prepare(tmp_path)
    notebook = Notebook(tmp_path)
    notebook.stub_person("people/dora.md", "Dora Chen", ["Dora"], email="dora@example.org")
    notebook.write("people/dora.md", notebook.read("people/dora.md").replace(
        "- (none yet)", "- [1] codex:s1:120 — 2026-09-07"))
    notebook.stub_project("projects/tallyho.md", "tallyho", ["/w/tallyho"])
    stored = state_path(tmp_path, "projects/tallyho/messages.jsonl")
    stored.parent.mkdir(parents=True)
    stored.write_text("".join(json.dumps({"source": source, "timestamp": stamp, "tool": "codex",
                                          "cwd": "/w/tallyho", "text": "ship"}) + "\n"
                              for source, stamp in (("codex:s2:10", "2026-09-06T00:00:00+00:00"),
                                                    ("codex:s2:50", "2026-09-08T00:00:00+00:00"))))
    mark_written(tmp_path, "projects/tallyho.md", "2026-09-06T00:00:00+00:00")
    read = {"source": "codex:s1:120", "text": "Dora sent the export"}
    elsewhere = {"source": "codex:s9:5", "project": "/w/kite", "text": "the kite logo is late"}
    assert nothing_new(notebook, "people/dora.md", [read, elsewhere])      # the other message is not about her
    assert not nothing_new(notebook, "people/dora.md", [read, {"source": "codex:s1:300", "text": "Dora again"}])
    assert nothing_new(notebook, "projects/tallyho.md",
                       [{"source": "codex:s2:10", "project": "/w/tallyho/src", "text": "ship"}, elsewhere])
    assert not nothing_new(notebook, "projects/tallyho.md",
                           [{"source": "codex:s2:50", "project": "/w/tallyho", "text": "ship"}])
    assert not nothing_new(notebook, "projects/tallyho.md", [elsewhere])  # nothing points at it: not for us to skip


def test_the_owner_is_not_a_lead_and_projects_are_found_by_name(tmp_path):
    """Every session is the owner's own, so the owner's name is in all of it; a
    real batch about One and ConnectOnion was pointed at the owner's other address."""
    from connectonion.rem.files import state_path, write_json
    prepare(tmp_path)
    notebook = Notebook(tmp_path)
    notebook.stub_person("people/me.md", "Aaron Xie", ["Aaron"], email="me@example.org")
    notebook.stub_person("people/me-too.md", "Aaron", [], email="me@other.example")
    notebook.stub_project("projects/one.md", "One", ["/w/one"])
    notebook.stub_project("projects/connectonion.md", "ConnectOnion", ["/w/co"])
    write_json(state_path(tmp_path, "map.json"), {"owner": {"record": "people/me.md"},
                                                  "possible_own_addresses": [{"record": "people/me-too.md"}]})
    items = [{"role": "extract", "text": "Aaron wants the One bot in Lark; ConnectOnion needs a release. one more."}]
    leads = page_leads(notebook, items)
    assert set(leads) == {"projects/one.md", "projects/connectonion.md"}


def test_notes_route_to_the_project_they_name_and_say_which_names_have_no_page(tmp_path):
    """#1985: sessions typed in the workspace root matched no project folder, and
    ten of eleven project notes in one sync reached no page, silently."""
    from connectonion.rem.leads import named_projects, note_leads

    prepare(tmp_path)
    notebook = Notebook(tmp_path)
    notebook.stub_project("projects/connectonion.md", "connectonion", ["/Users/x/projects/connectonion"])
    notebook.stub_project("projects/chat.md", "O Chat", ["/Users/x/projects/oo-chat"])
    notes = ("## People\n- **Dora** — dora@example.org\n\n"
             "## Projects\n- **ConnectOnion** — co rem renamed from wiki\n"
             "- **oo-chat** — reader restyle\n- **Night Runner** — cron agent idea\n\n"
             "## Decisions\n- **Rename** — wiki becomes co rem\n")

    assert named_projects(notes) == ["ConnectOnion", "oo-chat", "Night Runner"]
    found, unrouted = note_leads(notebook, notes)
    assert found == ["projects/connectonion.md", "projects/chat.md"]   # by title, and by folder name
    assert unrouted == ["Night Runner"]

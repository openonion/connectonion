"""co notion (read-only) against a fake Notion (2025-09-03): reads, completeness, data sources, recovery.

LLM-Note: Tests for connectonion/cli/commands/notion_commands.py and notion_api.py. The fake
(tests/unit/notion_fake.py) answers the reads co notion makes and fails on anything else, so a
command that tried to change Notion would fail its test. Faults (429, 5xx, timeouts) are injected
per request to test recovery.
"""

import json
import re
from pathlib import Path

import httpx
import pytest
from typer.main import get_command
from typer.testing import CliRunner

from connectonion.cli.commands import notion_api as api
from connectonion.cli.main import app
from tests.unit.notion_fake import FakeNotion, para, rich, uid

ROADMAP = uid(1)
CHILD = uid(2)
TASKS_DB, TASKS = uid(10), uid(11)
LEADS_DB, LEADS_A, LEADS_B = uid(20), uid(21), uid(22)
ROW = uid(30)

TASK_COLUMNS = {
    "Name": {"id": "title", "type": "title", "title": {}},
    "Status": {"id": "st", "type": "status", "status": {"options": [{"name": "Not started"}, {"name": "In progress"},
                                                                   {"name": "Done"}]}},
    "Tags": {"id": "tg", "type": "multi_select", "multi_select": {"options": [{"name": "docs"}, {"name": "q4"},
                                                                              {"name": "urgent"}]}},
    "Done": {"id": "dn", "type": "checkbox", "checkbox": {}},
    "Due": {"id": "du", "type": "date", "date": {}},
    "Points": {"id": "pt", "type": "number", "number": {}},
    "Owner": {"id": "ow", "type": "people", "people": {}},
    "Related": {"id": "rl", "type": "relation", "relation": {"data_source_id": TASKS}},
}


def task(title, status="Not started", tags=(), done=False, due=None, points=None, related=()):
    related = list(related)
    return {"Name": {"id": "title", "type": "title", "title": rich(title)},
            "Status": {"id": "st", "type": "status", "status": {"name": status}},
            "Tags": {"id": "tg", "type": "multi_select", "multi_select": [{"name": t} for t in tags]},
            "Done": {"id": "dn", "type": "checkbox", "checkbox": done},
            "Due": {"id": "du", "type": "date", "date": {"start": due, "end": None, "time_zone": None} if due else None},
            "Points": {"id": "pt", "type": "number", "number": points},
            "Owner": {"id": "ow", "type": "people", "people": [{"object": "user", "id": "user-ann", "name": "Ann"}]},
            "Related": {"id": "rl", "type": "relation", "relation": [{"id": r} for r in related[:25]],
                        "has_more": len(related) > 25, "_all": [{"id": r} for r in related]}}


@pytest.fixture
def notion(monkeypatch):
    fake = FakeNotion()
    fake.add_page(ROADMAP, "Roadmap", blocks=[
        {"type": "heading_1", "heading_1": {"rich_text": rich("Q4")}},
        para("Ship co notion."),
        {"type": "toggle", "toggle": {"rich_text": rich("Details")}, "children": [
            para("Nested line"), {"type": "bulleted_list_item", "bulleted_list_item": {"rich_text": rich("deeper")},
                                  "children": [para("deepest")]}]},
        {"type": "to_do", "to_do": {"rich_text": rich("Write tests"), "checked": True}},
        {"type": "table", "table": {"table_width": 2}, "children": [
            {"type": "table_row", "table_row": {"cells": [rich("Owner"), rich("Ann")]}}]},
        {"type": "image", "image": {"type": "file", "caption": rich("Architecture"),
                                    "file": {"url": "https://files.notion.test/arch.png",
                                             "expiry_time": "2026-10-24T01:00:00.000Z"}}},
        {"type": "ai_block", "ai_block": {}},
        {"type": "child_page", "child_page": {"title": "Notes"}, "id": CHILD},
    ])
    fake.add_page(CHILD, "Notes", parent={"type": "page_id", "page_id": ROADMAP}, blocks=[para("child text")])
    fake.add_database(TASKS_DB, "Tasks", [(TASKS, "Tasks", TASK_COLUMNS)], parent_page=ROADMAP)
    fake.add_row(TASKS, ROW, task("Write docs", "In progress", ("docs", "q4"), points=0,
                                  related=[uid(500 + i) for i in range(30)]))
    fake.add_database(LEADS_DB, "Leads", [(LEADS_A, "Current", TASK_COLUMNS), (LEADS_B, "Archive", TASK_COLUMNS)])
    monkeypatch.setattr(api, "_http", fake.client)
    monkeypatch.setattr(api, "_sleep", lambda seconds: fake.sent.append(("SLEEP", str(seconds), {})))
    monkeypatch.setenv("NOTION_API_KEY", "ntn_test")
    monkeypatch.delenv("NOTION_VERSION", raising=False)
    return fake


def run(*args, input=None):
    return CliRunner().invoke(app, ["notion", *args], input=input)


def writes(fake):
    return [s for s in fake.sent if s[0] in ("POST", "PATCH") and s[1] != "search" and not s[1].endswith("/query")]


def last_line(text):
    return text.strip().splitlines()[-1]


# -- links -----------------------------------------------------------------

@pytest.mark.parametrize("given, expected", [
    (ROADMAP, api.Target(ROADMAP)),
    (ROADMAP.replace("-", ""), api.Target(ROADMAP)),
    ("https://www.notion.so/acme/Roadmap-" + ROADMAP.replace("-", "") + "?pvs=4", api.Target(ROADMAP)),
    # A title made of hex letters must not be read into the id.
    ("https://www.notion.so/Cafe-Deadbeef-" + ROADMAP.replace("-", ""), api.Target(ROADMAP)),
    # A block anchor keeps the page as the object.
    ("https://www.notion.so/Roadmap-" + ROADMAP.replace("-", "") + "#" + CHILD.replace("-", ""),
     api.Target(ROADMAP, block=CHILD)),
    # A view parameter keeps the database as the object.
    ("https://www.notion.so/" + TASKS_DB.replace("-", "") + "?v=" + uid(99).replace("-", ""),
     api.Target(TASKS_DB, view=uid(99))),
    # A row opened in peek view over a database: the row is the object.
    ("https://www.notion.so/" + TASKS_DB.replace("-", "") + "?v=" + uid(99).replace("-", "") + "&p="
     + ROW.replace("-", "") + "&pm=s", api.Target(ROW, view=uid(99), peek=True)),
])
def test_links_name_the_object_notion_means(given, expected):
    assert api.parse_target(given) == expected


@pytest.mark.parametrize("given", ["roadmap", "", "https://www.notion.so/settings"])
def test_text_that_names_no_object_is_refused(given):
    with pytest.raises(api.NotionError):
        api.parse_target(given)


# -- identity --------------------------------------------------------------

def test_check_pins_the_api_version_and_names_the_workspace(notion):
    result = run("check")
    assert result.exit_code == 0, result.output
    request = notion.requests[0]
    assert request.headers["authorization"] == "Bearer ntn_test"
    assert request.headers["notion-version"] == "2025-09-03"
    assert "co agent" in result.stdout and "Acme" in result.stdout and "ws-acme" in result.stdout


def test_check_target_separates_a_valid_secret_from_an_unshared_page(notion):
    shared = run("check", "--target", ROADMAP)
    assert shared.exit_code == 0 and "Target shared: page Roadmap" in shared.stdout
    database = run("check", "--target", TASKS_DB)
    assert database.exit_code == 0 and "Target shared: data source Tasks" in database.stdout
    unshared = run("check", "--target", uid(77))
    assert unshared.exit_code == 1
    assert "Connected with the NOTION_API_KEY exported in your shell" in unshared.stdout
    assert "this key cannot read it" in unshared.stderr and "Content access" in unshared.stderr


def test_not_connected_names_how_to_make_and_save_a_key(notion, monkeypatch):
    monkeypatch.delenv("NOTION_API_KEY")
    monkeypatch.setattr("connectonion.environment.setting", lambda name: None)
    result = run("check")
    assert result.exit_code == 1 and "Notion is not connected" in result.stderr
    assert "Content access" in result.stderr and "app.notion.com/developers/connections" in result.stderr
    assert "personal access token" in result.stderr
    assert last_line(result.stderr) == f"Next: {api.SET_KEY}" and not notion.sent


def test_a_rejected_key_says_so(notion):
    notion.fail("GET", "users/me", httpx.Response(401, json={"object": "error", "status": 401, "code": "unauthorized",
                                                             "message": "API token is invalid."}))
    result = run("check")
    assert result.exit_code == 1 and "Notion rejected the NOTION_API_KEY exported in your shell" in result.stderr
    assert last_line(result.stderr) == "Next: unset NOTION_API_KEY && co notion check"


def test_a_rejected_saved_key_names_how_to_replace_it(notion, monkeypatch):
    monkeypatch.delenv("NOTION_API_KEY")
    monkeypatch.setattr("connectonion.environment.setting", lambda name: "ntn_saved" if name == "NOTION_API_KEY" else None)
    notion.fail("GET", "users/me", httpx.Response(401, json={"object": "error", "status": 401, "code": "unauthorized",
                                                             "message": "API token is invalid."}))
    result = run("check")
    assert result.exit_code == 1 and "Notion rejected NOTION_API_KEY" in result.stderr
    assert last_line(result.stderr) == f"Next: {api.SET_KEY}"


# -- search ----------------------------------------------------------------

def test_search_for_databases_asks_for_data_sources_and_keeps_full_ids(notion):
    result = run("pages", "--type", "database", "--json")
    assert result.exit_code == 0, result.output
    assert notion.sent[-1][2]["filter"] == {"property": "object", "value": "data_source"}
    found = json.loads(result.stdout)
    assert {r["id"] for r in found["results"]} == {TASKS, LEADS_A, LEADS_B}
    assert all(r["type"] == "database" for r in found["results"])
    assert found["complete"] is True and "not a list of the whole workspace" in found["note"]


def test_search_pages_through_with_a_cursor(notion):
    first = run("pages", "--type", "page", "-n", "1")
    assert first.exit_code == 0 and "(more available)" in first.stdout
    cursor = re.search(r"--cursor (\S+)", last_line(first.stdout))[1]
    first_id = json.loads(run("pages", "--type", "page", "-n", "1", "--json").stdout)["results"][0]["id"]
    second = run("pages", "--type", "page", "-n", "1", "--cursor", cursor, "--json")
    assert json.loads(second.stdout)["results"][0]["id"] != first_id


def test_an_empty_search_does_not_claim_the_page_is_absent(notion):
    result = run("search", "nothing like this")
    assert "0 results" in result.stdout and "not a list of the whole workspace" in result.stdout
    assert last_line(result.stdout) == "Next: co notion check --target <the page's link>"


# -- co notion pages: everything shared, as co asana projects and co obsidian notes list ----

def test_pages_lists_everything_shared_with_one_search_and_no_query(notion):
    result = run("pages")
    assert result.exit_code == 0, result.output
    assert notion.sent[-1][:2] == ("POST", "search") and notion.sent[-1][2]["query"] == ""
    assert "Roadmap" in result.stdout and "Tasks" in result.stdout
    assert "shared items" in result.stdout and "not a list of the whole workspace" in result.stdout
    assert last_line(result.stdout).startswith("Next: co notion ")


@pytest.mark.parametrize("words", ["", "   "])
def test_an_empty_search_is_refused_and_points_at_pages(notion, words):
    """One command per job (review of #3039: notes and ls did the same thing): pages lists, search finds."""
    result = run("search", words)
    assert result.exit_code == 2 and not notion.sent
    assert "co notion pages" in result.output


def test_pages_type_narrows_to_databases(notion):
    found = json.loads(run("pages", "--type", "database", "--json").stdout)
    assert {r["type"] for r in found["results"]} == {"database"}
    assert notion.sent[-1][2]["filter"] == {"property": "object", "value": "data_source"}


def test_pages_continues_with_its_own_command(notion):
    first = run("pages", "--type", "page", "-n", "1")
    assert first.exit_code == 0 and "(more available)" in first.stdout
    assert re.match(r"Next: co notion pages --type page -n 1 --cursor \S+$", last_line(first.stdout))
    second = run(*last_line(first.stdout).split()[3:], "--json")
    assert second.exit_code == 0 and json.loads(second.stdout)["results"]


def test_pages_rejects_an_unknown_type_without_asking_notion(notion):
    result = run("pages", "--type", "folder")
    assert result.exit_code == 2 and "co notion pages --help" in result.output and not notion.sent


def test_nothing_shared_points_at_sharing_not_absence(notion, monkeypatch):
    monkeypatch.setattr(api, "search", lambda *a, **k: ([], ""))
    result = run("pages")
    assert result.exit_code == 0 and "0 shared items" in result.stdout
    assert last_line(result.stdout) == "Next: co notion check --target <the page's link>"


def test_check_points_at_pages(notion):
    assert last_line(run("check").stdout) == "Next: co notion pages"


# -- row numbers: a list is numbered, and page, db and columns take the number ------------

def test_pages_numbers_its_rows_and_hides_long_ids(notion):
    result = run("pages")
    assert result.exit_code == 0, result.output
    rows = [line for line in result.stdout.splitlines() if re.match(r"\s*\d+\. ", line)]
    assert rows and rows[0].lstrip().startswith("1. ")
    assert ROADMAP not in result.stdout and "Listing: " in result.stdout
    assert re.fullmatch(r"Next: co notion (page|columns) 1", last_line(result.stdout))


def test_ids_flag_shows_each_rows_id(notion):
    assert ROADMAP in run("pages", "--ids").stdout


def test_page_takes_a_row_number_from_the_last_list(notion):
    shown = json.loads(run("pages", "--type", "page", "--json").stdout)["results"]
    run("pages", "--type", "page")
    result = run("page", "1")
    assert result.exit_code == 0, result.output
    assert shown[0]["title"] in result.stdout
    assert ("GET", f"pages/{shown[0]['id']}") in [s[:2] for s in notion.sent]


def test_db_and_columns_take_a_database_row_number(notion):
    run("pages", "--type", "database")
    names = [line.split(None, 3)[-1] for line in run("pages", "--type", "database").stdout.splitlines()
             if re.match(r"\s*\d+\. ", line)]
    number = str(names.index("Tasks") + 1)
    assert "columns in Tasks" in run("columns", number).stdout
    listed = run("db", number)
    assert listed.exit_code == 0, listed.output
    assert "Write docs" in listed.stdout and ROW not in listed.stdout
    assert last_line(listed.stdout) == "Next: co notion page 1"
    # The rows just listed are now the last list: page 1 is the first row of Tasks.
    assert "Write docs" in run("page", "1").stdout


def test_a_listing_id_pins_rows_after_another_list(notion):
    first = run("pages", "--type", "page")
    token = re.search(r"Listing: ([0-9a-f]{32})", first.stdout)[1]
    title = json.loads(run("pages", "--type", "page", "--json").stdout)["results"][0]["title"]
    run("db", TASKS_DB)
    assert title in run("page", "1", "--listing", token).stdout


def test_a_row_number_without_a_list_is_a_usage_error(notion):
    result = run("page", "1")
    assert result.exit_code == 2 and "No recent Notion list" in result.output
    assert "Next: co notion pages" in result.output


def test_a_row_number_past_the_list_is_refused(notion):
    run("pages", "--type", "page")
    result = run("page", "99")
    assert result.exit_code == 2 and "Relist" in result.output


def test_row_numbers_belong_to_the_key_that_listed_them(notion):
    run("pages")
    notion.workspace = {**notion.workspace, "id": "another-bot"}
    result = run("page", "1")
    assert result.exit_code == 2 and "another account" in result.output


def test_json_saves_no_row_numbers(notion):
    found = json.loads(run("pages", "--json").stdout)
    assert "Listing" not in json.dumps(found)
    assert run("page", "1").exit_code == 2


def test_an_empty_list_forgets_the_old_numbers(notion, monkeypatch):
    run("pages")
    monkeypatch.setattr(api, "search", lambda *a, **k: ([], ""))
    run("pages")
    assert run("page", "1").exit_code == 2


# -- cursors: bound to the list they came from, as co gmail binds its mailbox cursors ----

def test_lists_default_to_one_full_request(notion):
    run("pages")
    assert notion.sent[-1][2]["page_size"] == 100


def test_a_cursor_continues_only_its_own_list(notion):
    first = run("pages", "--type", "page", "-n", "1")
    cursor = re.search(r"--cursor (\S+)", last_line(first.stdout))[1]
    assert "." in cursor
    assert run("pages", "--type", "page", "-n", "1", "--cursor", cursor).exit_code == 0
    other = run("pages", "--type", "page", "-n", "2", "--cursor", cursor)
    assert other.exit_code == 2 and "belongs to another list" in other.output
    assert run("search", "Road", "-n", "1", "--cursor", cursor).exit_code == 2


def test_a_bare_notion_cursor_is_refused(notion):
    result = run("pages", "--cursor", uid(999))
    assert result.exit_code == 2 and not [s for s in notion.sent if s[1] == "search"]


def test_db_cursor_is_bound_to_its_filter(notion):
    first = json.loads(run("db", TASKS_DB, "-n", "1", "--json").stdout)
    if first["next_cursor"]:
        moved = run("db", TASKS_DB, "-n", "1", "--where", "Status=Done", "--cursor", first["next_cursor"])
        assert moved.exit_code == 2


# -- page --md: a Markdown document -----------------------------------------

def test_page_md_is_a_markdown_document(notion):
    result = run("page", ROADMAP, "--md")
    assert result.exit_code == 0, result.output
    doc = result.stdout
    assert doc.startswith("---\ntitle: \"Roadmap\"\n")
    assert "\n# Roadmap\n" in doc and "\n## Q4\n" in doc
    assert "| Owner | Ann |\n| --- | --- |" in doc
    assert "![Architecture](https://files.notion.test/arch.png)" in doc
    assert f"[Notes](https://www.notion.so/{CHILD.replace('-', '')})" in doc
    assert "- [x] Write tests" in doc
    assert "*[unsupported block: ai_block]*" in doc
    assert "Next:" not in result.stdout and "Next: co notion pages" in result.stderr


def test_page_md_nests_list_children_under_their_item(notion):
    doc = run("page", ROADMAP, "--md").stdout
    assert "- Details\n\n  Nested line\n\n  - deeper\n\n    deepest" in doc


def test_page_md_keeps_bold_italic_code_and_links(notion):
    notion.set_blocks(CHILD, [{"type": "paragraph", "paragraph": {"rich_text": [
        {"type": "text", "plain_text": "bold ", "annotations": {"bold": True}},
        {"type": "text", "plain_text": "code", "annotations": {"code": True}},
        {"type": "text", "plain_text": " and ", "annotations": {}},
        {"type": "text", "plain_text": "site", "href": "https://example.test", "annotations": {"italic": True}}]}}])
    assert "**bold** `code` and [*site*](https://example.test)" in run("page", CHILD, "--md").stdout


def test_page_md_says_a_partial_read_at_the_top(notion):
    doc = run("page", ROADMAP, "--md", "--max-blocks", "2").stdout
    assert "> **Incomplete:**" in doc.split("# Roadmap", 1)[1].split("\n\n")[1]


def test_page_md_and_json_together_is_a_usage_error(notion):
    assert run("page", ROADMAP, "--md", "--json").exit_code == 2 and not notion.sent


# -- cursors: bound to the list they came from, as co gmail binds its mailbox cursors ----

def test_a_cursor_from_one_list_is_refused_on_another(notion):
    first = run("pages", "--type", "page", "-n", "1")
    cursor = re.search(r"--cursor (\S+)", last_line(first.stdout))[1]
    wrong = run("search", "Road", "--type", "page", "-n", "1", "--cursor", cursor)
    assert wrong.exit_code == 2 and "belongs to another list" in wrong.output
    other_n = run("pages", "--type", "page", "-n", "2", "--cursor", cursor)
    assert other_n.exit_code == 2
    assert run("pages", "--type", "page", "-n", "1", "--cursor", cursor).exit_code == 0


def test_lists_ask_for_one_full_request_by_default(notion):
    run("pages")
    assert notion.sent[-1][2]["page_size"] == 100


# -- --md: the page as a Markdown document ------------------------------------

def _styled(text, **notes):
    return {"type": "text", "plain_text": text, "text": {"content": text},
            "annotations": {"bold": False, "italic": False, "strikethrough": False, "code": False, **notes}}


def test_md_is_a_markdown_document_with_front_matter(notion):
    result = run("page", ROW, "--md")
    assert result.exit_code == 0, result.output
    doc = result.stdout
    assert doc.startswith("---\ntitle: \"Write docs\"\n")
    assert '  "Status": "In progress"' in doc and "\n# Write docs\n" in doc
    assert "Next:" not in result.stdout and "Next: co notion pages" in result.stderr


def test_md_keeps_headings_lists_tables_links_and_styles(notion):
    notion.set_blocks(CHILD, [
        {"type": "paragraph", "paragraph": {"rich_text": [_styled("bold", bold=True), _styled(" and "),
                                                          _styled("code ", code=True)]}},
        {"type": "table", "table": {"table_width": 2}, "children": [
            {"type": "table_row", "table_row": {"cells": [rich("A"), rich("B")]}},
            {"type": "table_row", "table_row": {"cells": [rich("1"), rich("2|3")]}}]},
        {"type": "numbered_list_item", "numbered_list_item": {"rich_text": rich("first")},
         "children": [para("inside")]},
        {"type": "child_page", "child_page": {"title": "Sub"}, "id": ROADMAP},
    ])
    doc = run("page", CHILD, "--md").stdout
    assert "**bold** and `code` " in doc
    assert "| A | B |\n| --- | --- |\n| 1 | 2\\|3 |" in doc
    assert "1. first\n\n   inside" in doc
    assert f"[Sub](https://www.notion.so/{ROADMAP.replace('-', '')})" in doc


def test_md_of_the_roadmap_renders_its_blocks(notion):
    doc = run("page", ROADMAP, "--md").stdout
    assert "## Q4" in doc and "- [x] Write tests" in doc
    assert "![Architecture](https://files.notion.test/arch.png)" in doc
    assert "*[unsupported block: ai_block]*" in doc and "expire" in doc


def test_md_says_at_the_top_when_the_read_stopped(notion):
    doc = run("page", ROADMAP, "--md", "--max-blocks", "2").stdout
    assert "> **Incomplete:**" in doc.split("# Roadmap", 1)[1].split("\n\n")[1]


def test_md_and_json_together_is_a_usage_error(notion):
    assert run("page", ROW, "--md", "--json").exit_code == 2


# -- page ------------------------------------------------------------------

def test_page_reads_nested_blocks_tables_files_and_children(notion):
    result = run("page", ROADMAP)
    assert result.exit_code == 0, result.output
    out = result.stdout
    # The content is rendered as Markdown, as co obsidian renders a note: no raw # or | marks.
    assert out.startswith(f"Roadmap  {ROADMAP}\nEdited: ") and "Created: " in out.splitlines()[1]
    assert "\nQ4\n" in out and "# Q4" not in out and "• Details" in out
    assert "   Nested line" in out and "• deeper" in out and "deepest" in out
    assert re.search(r"Owner\s+Ann", out) and "| Owner |" not in out and "• [x] Write tests" in out
    assert "[image: Architecture]\n" in out                       # named in the content, its file listed once
    assert out.count("Architecture") == 2 and "File: Architecture (image; hosted by Notion" in out
    assert "[unsupported block: ai_block]" in out and "Not rendered (shown as [unsupported block])" in out
    assert "Notes (child page)" in out and CHILD not in out
    assert re.search(r"Child page:\n\s+1\.\s+Notes", out)
    assert "; complete" in out and not any(line != line.rstrip() for line in out.splitlines())


def test_a_limit_is_reported_and_never_presented_as_the_whole_page(notion):
    result = run("page", ROADMAP, "--max-blocks", "3", "--json")
    detail = json.loads(result.stdout)
    assert detail["coverage"]["complete"] is False and detail["coverage"]["blocks"] == 3
    shallow = json.loads(run("page", ROADMAP, "--depth", "1", "--json").stdout)
    assert shallow["coverage"]["complete"] is False and "deeper than 1" in shallow["coverage"]["stopped"][0]


def test_a_page_exactly_at_the_block_limit_is_complete(notion):
    result = run("page", CHILD, "--max-blocks", "1", "--json")
    detail = json.loads(result.stdout)
    assert detail["coverage"]["blocks"] == 1
    assert detail["coverage"]["complete"] is True


def test_server_html_failure_reports_the_status_and_next_step(notion):
    notion.fail("GET", "users/me", httpx.Response(502, text="<h1>Bad Gateway</h1>", headers={"content-type": "text/html"}), times=3)
    result = run("check")
    assert result.exit_code == 1
    assert "HTTP 502" in result.stderr
    assert "Next: co notion check" in result.stderr
    assert "Bad Gateway</h1>" not in result.stderr


def test_page_json_keeps_types_ids_and_empty_values(notion):
    detail = json.loads(run("page", ROW, "--json").stdout)
    props = detail["properties"]
    assert props["Points"] == {"id": "pt", "type": "number", "value": 0, "complete": True}
    assert props["Done"]["value"] is False and props["Due"]["value"] is None
    assert props["Tags"]["value"] == ["docs", "q4"]
    assert props["Owner"]["value"] == [{"id": "user-ann", "name": "Ann", "email": None}]
    assert detail["parent"] == "data_source" and detail["parent_id"] == TASKS


def test_a_relation_past_25_is_read_in_full(notion):
    props = json.loads(run("page", ROW, "--json").stdout)["properties"]
    assert len(props["Related"]["value"]) == 30
    assert any(path == f"pages/{ROW}/properties/rl" for _, path, _ in notion.sent)


def test_a_row_page_points_at_the_rest_of_its_database(notion):
    assert last_line(run("page", ROW).stdout) == f"Next: co notion db {TASKS}"


def test_a_page_with_child_pages_points_at_the_first_one(notion):
    assert last_line(run("page", ROADMAP).stdout) == "Next: co notion page 1"
    assert "child text" in run("page", "1").stdout


# -- what a page links to: relations by title, numbered with its child pages -----------------

def _linked_row(notion):
    notion.add_page(uid(60), "Quiz 1", parent={"type": "page_id", "page_id": ROADMAP})
    notion.add_page(uid(61), "Final Exam", parent={"type": "page_id", "page_id": ROADMAP})
    notion.add_row(TASKS, uid(62), task("Calculus 1", related=[uid(60), uid(61), uid(999)]))
    return uid(62)


def test_a_relation_shows_the_linked_pages_by_title_numbered_to_open(notion):
    row = _linked_row(notion)
    out = run("page", row).stdout
    assert re.search(r"Related \(3 linked\):\n\s+1\.\s+Quiz 1\n\s+2\.\s+Final Exam", out)
    assert "1 more not shown" in out and uid(60) not in out
    assert last_line(out) == "Next: co notion page 1"
    assert "Final Exam" in run("page", "2").stdout.splitlines()[0]


def test_page_json_names_the_linked_pages_and_keeps_every_id(notion):
    row = _linked_row(notion)
    detail = json.loads(run("page", row, "--json").stdout)
    assert detail["linked"]["Related"] == [{"id": uid(60), "title": "Quiz 1"}, {"id": uid(61), "title": "Final Exam"}]
    assert detail["properties"]["Related"]["value"] == [uid(60), uid(61), uid(999)]


def test_a_relation_no_page_of_which_is_readable_is_counted_not_guessed(notion):
    out = run("page", ROW).stdout
    assert "Related (30 linked): none this key can read" in out


def test_db_rows_show_a_relation_as_its_count(notion):
    row = _linked_row(notion)
    out = run("db", TASKS_DB).stdout
    assert "Related: 3 linked" in out and uid(60) not in out


def test_titles_are_read_for_at_most_25_linked_pages(notion, monkeypatch):
    from connectonion.cli.commands import notion_commands
    monkeypatch.setattr(notion_commands, "LINKED_TITLES", 1)
    row = _linked_row(notion)
    run("page", row)
    reads = [path for method, path, _ in notion.sent if method == "GET" and path in (f"pages/{uid(60)}", f"pages/{uid(61)}")]
    assert reads == [f"pages/{uid(60)}"]


# -- data sources ----------------------------------------------------------

def test_columns_come_from_the_data_source(notion):
    result = run("columns", TASKS_DB, "--json")
    assert result.exit_code == 0, result.output
    found = json.loads(result.stdout)
    assert found["data_source"]["id"] == TASKS and found["data_source"]["database_id"] == TASKS_DB
    by_name = {c["name"]: c for c in found["columns"]}
    assert by_name["Status"]["options"] == ["Not started", "In progress", "Done"] and by_name["Status"]["id"] == "st"
    assert "settable" not in by_name["Owner"]          # nothing is written, so nothing is marked writable


def test_columns_points_at_a_filter_the_database_takes(notion):
    assert last_line(run("columns", TASKS_DB).stdout) == f'Next: co notion db {TASKS} --where "Status=Not started"'


def test_a_database_with_several_data_sources_is_never_guessed(notion):
    result = run("columns", LEADS_DB)
    assert result.exit_code == 1
    assert f"Current ({LEADS_A})" in result.stderr and f"Archive ({LEADS_B})" in result.stderr
    assert "--source" in result.stderr
    picked = json.loads(run("columns", LEADS_DB, "--source", "archive", "--json").stdout)
    assert picked["data_source"]["id"] == LEADS_B


def test_a_data_source_id_works_where_a_database_link_does(notion):
    assert json.loads(run("columns", TASKS, "--json").stdout)["data_source"]["id"] == TASKS


def test_db_filters_and_sorts_by_the_real_schema(notion):
    notion.add_row(TASKS, uid(31), task("Plan Q1", "Done", ("q4",), due="2026-11-01"))
    result = run("db", TASKS_DB, "--where", "status=done", "--where", "Tags~q4", "--sort", "-Due", "--json")
    assert result.exit_code == 0, result.output
    method, path, body = notion.sent[-1]
    assert path == f"data_sources/{TASKS}/query"
    assert body["filter"] == {"and": [{"property": "Status", "status": {"equals": "Done"}},
                                      {"property": "Tags", "multi_select": {"contains": "q4"}}]}
    assert body["sorts"] == [{"property": "Due", "direction": "descending"}]
    rows = json.loads(result.stdout)["rows"]
    assert [r["title"] for r in rows] == ["Plan Q1"]


@pytest.mark.parametrize("clause, says", [
    ("Priority=high", "No column 'Priority'"),
    ("Status=Blocked", "No Status option 'Blocked'"),
    ("Status>Done", "does not take >"),
    ("Owner=ann", "cannot filter on it"),
    ("edited>yesterday", "takes = > < >= <= and a date"),
])
def test_db_checks_filters_before_querying(notion, clause, says):
    result = run("db", TASKS_DB, "--where", clause)
    assert result.exit_code == 1 and says in result.stderr
    assert not any(path.endswith("/query") for _, path, _ in notion.sent)


def test_db_pages_through_with_a_cursor(notion):
    for i in range(3):
        notion.add_row(TASKS, uid(40 + i), task(f"Row {i}"))
    first = run("db", TASKS_DB, "-n", "2")
    assert "(more available)" in first.stdout and "--cursor" in last_line(first.stdout)
    cursor = re.search(r"--cursor (\S+)", last_line(first.stdout))[1]
    rest = json.loads(run("db", TASKS_DB, "-n", "2", "--cursor", cursor, "--json").stdout)
    assert len(rest["rows"]) == 2 and rest["complete"] is True


def test_a_read_waits_out_a_rate_limit_then_succeeds(notion):
    notion.fail("GET", f"pages/{ROADMAP}", httpx.Response(429, headers={"retry-after": "3"},
                                                          json={"object": "error", "status": 429,
                                                                "code": "rate_limited", "message": "slow down"}))
    result = run("page", ROADMAP)
    assert result.exit_code == 0, result.output
    assert ("SLEEP", "3.0", {}) in notion.sent


def test_a_rate_limit_that_persists_is_reported_not_looped(notion):
    notion.fail("GET", "users/me", httpx.Response(429, json={"object": "error", "status": 429, "code": "rate_limited",
                                                             "message": "slow"}), times=10)
    result = run("check")
    assert result.exit_code == 1 and "rate limiting" in result.stderr
    assert len([s for s in notion.sent if s[1] == "users/me"]) == api.READ_ATTEMPTS


# -- contracts -------------------------------------------------------------

def test_every_command_the_skill_names_exists():
    leaves = set(get_command(app).commands["notion"].commands)
    skill = (Path(__file__).resolve().parents[2] / "connectonion/useful_skills/co-notion/SKILL.md").read_text()
    named = set(re.findall(r"co notion ([a-z]+)", skill))
    assert named and named <= leaves


def test_f05_links_in_content_are_shown_with_their_targets(notion):
    notion.set_blocks(CHILD, [{"type": "paragraph", "paragraph": {"rich_text": [
        {"type": "text", "plain_text": "See ", "text": {"content": "See "}},
        {"type": "text", "plain_text": "the spec", "href": "https://spec.test/v1",
         "text": {"content": "the spec", "link": {"url": "https://spec.test/v1"}}},
        {"type": "text", "plain_text": "!", "href": "javascript:alert(1)", "text": {"content": "!"}}]}}])
    assert "See the spec (https://spec.test/v1)!" in run("page", CHILD).stdout      # rendered, target kept
    assert "See [the spec](https://spec.test/v1)!" in run("page", CHILD, "--md").stdout


def test_restricted_resource_is_a_missing_capability_not_an_unshared_page(notion):
    notion.fail("GET", f"pages/{ROADMAP}", httpx.Response(403, json={
        "object": "error", "status": 403, "code": "restricted_resource", "message": "Insufficient permissions"}))
    result = run("page", ROADMAP)
    assert result.exit_code == 1 and "lacks the capability" in result.stderr
    assert "this key cannot read it" not in result.stderr


def test_db_reports_notions_result_limit_instead_of_claiming_complete(notion):
    notion.query_cap = 3
    for i in range(5):
        notion.add_row(TASKS, uid(600 + i), task(f"Capped {i}"), edited=f"2026-10-0{i + 1}T00:00:00.000Z")
    found = json.loads(run("db", TASKS_DB, "-n", "100", "--json").stdout)
    assert found["capped"] is True and found["complete"] is False and found["next_cursor"] is None
    text = run("db", TASKS_DB, "-n", "100")
    assert "Notion stopped this query at 10,000 results" in text.stdout
    assert '--where "edited>' in last_line(text.stdout)


def test_db_keeps_the_cursor_when_notion_marks_the_first_page_incomplete(notion):
    """The mark may come before the last page: the next page is still offered, and nothing says complete."""
    notion.query_cap = 3
    notion.cap_marks_every_page = True
    for i in range(5):
        notion.add_row(TASKS, uid(600 + i), task(f"Capped {i}"), edited=f"2026-10-0{i + 1}T00:00:00.000Z")
    found = json.loads(run("db", TASKS_DB, "-n", "2", "--json").stdout)
    assert found["capped"] is True and found["complete"] is False and found["next_cursor"]
    assert "--cursor" in last_line(run("db", TASKS_DB, "-n", "2").stdout)


# -- read-only, by construction ----------------------------------------------

def test_co_notion_has_only_read_commands():
    assert set(get_command(app).commands["notion"].commands) == {"check", "pages", "search", "page", "db", "columns"}


def test_every_request_a_command_makes_is_a_read(notion):
    """GET, or the two POSTs Notion uses for reading: search and a data source query."""
    for args in (["check", "--target", ROADMAP], ["pages"], ["search", "road"], ["page", ROADMAP],
                 ["db", TASKS_DB, "--where", "Status=Done"], ["columns", TASKS_DB]):
        assert run(*args).exit_code == 0, args
    assert notion.sent
    assert all(method == "GET" or (method == "POST" and (path == "search" or path.endswith("/query")))
               for method, path, _ in notion.sent if method != "SLEEP")


def test_a_database_command_given_a_page_says_so_and_points_at_the_databases(notion):
    run("db", TASKS_DB)                     # the last list is now the rows of Tasks
    result = run("columns", "1")            # row 1 is a page, not a database
    assert result.exit_code == 1
    assert "Write docs is a page (a row of a database), not a database" in result.stderr
    assert last_line(result.stderr) == "Next: co notion pages --type database"


def test_a_page_shows_its_properties_under_a_heading_and_its_times_labelled(notion):
    out = run("page", ROW).stdout
    assert out.splitlines()[1].startswith("Edited: ") and "Created: " in out.splitlines()[1]
    assert "\nProperties\n  Status: In progress\n" in out and "No content." in out


def test_a_title_with_line_breaks_is_shown_on_one_line_and_kept_whole_in_json(notion):
    two_lines = "Why Do Humans Need Sleep?\nSleep is one of the most important processes."
    notion.add_page(uid(80), two_lines, parent={"type": "page_id", "page_id": ROADMAP},
                    edited="2026-11-24T00:00:00.000Z")
    one_line = "Why Do Humans Need Sleep? Sleep is one of the most important processes."
    listed = run("pages", "--type", "page").stdout
    assert re.search(r"\n\s*1\.\s+page\s+2026-11-24\s+" + re.escape(one_line) + "\n", listed)
    assert "\nSleep is one" not in listed
    shown = run("page", uid(80)).stdout
    assert shown.splitlines()[0] == f"{one_line}  {uid(80)}"
    doc = run("page", uid(80), "--md").stdout
    assert f"\n# {one_line}\n" in doc and 'title: "Why Do Humans Need Sleep?\\nSleep' in doc
    assert json.loads(run("page", uid(80), "--json").stdout)["title"] == two_lines

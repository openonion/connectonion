"""`co onenote changes` and `co onenote show`: the REM CLI JSON source contract (DD-081).

REM calls these two commands and keeps nothing but a cursor, so they must work
from a plain shell with scope on the command line (--section), read only what
that scope allows, and never print a partial result as if it were complete.
These tests stand in for Microsoft Graph; no account is used.
"""

import json
import re
from unittest.mock import MagicMock

import pytest
from typer.testing import CliRunner

from connectonion.cli.main import app
from connectonion.useful_tools import onenote

RUNNER = CliRunner()
GRAPH = "https://graph.microsoft.com/v1.0"
LINK = "https://onedrive.live.com/redir.aspx?cid=abc&page=edit&resid=ABC!1"
NOTEBOOKS = {"value": [{"id": "nb1", "displayName": "COMP3900",
                        "sections": [{"id": "s1", "displayName": "Lab notes"},
                                     {"id": "s2", "displayName": "Readings"}]}]}


def page(page_id, modified, title="Week", link=LINK, section="s1"):
    return {"id": page_id, "title": title, "lastModifiedDateTime": modified,
            "createdDateTime": "2026-11-01T00:00:00Z",
            "links": {"oneNoteWebUrl": {"href": link}},
            "parentSection": {"id": section}, "parentNotebook": {"id": "nb1"}}


NEWEST_FIRST = [page("p3", "2026-11-25T09:00:00.123Z", "Retro"),
                page("p2", "2026-11-22T10:00:00Z", "Planning"),
                page("p1", "2026-11-10T08:00:00Z", "Kickoff")]


@pytest.fixture(autouse=True)
def credentials(monkeypatch):
    monkeypatch.setenv("MICROSOFT_SCOPES", "Mail.ReadWrite,Notes.ReadWrite")
    monkeypatch.setenv("MICROSOFT_ACCESS_TOKEN", "token")
    from connectonion.useful_tools.outlook import Outlook
    monkeypatch.setattr(Outlook, "_refresh_via_backend", lambda self, rt: "fresh")
    monkeypatch.setattr("connectonion.useful_tools.outlook.time.sleep", lambda seconds: None)


@pytest.fixture
def graph(monkeypatch):
    """Route httpx.request by URL path: {path: body or (status, body)}. Returns the list of requested URLs."""
    calls = []

    def install(routes):
        def request(method, url, headers=None, **kwargs):
            calls.append(url)
            path = url.split("?")[0][len(GRAPH):]
            if path not in routes:
                raise AssertionError(f"unexpected {method} {url}")
            answer = routes[path]
            answer = answer(url) if callable(answer) else answer
            status, body = answer if isinstance(answer, tuple) else (200, answer)
            response = MagicMock(status_code=status, headers={})
            if isinstance(body, str):
                response.text, response.json = body, MagicMock(side_effect=ValueError)
            else:
                response.text, response.json = json.dumps(body), MagicMock(return_value=body)
            return response
        monkeypatch.setattr("httpx.request", request)
        return calls
    return install


def changes(*extra):
    return RUNNER.invoke(app, ["onenote", "changes", "--since", "2026-11-20T00:00:00Z",
                               "--section", "s1", "--json", *extra])


def plain(text):
    return re.sub(r"\x1b\[[0-9;]*m", "", text)


def test_both_commands_are_listed_with_an_example_and_need_no_sign_in(graph):
    calls = graph({})
    group = plain(RUNNER.invoke(app, ["onenote", "--help"]).output)
    assert "changes" in group and "show" in group
    for command in ("changes", "show"):
        shown = RUNNER.invoke(app, ["onenote", command, "--help"])
        assert shown.exit_code == 0
        assert "Example:" in plain(shown.output) and "--section" in plain(shown.output)
    assert calls == []


def test_changes_lists_only_newer_pages_oldest_first_without_reading_content(graph):
    calls = graph({"/me/onenote/notebooks": NOTEBOOKS,
                   "/me/onenote/sections/s1/pages": {"value": NEWEST_FIRST}})
    result = changes()
    assert result.exit_code == 0, result.output
    body = json.loads(result.stdout)
    assert body["since"] == "2026-11-20T00:00:00Z" and body["until"] > body["since"]
    assert body["items"] == [
        {"id": "p2", "version": "2026-11-22T10:00:00Z", "time": "2026-11-22T10:00:00Z",
         "title": "Planning", "link": LINK},
        {"id": "p3", "version": "2026-11-25T09:00:00.123Z", "time": "2026-11-25T09:00:00.123Z",
         "title": "Retro", "link": LINK},
    ]
    assert not any("/content" in url for url in calls)
    assert "Next:" in plain(result.stderr) and "co onenote show p2 --section s1" in plain(result.stderr)


def test_changes_stops_at_the_first_unchanged_page_instead_of_paging_the_whole_section(graph):
    calls = graph({"/me/onenote/notebooks": NOTEBOOKS,
                   "/me/onenote/sections/s1/pages": {"value": NEWEST_FIRST,
                                                     "@odata.nextLink": f"{GRAPH}/me/onenote/sections/s1/pages?$skip=100"}})
    assert changes().exit_code == 0
    assert sum("/sections/s1/pages" in url for url in calls) == 1


def test_changes_follows_graph_paging_while_pages_are_still_newer(graph):
    def pages(url):
        if "$skip=2" in url:
            return {"value": NEWEST_FIRST[2:]}
        return {"value": NEWEST_FIRST[:2], "@odata.nextLink": f"{GRAPH}/me/onenote/sections/s1/pages?$skip=2"}
    graph({"/me/onenote/notebooks": NOTEBOOKS, "/me/onenote/sections/s1/pages": pages})
    result = changes()
    assert [item["id"] for item in json.loads(result.stdout)["items"]] == ["p2", "p3"]


def test_a_next_link_off_microsoft_graph_fails_without_partial_json(graph):
    graph({"/me/onenote/notebooks": NOTEBOOKS,
           "/me/onenote/sections/s1/pages": {"value": NEWEST_FIRST[:1],
                                             "@odata.nextLink": "https://example.com/steal?$skip=1"}})
    result = changes()
    assert result.exit_code == 1 and result.stdout == ""
    assert "outside Microsoft Graph" in plain(result.stderr)


def test_no_changes_is_an_empty_success_whose_next_step_is_the_new_cursor(graph):
    graph({"/me/onenote/notebooks": NOTEBOOKS,
           "/me/onenote/sections/s1/pages": {"value": NEWEST_FIRST[2:]}})
    result = changes()
    body = json.loads(result.stdout)
    assert result.exit_code == 0 and body["items"] == []
    assert f"co onenote changes --since {body['until']} --section s1" in plain(result.stderr)


@pytest.mark.parametrize("since", ["2026-11-20", "2026-11-20T00:00:00", "yesterday"])
def test_since_without_a_time_and_timezone_is_refused_before_any_request(graph, since):
    calls = graph({})
    result = RUNNER.invoke(app, ["onenote", "changes", "--since", since, "--section", "s1", "--json"])
    assert result.exit_code == 2 and result.stdout == "" and calls == []
    assert "timezone" in plain(result.stderr)


def test_a_section_not_in_this_account_is_refused_before_listing_pages(graph):
    calls = graph({"/me/onenote/notebooks": NOTEBOOKS})
    result = RUNNER.invoke(app, ["onenote", "changes", "--since", "2026-11-20T00:00:00Z",
                                 "--section", "elsewhere", "--json"])
    assert result.exit_code == 1 and result.stdout == ""
    assert not any("/pages" in url for url in calls)
    assert "co onenote ls --ids" in plain(result.stderr)


def test_too_many_changes_is_refused_rather_than_truncated(graph, monkeypatch):
    monkeypatch.setattr(onenote, "MAX_CHANGES", 1)
    graph({"/me/onenote/notebooks": NOTEBOOKS,
           "/me/onenote/sections/s1/pages": {"value": NEWEST_FIRST}})
    result = changes()
    assert result.exit_code == 1 and result.stdout == ""
    assert "more recent --since" in plain(result.stderr)


def test_a_rate_limit_that_does_not_clear_fails_the_read(graph):
    graph({"/me/onenote/notebooks": NOTEBOOKS,
           "/me/onenote/sections/s1/pages": (429, {"error": {"code": "20166"}})})
    result = changes()
    assert result.exit_code == 1 and result.stdout == ""


def test_without_a_onenote_scope_it_names_the_sign_in_and_sends_nothing(graph, monkeypatch):
    monkeypatch.setenv("MICROSOFT_SCOPES", "Mail.ReadWrite")
    calls = graph({})
    result = changes()
    assert result.exit_code == 1 and result.stdout == "" and calls == []
    assert "co auth microsoft" in plain(result.stderr)


def test_an_expired_sign_in_fails_with_the_sign_in_command(graph, monkeypatch):
    monkeypatch.setenv("MICROSOFT_SCOPES", "Notes.ReadWrite.All")
    graph({"/me/onenote/notebooks": (401, {"error": {"code": "40001"}})})
    result = changes()
    assert result.exit_code == 1 and result.stdout == ""
    assert "co auth microsoft" in plain(result.stderr)


CONTENT = ("<html><head><title>Planning</title></head><body><h1>Planning</h1>"
           "<p>Ship the demo on Friday.</p><p>key sk-ant-abcdefghijklmnopqrstuvwxyz</p></body></html>")


def test_show_returns_the_page_text_version_and_link(graph):
    graph({"/me/onenote/notebooks": NOTEBOOKS,
           "/me/onenote/pages/p2": page("p2", "2026-11-22T10:00:00Z", "Planning"),
           "/me/onenote/pages/p2/content": CONTENT.replace("<p>key sk-ant-abcdefghijklmnopqrstuvwxyz</p>", "")})
    result = RUNNER.invoke(app, ["onenote", "show", "onenote:p2", "--section", "s1", "--json"])
    assert result.exit_code == 0, result.output
    body = json.loads(result.stdout)
    assert body["id"] == "p2" and body["version"] == body["time"] == "2026-11-22T10:00:00Z"
    assert body["text"] == "Planning\nShip the demo on Friday."
    assert body["author"] is None and body["link"] == LINK and body["section_id"] == "s1"


def test_show_withholds_credential_shaped_text(graph):
    graph({"/me/onenote/pages/p2": page("p2", "2026-11-22T10:00:00Z"),
           "/me/onenote/pages/p2/content": CONTENT})
    body = json.loads(RUNNER.invoke(app, ["onenote", "show", "p2", "--json"]).stdout)
    assert "sk-ant-" not in body["text"] and body["text"] == "[withheld: possible credential]"


def test_show_refuses_a_page_filed_outside_the_given_section_without_reading_it(graph):
    calls = graph({"/me/onenote/notebooks": NOTEBOOKS,
                   "/me/onenote/pages/p9": page("p9", "2026-11-22T10:00:00Z", section="s2")})
    result = RUNNER.invoke(app, ["onenote", "show", "p9", "--section", "s1", "--json"])
    assert result.exit_code == 1 and result.stdout == ""
    assert "outside section s1" in plain(result.stderr)
    assert not any(url.endswith("/content") for url in calls)


def test_show_of_a_missing_page_is_not_found(graph):
    graph({"/me/onenote/pages/gone": (404, {"error": {"code": "20102"}})})
    result = RUNNER.invoke(app, ["onenote", "show", "gone", "--json"])
    assert result.exit_code == 1 and result.stdout == ""
    assert "No OneNote page gone" in plain(result.stderr)


@pytest.mark.parametrize("page_id", ["../me", "p2?x=1", "p 2", ""])
def test_show_refuses_an_id_that_is_not_one_graph_token_before_any_request(graph, page_id):
    calls = graph({})
    result = RUNNER.invoke(app, ["onenote", "show", page_id, "--json"])
    assert result.exit_code == 2 and result.stdout == "" and calls == []


@pytest.mark.parametrize("link", ["http://onedrive.live.com/x", "https://evil.example/x",
                                  "https://onedrive.live.com/x?authkey=abc", "https://user:pw@onenote.com/x",
                                  "https://onenote.com:8443/x"])
def test_an_unsafe_link_is_dropped_not_returned(link):
    assert onenote.clean_link(page("p1", "2026-11-22T10:00:00Z", link=link)) is None


def test_the_human_listing_names_each_page_and_one_next_step(graph):
    graph({"/me/onenote/notebooks": NOTEBOOKS,
           "/me/onenote/sections/s1/pages": {"value": NEWEST_FIRST}})
    result = RUNNER.invoke(app, ["onenote", "changes", "--since", "2026-11-20T00:00:00Z", "--section", "Lab notes"])
    shown = plain(result.output)
    assert result.exit_code == 0 and "Planning" in shown and "Retro" in shown and "Kickoff" not in shown
    assert "co onenote show p2 --section 'Lab notes'" in shown

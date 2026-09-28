"""OneNote notebooks for agents and the terminal (#1887).

A student wanted a backend on their OneNote notebooks, and `co auth microsoft`
could not grant it. The tool shares Outlook's credentials, refresh and throttling
retries; these tests stand in for Microsoft Graph.
"""

import os
import re
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import httpx
import pytest

from connectonion.useful_tools.onenote import OneNote

SCOPES = "Mail.ReadWrite,Notes.ReadWrite.All"


@pytest.fixture(autouse=True)
def credentials(monkeypatch):
    monkeypatch.setenv("MICROSOFT_SCOPES", SCOPES)
    monkeypatch.setenv("MICROSOFT_ACCESS_TOKEN", "token")
    from connectonion.useful_tools.outlook import Outlook
    monkeypatch.setattr(Outlook, "_refresh_via_backend", lambda self, rt: "fresh")


def _graph(routes):
    """httpx.request stand-in: {(METHOD, path suffix): (status, json-or-text)}; records calls."""
    calls = []

    def request(method, url, headers=None, **kwargs):
        calls.append((method, url, headers, kwargs))
        for (m, suffix), (status, body) in routes.items():
            if m == method and url.split("?")[0].endswith(suffix):
                response = MagicMock(status_code=status, headers={})
                if isinstance(body, str):
                    response.text, response.json = body, MagicMock(side_effect=ValueError)
                else:
                    response.text, response.json = "x", MagicMock(return_value=body)
                return response
        raise AssertionError(f"unexpected {method} {url}")
    return request, calls


NOTEBOOKS = {"value": [{"id": "nb1", "displayName": "COMP3900",
                        "sections": [{"id": "s1", "displayName": "Lab notes"},
                                     {"id": "s2", "displayName": "Readings"}]},
                       {"id": "nb2", "displayName": "Personal",
                        "sections": [{"id": "s3", "displayName": "Lab notes"}]}]}


def test_without_the_notes_scope_it_names_the_command():
    with patch.dict(os.environ, {"MICROSOFT_SCOPES": "Mail.ReadWrite,Mail.Send"}):
        with pytest.raises(ValueError, match="Notes.ReadWrite") as refused:
            OneNote()
    assert "co auth microsoft" in str(refused.value)



class TestPersonalMicrosoftAccounts:
    """#1910: outlook.com accepts Notes.ReadWrite only; .All is work or school."""

    def test_notes_readwrite_alone_is_enough(self):
        request, _ = _graph({("GET", "/me/onenote/notebooks"): (200, NOTEBOOKS)})
        with patch.dict(os.environ, {"MICROSOFT_SCOPES": "Mail.ReadWrite,Notes.ReadWrite"}), \
                patch("connectonion.useful_tools.outlook.httpx.request", request):
            assert "COMP3900" in OneNote().list_notebooks()

    def test_a_401_with_only_the_work_scope_says_why_not_expired(self):
        request, _ = _graph({("GET", "/me/onenote/notebooks"): (401, {"error": {"code": "40001"}})})
        with patch("connectonion.useful_tools.outlook.httpx.request", request):
            with pytest.raises(ValueError) as refused:
                OneNote().list_notebooks()
        message = str(refused.value)
        assert "personal Microsoft account" in message and "Notes.ReadWrite" in message
        assert "co auth microsoft" in message and "expired" not in message

    def test_a_401_on_page_content_says_the_same(self):
        request, _ = _graph({("GET", "/me/onenote/pages/p1/content"): (401, "")})
        with patch("connectonion.useful_tools.onenote.httpx.request", request):
            with pytest.raises(ValueError, match="personal Microsoft account"):
                OneNote().read_page("p1")


def test_notebooks_are_listed_with_their_sections_and_ids():
    request, _ = _graph({("GET", "/me/onenote/notebooks"): (200, NOTEBOOKS)})
    with patch("connectonion.useful_tools.onenote.httpx.request", request), \
            patch("connectonion.useful_tools.outlook.httpx.request", request):
        text = OneNote().list_notebooks()
    assert "COMP3900" in text and "Lab notes" in text and "s1" in text and "Personal" in text


def test_a_section_name_used_twice_is_refused_with_every_match():
    request, _ = _graph({("GET", "/me/onenote/notebooks"): (200, NOTEBOOKS)})
    with patch("connectonion.useful_tools.outlook.httpx.request", request):
        with pytest.raises(ValueError) as refused:
            OneNote().list_pages("Lab notes")
    message = str(refused.value)
    assert "Several sections are named 'Lab notes'" in message and "s1" in message and "s3" in message


def test_a_page_is_read_as_text():
    html = ("<html><head><title>Week 5</title></head><body><h1>Results</h1><p>Accuracy 91%.</p>"
            "<img src='x' alt='chart'/><p>Next: tune&nbsp;it</p></body></html>")
    request, _ = _graph({("GET", "/me/onenote/pages/p1/content"): (200, html)})
    with patch("connectonion.useful_tools.onenote.httpx.request", request):
        text = OneNote().read_page("p1")
    assert "Week 5" in text and "Results" in text and "Accuracy 91%." in text
    assert "[image: chart]" in text and "Next: tune it" in text
    assert "<p>" not in text


def test_recent_pages_need_no_section_and_keep_copyable_page_ids():
    pages = {"value": [{"id": "0-A!42", "title": "Today's plan",
                        "lastModifiedDateTime": "2026-09-28T02:00:00Z"}]}
    request, calls = _graph({("GET", "/me/onenote/pages"): (200, pages)})
    with patch("connectonion.useful_tools.outlook.httpx.request", request):
        result = OneNote().list_recent_pages()
    assert "Today's plan" in result and "0-A!42" in result
    assert "/me/onenote/pages?$top=20" in calls[0][1]
    assert calls[0][3]["timeout"] >= 30


def test_read_by_exact_title_escapes_apostrophes_and_detects_duplicates():
    title = "Aaron's plan"
    request, calls = _graph({
        ("GET", "/me/onenote/pages"): (200, {"value": [{"id": "0-A!42", "title": title}]}),
        ("GET", "/me/onenote/pages/0-A!42/content"): (200, "<p>Done</p>"),
    })
    with patch("connectonion.useful_tools.outlook.httpx.request", request), \
         patch("connectonion.useful_tools.onenote.httpx.request", request):
        assert "Done" in OneNote().read_page_by_title(title)
    assert calls[0][3]["params"]["$filter"] == "title eq 'Aaron''s plan'"

    duplicates = {"value": [{"id": "0-A!42", "title": title},
                            {"id": "0-A!43", "title": title}]}
    request, _ = _graph({("GET", "/me/onenote/pages"): (200, duplicates)})
    with patch("connectonion.useful_tools.outlook.httpx.request", request):
        with pytest.raises(ValueError, match="Several pages") as refused:
            OneNote().read_page_by_title(title)
    assert "0-A!42" in str(refused.value) and "0-A!43" in str(refused.value)


def test_create_page_posts_escaped_html_to_the_section_and_returns_its_link():
    request, calls = _graph({
        ("GET", "/me/onenote/notebooks"): (200, NOTEBOOKS),
        ("POST", "/me/onenote/sections/s2/pages"): (201, {"id": "p9", "links": {"oneNoteWebUrl": {"href": "https://onenote/p9"}}}),
    })
    with patch("connectonion.useful_tools.onenote.httpx.request", request), \
            patch("connectonion.useful_tools.outlook.httpx.request", request):
        result = OneNote().create_page("Readings", "Week <6>", "Line one\n\nLine & two")
    method, url, headers, kwargs = calls[-1]
    assert headers["Content-Type"] == "text/html"
    body = kwargs["content"].decode()
    assert "<title>Week &lt;6&gt;</title>" in body and "<p>Line &amp; two</p>" in body
    assert "p9" in result and "https://onenote/p9" in result


def test_create_timeout_says_the_page_may_already_exist():
    def slow_post(method, url, **kwargs):
        raise httpx.ReadTimeout("slow")

    with patch.object(OneNote, "_section", return_value={"id": "s2"}), \
            patch("connectonion.useful_tools.onenote.httpx.request", slow_post):
        with pytest.raises(ValueError, match="may exist"):
            OneNote().create_page("Readings", "Week 5", "Body")


def test_an_expired_token_is_refreshed_once_for_page_content():
    responses = iter([MagicMock(status_code=401, text="", headers={}),
                      MagicMock(status_code=200, text="<html><body><p>ok</p></body></html>", headers={})])
    seen = []

    def request(method, url, headers=None, **kwargs):
        seen.append(headers["Authorization"])
        return next(responses)
    with patch("connectonion.useful_tools.onenote.httpx.request", request):
        assert "ok" in OneNote().read_page("p1")
    assert seen == ["Bearer token", "Bearer fresh"]


def test_onenote_is_exported_for_agents():
    from connectonion import OneNote as exported
    assert exported is OneNote


@pytest.fixture
def cli_listings(monkeypatch, tmp_path):
    from connectonion.cli.commands import onenote_commands
    monkeypatch.setattr(onenote_commands, "LISTINGS", tmp_path / "onenote-listings")
    monkeypatch.setattr(onenote_commands, "_account", lambda note: "one@example.test")


def test_the_cli_lists_notebooks_and_names_the_next_command(monkeypatch, capsys, cli_listings):
    from connectonion.cli.commands import onenote_commands
    monkeypatch.setattr(onenote_commands, "_onenote",
                        lambda: SimpleNamespace(notebook_items=lambda: NOTEBOOKS["value"]))
    onenote_commands.handle_onenote_ls()
    out = capsys.readouterr().out
    assert "COMP3900" in out and "2. Readings" in out
    assert "section s2" not in out
    assert "Next: co onenote pages 1" in out


def test_bare_onenote_and_missing_page_argument_browse_recent_pages(monkeypatch, cli_listings):
    from typer.testing import CliRunner
    from connectonion.cli.commands import onenote_commands
    from connectonion.cli.main import app
    monkeypatch.setattr(onenote_commands, "_onenote",
                        lambda: SimpleNamespace(page_items=lambda *args, **kwargs: [
                            {"id": "0-A!42", "title": "Recent", "lastModifiedDateTime": "2026-09-28"}]))
    for args in (["onenote"], ["onenote", "pages"], ["onenote", "read"]):
        result = CliRunner().invoke(app, args)
        assert result.exit_code == 0, result.output
        assert "1. Recent" in result.output and "page 0-A!42" not in result.output
        assert "Next: co onenote read 1" in result.output


def test_ids_option_exposes_full_ids_only_when_requested(monkeypatch, cli_listings):
    from typer.testing import CliRunner
    from connectonion.cli.commands import onenote_commands
    from connectonion.cli.main import app
    note = SimpleNamespace(notebook_items=lambda: NOTEBOOKS["value"],
                           page_items=lambda *args, **kwargs: [
                               {"id": "0-A!42", "title": "Recent"}])
    monkeypatch.setattr(onenote_commands, "_onenote", lambda: note)
    runner = CliRunner()
    assert "section s2" in runner.invoke(app, ["onenote", "ls", "--ids"]).output
    assert "page 0-A!42" in runner.invoke(app, ["onenote", "pages", "--ids"]).output


def test_cli_timeout_is_concise_and_create_is_not_blindly_retried(monkeypatch, capsys, cli_listings):
    from connectonion.cli.commands import onenote_commands

    def slow(*args, **kwargs):
        raise httpx.ReadTimeout("slow")

    monkeypatch.setattr(onenote_commands, "_onenote",
                        lambda: SimpleNamespace(page_items=slow))
    with pytest.raises(SystemExit) as failed:
        onenote_commands.handle_onenote_pages()
    assert failed.value.code == 1
    output = capsys.readouterr().err
    assert "Try again: co onenote pages" in output and "Traceback" not in output

    monkeypatch.setattr(onenote_commands, "_onenote",
                        lambda: SimpleNamespace(create_page=lambda *args: slow()))
    with pytest.raises(SystemExit):
        onenote_commands.handle_onenote_create("Lab notes", "New", "Body")
    assert "may exist" in capsys.readouterr().err


def test_numbered_terminal_journey_uses_section_and_page_ids(monkeypatch, cli_listings):
    from typer.testing import CliRunner
    from connectonion.cli.commands import onenote_commands
    from connectonion.cli.main import app
    calls = []

    def pages(section=None, max_results=20):
        calls.append(("pages", section))
        return [{"id": "0-A!41", "title": "Same title", "lastModifiedDateTime": "2026-09-28"},
                {"id": "0-A!42", "title": "Same title", "lastModifiedDateTime": "2026-09-27"}]

    note = SimpleNamespace(notebook_items=lambda: NOTEBOOKS["value"], page_items=pages,
                           read_page=lambda page_id: calls.append(("read", page_id)) or "Page body")
    monkeypatch.setattr(onenote_commands, "_onenote", lambda: note)
    runner = CliRunner()
    listed = runner.invoke(app, ["onenote", "ls"])
    assert listed.exit_code == 0, listed.output
    assert "2. Readings" in listed.output
    selected = runner.invoke(app, ["onenote", "pages", "2"])
    assert selected.exit_code == 0, selected.output
    assert "1. Same title" in selected.output and "2. Same title" in selected.output
    assert "page 0-A!42" not in selected.output
    opened = runner.invoke(app, ["onenote", "read", "2"])
    assert opened.exit_code == 0, opened.output
    assert "Page body" in opened.output
    assert calls == [("pages", "s2"), ("read", "0-A!42")]


def test_empty_relist_and_account_switch_never_use_an_old_number(monkeypatch, cli_listings):
    from typer.testing import CliRunner
    from connectonion.cli.commands import onenote_commands
    from connectonion.cli.main import app
    account = ["one@example.test"]
    monkeypatch.setattr(onenote_commands, "_account", lambda note: account[0])
    note = SimpleNamespace(page_items=MagicMock(return_value=[{"id": "p1", "title": "First"}]),
                           read_page=MagicMock(return_value="secret"))
    monkeypatch.setattr(onenote_commands, "_onenote", lambda: note)
    runner = CliRunner()
    assert runner.invoke(app, ["onenote", "pages"]).exit_code == 0
    account[0] = "other@example.test"
    assert runner.invoke(app, ["onenote", "read", "1"]).exit_code == 1
    account[0] = "one@example.test"
    note.page_items.return_value = []
    assert runner.invoke(app, ["onenote", "pages"]).exit_code == 0
    assert runner.invoke(app, ["onenote", "read", "1"]).exit_code == 1
    note.read_page.assert_not_called()


def test_listing_id_pins_the_section_after_a_new_ls(monkeypatch, cli_listings):
    from typer.testing import CliRunner
    from connectonion.cli.commands import onenote_commands
    from connectonion.cli.main import app
    notebooks = MagicMock(side_effect=[
        [{"displayName": "First", "sections": [{"id": "s1", "displayName": "Notes"}]}],
        [{"displayName": "Second", "sections": [{"id": "s2", "displayName": "Notes"}]}],
    ])
    pages = MagicMock(return_value=[])
    monkeypatch.setattr(onenote_commands, "_onenote", lambda: SimpleNamespace(
        notebook_items=notebooks, page_items=pages))
    runner = CliRunner()
    first = runner.invoke(app, ["onenote", "ls"])
    token = re.search(r"Listing: ([a-f0-9]{32})", first.output).group(1)
    assert runner.invoke(app, ["onenote", "ls"]).exit_code == 0
    assert runner.invoke(app, ["onenote", "pages", "1", "--listing", token]).exit_code == 0
    assert runner.invoke(app, ["onenote", "pages", "1"]).exit_code == 0
    assert [call.args[0] for call in pages.call_args_list] == ["s1", "s2"]


def test_numbered_page_expires_in_fifteen_minutes(monkeypatch, cli_listings):
    from typer.testing import CliRunner
    from connectonion.cli.commands import gmail_listings, onenote_commands
    from connectonion.cli.main import app
    now = [1000.0]
    monkeypatch.setattr(gmail_listings.time, "time", lambda: now[0])
    read = MagicMock(return_value="body")
    monkeypatch.setattr(onenote_commands, "_onenote", lambda: SimpleNamespace(
        page_items=lambda *args, **kwargs: [{"id": "p1", "title": "First"}], read_page=read))
    runner = CliRunner()
    assert runner.invoke(app, ["onenote", "pages"]).exit_code == 0
    now[0] += 15 * 60
    result = runner.invoke(app, ["onenote", "read", "1"])
    assert result.exit_code == 1
    assert "co onenote pages" in result.output
    read.assert_not_called()


def test_numbered_create_requires_confirmation_or_explicit_listing(monkeypatch, capsys, cli_listings):
    from connectonion.cli.commands import onenote_commands
    note = SimpleNamespace(notebook_items=lambda: NOTEBOOKS["value"],
                           _section=lambda section: {"notebook": "COMP3900", "displayName": "Readings"},
                           create_page=MagicMock(return_value="Created page p9"))
    monkeypatch.setattr(onenote_commands, "_onenote", lambda: note)
    onenote_commands.handle_onenote_ls()
    monkeypatch.setattr(onenote_commands, "_can_confirm", lambda: False)
    with pytest.raises(SystemExit):
        onenote_commands.handle_onenote_create("2", "Week 5", "Body")
    note.create_page.assert_not_called()
    monkeypatch.setattr(onenote_commands, "_can_confirm", lambda: True)
    monkeypatch.setattr(onenote_commands.typer, "confirm", lambda *args, **kwargs: False)
    with pytest.raises(onenote_commands.typer.Exit):
        onenote_commands.handle_onenote_create("2", "Week 5", "Body")
    note.create_page.assert_not_called()
    monkeypatch.setattr(onenote_commands.typer, "confirm", lambda *args, **kwargs: True)
    onenote_commands.handle_onenote_create("2", "Week 5", "Body")
    note.create_page.assert_called_once_with("s2", "Week 5", "Body")
    assert "COMP3900 / Readings" in capsys.readouterr().err


def test_the_cli_turns_a_refusal_into_one_line_and_exit_1(monkeypatch, capsys):
    from connectonion.cli.commands import onenote_commands

    def refuse():
        raise ValueError("Missing Microsoft Notes.ReadWrite.All scope.\n  co auth microsoft")
    monkeypatch.setattr(onenote_commands, "_onenote", refuse)
    with pytest.raises(SystemExit) as exit_:
        onenote_commands.handle_onenote_ls()
    assert exit_.value.code == 1 and "co auth microsoft" in capsys.readouterr().err


def test_onenote_is_a_co_command():
    import re
    from typer.testing import CliRunner
    from connectonion.cli.main import app
    result = CliRunner().invoke(app, ["onenote", "--help"], env={"COLUMNS": "200"})
    text = re.sub(r"\x1b\[[0-9;]*m", "", result.output)
    assert all(verb in text for verb in ("ls", "pages", "read", "create"))


class TestARealNotebook:
    """Found on the owner's own notebook on 1.8.9b19, right after OneNote worked.

    Listing the pages of "Quick Notes" took Graph 6-8 seconds, httpx's default
    timeout is 5, and the ReadTimeout reached the terminal as a traceback. A
    page with code clipped from the web read back with U+FFFC where its line
    breaks were.
    """

    def test_graph_calls_wait_long_enough_for_a_slow_section(self):
        seen = []

        def request(method, url, headers=None, **kwargs):
            seen.append(kwargs.get("timeout"))
            response = MagicMock(status_code=200, headers={}, text="x")
            response.json = MagicMock(return_value={"value": []} if "pages" in url else NOTEBOOKS)
            return response
        with patch("connectonion.useful_tools.outlook.httpx.request", request):
            OneNote().list_pages("s1")
        assert seen and all(t is not None and t >= 30 for t in seen)

    def test_a_timeout_is_a_sentence_not_a_traceback(self):
        import httpx

        def request(method, url, headers=None, **kwargs):
            raise httpx.ReadTimeout("The read operation timed out")
        with patch("connectonion.useful_tools.outlook.httpx.request", request):
            with pytest.raises(ValueError) as refused:
                OneNote().list_notebooks()
        assert "did not answer" in str(refused.value) and "co onenote" in str(refused.value)

    def test_object_replacement_characters_become_line_breaks(self):
        from connectonion.useful_tools.onenote import _page_text
        text = _page_text("<html><body><p>&lt;div&gt;￼  &lt;div&gt;01&lt;/div&gt;￼&lt;/div&gt;</p></body></html>")
        assert "￼" not in text and "<div>01</div>" in text.splitlines()

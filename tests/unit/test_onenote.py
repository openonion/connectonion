"""OneNote notebooks for agents and the terminal (#1887).

A student wanted a backend on their OneNote notebooks, and `co auth microsoft`
could not grant it. The tool shares Outlook's credentials, refresh and throttling
retries; these tests stand in for Microsoft Graph.
"""

import os
from unittest.mock import MagicMock, patch

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
    """#1910: outlook.com accepts Notes.ReadWrite only; .All is work or school.

    A personal account signed in with .All alone got a token that read mail,
    while OneNote answered 401 40001 and the CLI said "authorization expired",
    sending the person round the same sign-in forever.
    """

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


def test_the_cli_lists_notebooks_and_names_the_next_command(monkeypatch, capsys):
    from types import SimpleNamespace
    from connectonion.cli.commands import onenote_commands
    monkeypatch.setattr(onenote_commands, "_onenote",
                        lambda: SimpleNamespace(list_notebooks=lambda: "COMP3900  (notebook nb1)"))
    onenote_commands.handle_onenote_ls()
    out = capsys.readouterr().out
    assert "COMP3900" in out and "co onenote pages" in out


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

"""
Purpose: OneNote notebooks for agents and the CLI via Microsoft Graph (#1887)
LLM-Note:
  Dependencies: imports from [html, re, httpx, useful_tools/outlook.Outlook] | imported by [useful_tools/__init__.py, cli/commands/onenote_commands.py] | requires Notes.ReadWrite.All from 'co auth microsoft' | tested by [tests/unit/test_onenote.py]
  Data flow: OneNote methods → JSON Graph calls go through Outlook's authenticated _request (token refresh, 429/503/504 retries) → page content (HTML in, HTML out) goes through _raw(), which uses the same token and refreshes once on 401 → read_page() turns the page's HTML into text; create_page() escapes the text into paragraphs
  State/Effects: reads MICROSOFT_* credentials | create_page() adds a page to a section; nothing here edits or deletes an existing page
  Integration: exposes OneNote with list_notebooks(), list_sections(notebook), list_pages(section), read_page(page_id), create_page(section, title, text) | a section is found by id or exact name; a name in several notebooks is refused with every match
  Errors: ValueError naming `co auth microsoft` when Notes.ReadWrite.All is missing, or naming `co onenote ls` for an unknown or ambiguous section | Graph errors surface as ProviderCredentialError like Outlook's

OneNote tool: list, read and create pages in the notebooks you can open.

Usage:
    from connectonion import Agent, OneNote
    agent = Agent("notes", tools=[OneNote()])
"""

import html
import re

import httpx

from .outlook import Outlook

NOTES_SCOPE = "Notes.ReadWrite.All"


class OneNote:
    """Your OneNote notebooks and the ones shared with you, including Class Notebooks."""

    def __init__(self):
        # Outlook's credential record, token refresh and throttling retries,
        # without its mail tools: composed, not inherited, so an agent given
        # OneNote() is not also handed send() and archive().
        self._graph = Outlook.__new__(Outlook)
        credentials = self._graph._credentials
        scopes = credentials.get("SCOPES") or ""
        if not scopes:
            credentials.require_configured()
        if NOTES_SCOPE not in set(scopes.replace(",", " ").split()):
            raise ValueError(
                f"Missing Microsoft {NOTES_SCOPE} scope: this sign-in did not ask for OneNote.\n"
                "Sign in again; since 1.8.9 it asks for OneNote too:\n"
                "  co auth microsoft"
            )
        self._graph._access_token = None

    # ---- Graph ------------------------------------------------------------

    def _json(self, endpoint: str) -> dict:
        return self._graph._request("GET", endpoint)

    def _raw(self, method: str, endpoint: str, *, content: bytes | None = None,
             content_type: str | None = None) -> httpx.Response:
        """Page content is HTML both ways, so it cannot go through the JSON path."""
        url = f"{Outlook.GRAPH_API_URL}{endpoint}"
        headers = {"Authorization": f"Bearer {self._graph._get_access_token()}"}
        if content_type:
            headers["Content-Type"] = content_type
        response = httpx.request(method, url, headers=headers, content=content)
        if response.status_code == 401 and self._graph._credentials.get("REFRESH_TOKEN") is not None:
            self._graph._access_token = self._graph._refresh_via_backend(
                self._graph._credentials.get("REFRESH_TOKEN"))
            headers["Authorization"] = f"Bearer {self._graph._access_token}"
            response = httpx.request(method, url, headers=headers, content=content)
        if response.status_code == 401 and self._graph._credentials.get("REFRESH_TOKEN") is None:
            self._graph._access_token = self._graph._refresh_via_backend(None)
            headers["Authorization"] = f"Bearer {self._graph._access_token}"
            response = httpx.request(method, url, headers=headers, content=content)
        if response.status_code not in (200, 201):
            from ..provider_credentials import ProviderCredentialError
            raise ProviderCredentialError(
                "permission_denied" if response.status_code == 403 else "provider_unavailable",
                f"OneNote request failed (HTTP {response.status_code}).", "co auth microsoft",
                status=response.status_code)
        return response

    def _notebooks(self) -> list:
        return self._json("/me/onenote/notebooks?$expand=sections($select=id,displayName)"
                          "&$select=id,displayName").get("value", [])

    def _section(self, section: str) -> dict:
        """A section by id or exact name; a name in several notebooks is refused."""
        matches = []
        for notebook in self._notebooks():
            for candidate in notebook.get("sections") or []:
                if section in (candidate.get("id"), candidate.get("displayName")):
                    matches.append({**candidate, "notebook": notebook.get("displayName", "")})
        exact = [m for m in matches if m.get("id") == section]
        if exact:
            return exact[0]
        if not matches:
            raise ValueError(f"No section named {section!r}. See the names and ids with: co onenote ls")
        if len(matches) > 1:
            listed = "; ".join(f"{m['notebook']} / {m['displayName']} (id {m['id']})" for m in matches)
            raise ValueError(f"Several sections are named {section!r}: {listed}. Pass the section id instead.")
        return matches[0]

    # ---- tools ------------------------------------------------------------

    def list_notebooks(self) -> str:
        """List your OneNote notebooks and their sections, with the ids other calls take."""
        notebooks = self._notebooks()
        if not notebooks:
            return "No OneNote notebooks found."
        lines = []
        for notebook in notebooks:
            lines.append(f"{notebook.get('displayName', '')}  (notebook {notebook.get('id', '')})")
            for section in notebook.get("sections") or []:
                lines.append(f"  {section.get('displayName', '')}  (section {section.get('id', '')})")
        return "\n".join(lines)

    def list_sections(self, notebook: str) -> str:
        """List the sections of one notebook, by its name or id."""
        for found in self._notebooks():
            if notebook in (found.get("id"), found.get("displayName")):
                sections = found.get("sections") or []
                return "\n".join(f"{s.get('displayName', '')}  (section {s.get('id', '')})" for s in sections) \
                    or f"Notebook {found.get('displayName')} has no sections."
        raise ValueError(f"No notebook named {notebook!r}. See the names with: co onenote ls")

    def list_pages(self, section: str, max_results: int = 20) -> str:
        """List pages in a section (name or id), most recently changed first."""
        found = self._section(section)
        pages = self._json(f"/me/onenote/sections/{found['id']}/pages?$top={int(max_results)}"
                           "&$select=id,title,lastModifiedDateTime&$orderby=lastModifiedDateTime desc"
                           ).get("value", [])
        if not pages:
            return f"No pages in {found.get('displayName')}."
        return "\n".join(f"{p.get('title') or '(untitled)'}  ({(p.get('lastModifiedDateTime') or '')[:10]}, "
                         f"page {p.get('id', '')})" for p in pages)

    def read_page(self, page_id: str) -> str:
        """Read one page as plain text. Images and attachments are named, not downloaded."""
        return _page_text(self._raw("GET", f"/me/onenote/pages/{page_id}/content").text)

    def create_page(self, section: str, title: str, text: str = "") -> str:
        """Create a new page in a section (name or id) with a title and plain-text body."""
        found = self._section(section)
        paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text or "") if p.strip()]
        body = "".join(f"<p>{html.escape(p).replace(chr(10), '<br/>')}</p>" for p in paragraphs)
        document = (f"<!DOCTYPE html><html><head><title>{html.escape(title)}</title></head>"
                    f"<body>{body}</body></html>")
        created = self._raw("POST", f"/me/onenote/sections/{found['id']}/pages",
                            content=document.encode("utf-8"), content_type="text/html").json()
        link = ((created.get("links") or {}).get("oneNoteWebUrl") or {}).get("href", "")
        return f"Created page {created.get('id', '')} in {found.get('displayName')}" + (f": {link}" if link else "")


def _page_text(page_html: str) -> str:
    """OneNote page HTML as readable text: headings, paragraphs and list items on their own lines."""
    text = re.sub(r"(?is)<(script|style)\b.*?</\1>", "", page_html)
    title = re.search(r"(?is)<title>(.*?)</title>", text)
    text = re.sub(r"(?is)<head\b.*?</head>", "", text)
    text = re.sub(r"(?is)<img\b[^>]*\balt=['\"]([^'\"]*)['\"][^>]*>", r"\n[image: \1]\n", text)
    text = re.sub(r"(?is)<img\b[^>]*>", "\n[image]\n", text)
    text = re.sub(r"(?is)<object\b[^>]*\bdata-attachment=['\"]([^'\"]*)['\"][^>]*>", r"\n[attachment: \1]\n", text)
    text = re.sub(r"(?is)</?(p|div|h[1-6]|li|br|tr)\b[^>]*>", "\n", text)
    text = html.unescape(re.sub(r"(?s)<[^>]+>", "", text)).replace("\xa0", " ")
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if title and title.group(1).strip() and (not lines or lines[0] != title.group(1).strip()):
        lines.insert(0, html.unescape(title.group(1).strip()))
    return "\n".join(lines)

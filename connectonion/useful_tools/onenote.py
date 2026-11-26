"""
Purpose: OneNote notebooks for agents and the CLI via Microsoft Graph (#1887)
LLM-Note:
  Dependencies: imports from [html, re, httpx, useful_tools/outlook.Outlook] | imported by [useful_tools/__init__.py, cli/commands/onenote_commands.py] | requires Notes.ReadWrite (or, work/school, Notes.ReadWrite.All) from 'co auth microsoft' | tested by [tests/unit/test_onenote.py]
  Data flow: OneNote methods → JSON Graph calls go through Outlook's authenticated _request (token refresh, 429/503/504 retries) → page content (HTML in, HTML out) goes through _raw(), which uses the same token and refreshes once on 401 → read_page() turns the page's HTML into text; create_page() escapes the text into paragraphs
  State/Effects: reads MICROSOFT_* credentials | create_page() adds a page to a section; nothing here edits or deletes an existing page
  Integration: exposes OneNote with list_notebooks(), list_sections(notebook), list_pages(section), list_recent_pages(), read_page(page_id), read_page_by_title(title), create_page(section, title, text) | the CLI uses structured notebook_items() and page_items() for numbered rows
  Errors: ValueError naming `co auth microsoft` when no OneNote scope was granted, or when OneNote answers 401 to a sign-in without Notes.ReadWrite (a personal account, #1910), or naming `co onenote ls` for an unknown or ambiguous section | Graph errors surface as ProviderCredentialError like Outlook's

OneNote tool: list, read and create pages in the notebooks you can open.

Usage:
    from connectonion import Agent, OneNote
    agent = Agent("notes", tools=[OneNote()])
"""

import html
import re
from datetime import datetime, timezone

import httpx

from .outlook import Outlook

# Notes.ReadWrite is the only OneNote scope a personal Microsoft account
# (outlook.com) accepts; Notes.ReadWrite.All is work or school only, and adds
# notebooks shared with the user and Class Notebooks. Either one is enough (#1910).
NOTES_SCOPE = "Notes.ReadWrite"
NOTES_SCOPES = ("Notes.ReadWrite", "Notes.ReadWrite.All")

# With .All alone an outlook.com token reads mail while OneNote answers 401
# 40001. Saying "expired" sent the person round the same sign-in forever.
# The OneNote API is slow: listing 20 pages of a real "Quick Notes" section
# took 6-8 s, past httpx's 5 s default, and the ReadTimeout reached the
# terminal as a traceback.
TIMEOUT = 60
NO_ANSWER = ("OneNote did not answer within {seconds} s (the OneNote API is slow on large sections). "
             "Try again: co onenote ls")

PERSONAL_ACCOUNT_REFUSAL = (
    "OneNote refused this sign-in (HTTP 401). A personal Microsoft account (outlook.com) needs "
    "Notes.ReadWrite, which this sign-in did not ask for; co auth microsoft asks for it since 1.8.9b20.\n"
    "Sign in again:\n  co auth microsoft"
)


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
        granted = set(scopes.replace(",", " ").split())
        if not granted & set(NOTES_SCOPES):
            raise ValueError(
                f"Missing Microsoft {NOTES_SCOPE} scope: this sign-in did not ask for OneNote.\n"
                "Sign in again; since 1.8.9 it asks for OneNote too:\n"
                "  co auth microsoft"
            )
        self._personal_scope_missing = NOTES_SCOPE not in granted
        self._graph._access_token = None

    # ---- Graph ------------------------------------------------------------

    def _json(self, endpoint: str, **kwargs) -> dict:
        from ..provider_credentials import ProviderCredentialError
        try:
            return self._graph._request("GET", endpoint, timeout=TIMEOUT, **kwargs)
        except httpx.TransportError as error:
            raise ValueError(NO_ANSWER.format(seconds=TIMEOUT)) from error
        except ProviderCredentialError as error:
            self._refuse_personal_account(getattr(error, "code", None) == "reauth_required")
            raise

    @staticmethod
    def _send(method: str, url: str, headers: dict, content: bytes | None) -> httpx.Response:
        try:
            return httpx.request(method, url, headers=headers, content=content, timeout=TIMEOUT)
        except httpx.TransportError as error:
            if method == "POST":
                raise ValueError("OneNote did not confirm whether it created the page. It may exist; "
                                 "check the section before trying again.") from error
            raise ValueError(NO_ANSWER.format(seconds=TIMEOUT)) from error

    def _refuse_personal_account(self, unauthorized: bool) -> None:
        if unauthorized and self._personal_scope_missing:
            raise ValueError(PERSONAL_ACCOUNT_REFUSAL)

    def _raw(self, method: str, endpoint: str, *, content: bytes | None = None,
             content_type: str | None = None) -> httpx.Response:
        """Page content is HTML both ways, so it cannot go through the JSON path."""
        url = f"{Outlook.GRAPH_API_URL}{endpoint}"
        headers = {"Authorization": f"Bearer {self._graph._get_access_token()}"}
        if content_type:
            headers["Content-Type"] = content_type
        response = self._send(method, url, headers, content)
        if response.status_code == 401 and self._graph._credentials.get("REFRESH_TOKEN") is not None:
            self._graph._access_token = self._graph._refresh_via_backend(
                self._graph._credentials.get("REFRESH_TOKEN"))
            headers["Authorization"] = f"Bearer {self._graph._access_token}"
            response = self._send(method, url, headers, content)
        if response.status_code == 401 and self._graph._credentials.get("REFRESH_TOKEN") is None:
            self._graph._access_token = self._graph._refresh_via_backend(None)
            headers["Authorization"] = f"Bearer {self._graph._access_token}"
            response = self._send(method, url, headers, content)
        self._refuse_personal_account(response.status_code == 401)
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
        notebooks = self.notebook_items()
        if not notebooks:
            return "No OneNote notebooks found."
        lines = []
        for notebook in notebooks:
            lines.append(f"{notebook.get('displayName', '')}  (notebook {notebook.get('id', '')})")
            for section in notebook.get("sections") or []:
                lines.append(f"  {section.get('displayName', '')}  (section {section.get('id', '')})")
        return "\n".join(lines)

    def notebook_items(self) -> list[dict]:
        """Notebook and section metadata for a terminal listing."""
        return self._notebooks()

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
        pages = self.page_items(section, max_results=max_results)
        if not pages:
            return f"No pages in {section}."
        return self._format_pages(pages)

    def list_recent_pages(self, max_results: int = 20) -> str:
        """List recent pages across sections, so browsing needs no section id."""
        pages = self.page_items(max_results=max_results)
        return self._format_pages(pages) if pages else "No OneNote pages found. Run: co onenote ls"

    def page_items(self, section: str | None = None, max_results: int = 20) -> list[dict]:
        """Page metadata, newest first, across notebooks or in one section."""
        base = ("/me/onenote/pages" if section is None else
                f"/me/onenote/sections/{self._section(section)['id']}/pages")
        return self._json(f"{base}?$top={int(max_results)}"
                          "&$select=id,title,lastModifiedDateTime"
                          "&$orderby=lastModifiedDateTime desc").get("value", [])

    @staticmethod
    def _format_pages(pages: list[dict]) -> str:
        return "\n".join(f"{p.get('title') or '(untitled)'}  ({(p.get('lastModifiedDateTime') or '')[:10]}, "
                         f"page {p.get('id', '')})" for p in pages)

    def read_page_by_title(self, title: str) -> str:
        """Read a uniquely titled page without copying its long Graph id."""
        escaped = title.replace("'", "''")
        result = self._json("/me/onenote/pages", params={
            "$filter": f"title eq '{escaped}'", "$top": 100,
            "$select": "id,title,lastModifiedDateTime",
        })
        matches = [page for page in result.get("value", []) if page.get("title") == title]
        if not matches:
            raise ValueError(f"No page titled {title!r}. Run: co onenote pages")
        if len(matches) != 1 or result.get("@odata.nextLink"):
            ids = ", ".join(page.get("id", "") for page in matches)
            raise ValueError(f"Several pages are titled {title!r}: {ids}. Use the page id from co onenote pages.")
        return self.read_page(matches[0]["id"])

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
    # U+FFFC is where OneNote keeps the line breaks of code clipped from the web.
    text = html.unescape(re.sub(r"(?s)<[^>]+>", "", text)).replace("\xa0", " ").replace("\ufffc", "\n")
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if title and title.group(1).strip() and (not lines or lines[0] != title.group(1).strip()):
        lines.insert(0, html.unescape(title.group(1).strip()))
    return "\n".join(lines)


# ---- REM source commands (DD-081): co onenote changes / show --json ---------
#
# Module functions, not OneNote methods, so an agent given OneNote() is not
# handed them as tools. Scope arrives on the command line (--section); nothing
# here reads REM state, and nothing is written anywhere.

MAX_CHANGES = 1_000
PAGE_BATCH = 100      # the OneNote API's largest $top for pages
MAX_BATCHES = 100
LINK_HOSTS = ("onenote.com", "onedrive.com", "live.com", "sharepoint.com", "office.com")
SECRET_QUERY_KEYS = {"access_token", "authkey", "token", "sig", "code", "tempauth"}


class OneNoteSourceError(ValueError):
    """A source-command failure with a safe message, one recovery command and a stable kind."""

    def __init__(self, message: str, next_step: str, kind: str = "incomplete"):
        super().__init__(message)
        self.next_step = next_step
        self.kind = kind


def parse_since(raw: str) -> datetime:
    """--since as UTC; a date and time with a timezone, e.g. 2026-11-20T00:00:00Z."""
    hint = "--since must be an ISO-8601 date and time with a timezone, e.g. 2026-11-20T00:00:00Z."
    text = raw[:-1] + "+00:00" if isinstance(raw, str) and raw.endswith(("Z", "z")) else raw
    try:
        if not isinstance(text, str) or "T" not in text:
            raise ValueError
        moment = datetime.fromisoformat(text)
    except ValueError:
        raise OneNoteSourceError(hint, "co onenote changes --help", "invalid") from None
    if moment.utcoffset() is None:
        raise OneNoteSourceError(hint, "co onenote changes --help", "invalid")
    return moment.astimezone(timezone.utc)


def _graph_time(value: object, page_id: str) -> datetime:
    try:
        return parse_since(value)
    except OneNoteSourceError:
        raise OneNoteSourceError(f"OneNote returned no valid lastModifiedDateTime for page {page_id}.",
                                 "co onenote ls") from None


def _utc(moment: datetime) -> str:
    return moment.isoformat().replace("+00:00", "Z")


def valid_id(value: object) -> bool:
    """One clean Graph ID token: no spaces, slashes, query or fragment characters."""
    return (isinstance(value, str) and 0 < len(value) <= 512 and value.isascii() and value.isprintable()
            and not any(ch.isspace() or ch in "/\\?#%" for ch in value))


def clean_link(page: dict) -> str | None:
    """The page's OneNote web link, only when it is https on a Microsoft host and carries no token."""
    from urllib.parse import parse_qsl, urlsplit
    from .granola import KEY_SHAPES
    url = ((page.get("links") or {}).get("oneNoteWebUrl") or {}).get("href")
    if not isinstance(url, str) or KEY_SHAPES.search(url) or any(ord(ch) < 33 for ch in url):
        return None
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError:
        return None
    host = (parts.hostname or "").lower()
    keys = {key.lower() for key, _ in parse_qsl(parts.query + "&" + parts.fragment)}
    if (parts.scheme != "https" or parts.username or parts.password or port not in (None, 443)
            or not any(host == domain or host.endswith("." + domain) for domain in LINK_HOSTS)
            or keys & SECRET_QUERY_KEYS):
        return None
    return url


def _source_section(note: OneNote, section: str) -> dict:
    """A section in the signed-in account's own notebook list, by id or unique exact name."""
    if not isinstance(section, str) or not section.strip():
        raise OneNoteSourceError("--section needs a section ID from co onenote ls --ids.",
                                 "co onenote ls --ids", "invalid")
    try:
        return note._section(section)
    except ValueError as error:
        raise OneNoteSourceError(str(error), "co onenote ls --ids", "scope") from None


def _next_batch(link: object) -> str:
    """Graph's absolute @odata.nextLink as an endpoint on the same Graph API."""
    prefix = f"{Outlook.GRAPH_API_URL}/"
    if not isinstance(link, str) or not link.startswith(prefix):
        raise OneNoteSourceError("OneNote returned a next-page link outside Microsoft Graph.", "co onenote ls")
    return link[len(Outlook.GRAPH_API_URL):]


def section_changes(note: OneNote, section: str, since: datetime) -> list[dict]:
    """Pages in one section modified after `since`, oldest first. Metadata only: no page content is read.

    Reads newest first (the order `co onenote pages` already uses) and stops at the
    first page not newer than `since`, so only the changed pages are listed.
    """
    from urllib.parse import quote
    from .granola import redact_text
    found = _source_section(note, section)
    endpoint = (f"/me/onenote/sections/{quote(found['id'], safe='')}/pages?$top={PAGE_BATCH}"
                "&$select=id,title,lastModifiedDateTime,links&$orderby=lastModifiedDateTime desc")
    changed: list[tuple] = []
    for _ in range(MAX_BATCHES):
        batch = note._json(endpoint)
        for page in batch.get("value") or []:
            page_id = page.get("id")
            if not valid_id(page_id):
                raise OneNoteSourceError("OneNote returned an invalid page ID.", "co onenote ls")
            modified = _graph_time(page.get("lastModifiedDateTime"), page_id)
            if modified <= since:
                return _oldest_first(changed)
            if len(changed) >= MAX_CHANGES:
                raise OneNoteSourceError(
                    f"More than {MAX_CHANGES} pages changed since {_utc(since)}; pass a more recent --since.",
                    f"co onenote changes --since {_utc(since)} --section {found['id']}")
            time = page["lastModifiedDateTime"]   # Graph's own string: the page's only revision marker
            changed.append((modified, {"id": page_id, "version": time, "time": time,
                                       "title": redact_text(page.get("title") or "(untitled)"),
                                       "link": clean_link(page)}))
        if not batch.get("@odata.nextLink"):
            return _oldest_first(changed)
        endpoint = _next_batch(batch["@odata.nextLink"])
    raise OneNoteSourceError(f"OneNote paging went past {MAX_BATCHES} batches.", "co onenote ls")


def _oldest_first(changed: list[tuple]) -> list[dict]:
    return [item for _, item in sorted(changed, key=lambda pair: (pair[0], pair[1]["id"]))]


def page_source(note: OneNote, page_id: str, section: str | None = None) -> dict:
    """One page live: metadata, then its text. With `section`, a page filed elsewhere is refused."""
    from urllib.parse import quote
    from ..provider_credentials import ProviderCredentialError
    from .granola import redact_text
    clean = page_id[len("onenote:"):] if isinstance(page_id, str) and page_id.startswith("onenote:") else page_id
    if not valid_id(clean):
        raise OneNoteSourceError("Page ID is invalid. Use an id from co onenote changes.",
                                 "co onenote changes --help", "invalid")
    found = _source_section(note, section) if section is not None else None
    try:
        page = note._json(f"/me/onenote/pages/{quote(clean, safe='')}?$expand=parentSection,parentNotebook")
    except ProviderCredentialError as error:
        if error.status == 404:
            raise OneNoteSourceError(f"No OneNote page {clean} in this account.", "co onenote ls --ids",
                                     "not_found") from None
        raise
    if page.get("id") != clean:
        raise OneNoteSourceError("OneNote returned a different page than the one asked for.", "co onenote ls")
    parent = (page.get("parentSection") or {}).get("id")
    if found is not None and parent != found["id"]:
        raise OneNoteSourceError(f"Page {clean} is outside section {found['id']}.",
                                 f"co onenote pages {found['id']} --ids", "scope")
    _graph_time(page.get("lastModifiedDateTime"), clean)
    time = page["lastModifiedDateTime"]
    text = _page_text(note._raw("GET", f"/me/onenote/pages/{quote(clean, safe='')}/content").text)
    return {"id": clean, "version": time, "time": time, "created": page.get("createdDateTime"),
            "title": redact_text(page.get("title") or "(untitled)"), "text": redact_text(text),
            "author": None, "link": clean_link(page), "section_id": parent,
            "notebook_id": (page.get("parentNotebook") or {}).get("id")}

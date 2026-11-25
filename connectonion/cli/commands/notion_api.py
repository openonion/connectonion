"""
Purpose: Notion's REST API for `co notion` — one read-only client, one set of limits
LLM-Note:
  Dependencies: imports from [json, re, time, urllib.parse, httpx, environment.py (setting: process, env file, then the --secret store)] | imported by [cli/commands/notion_commands.py] | tested by [tests/unit/test_notion_commands.py]
  Data flow: credential() = a NOTION_API_KEY exported in the shell, else NOTION_API_KEY from the selected env file or the --secret store → call(method, path, body) sends https://api.notion.com/v1/<path> with `Authorization: Bearer <key>` and `Notion-Version: 2025-09-03` → JSON dict | parse_target() turns a link or id into {id, block, view} | data_source() resolves a database link to the one data source it means | read_page() returns properties (typed, paginated), the block tree (nested, bounded) and an explicit coverage record
  State/Effects: reads NOTION_API_KEY (and optional NOTION_VERSION); network: Notion only. Every request is a read: GET, or the read-only POSTs search and data_sources/<id>/query
  Integration: row() is the one shape search/db lists print and --json returns | the 2025-09-03 model: a database is a container of data sources; schema, query and rows belong to a data source
  Errors: NotionError(message, next_step, kind, detail). A read's 429, 5xx or transport failure is retried a bounded number of times (attempts and seconds), then reported; a write is retried only on 429, and after a timeout or 5xx it is reported as unknown_outcome, never re-sent
"""

import json
import re
import time
from dataclasses import dataclass
from urllib.parse import parse_qs, urlparse

import httpx

URL = "https://api.notion.com/v1"
KEY = "NOTION_API_KEY"
VERSION_KEY = "NOTION_VERSION"
# The data-source model (databases hold data sources; schema, query and rows
# belong to the data source). Pinned so a Notion release never changes a shape.
DEFAULT_VERSION = "2025-09-03"
# Where the key comes from: an internal connection's token (it reads only the pages given to it), or a
# personal access token (it reads what the person's own Notion account can read).
KEY_PAGE = ("the Notion Developer portal (app.notion.com/developers/connections) → Internal connections → "
            "Configuration")
CONTENT_ACCESS = "Content access → Edit access in the Developer portal, or open the page → ••• → Connections"
KEY_SCOPE = ("an internal connection reads only the pages given to it; a personal access token reads what your "
             "own Notion account can read")
SET_KEY = f"co env set {KEY} ntn_... --secret"
SHARE_HINT = f"With an internal connection, give it the page: {CONTENT_ACCESS}"
SEARCH_NOTE = ("This lists what this key can read (" + KEY_SCOPE + "); "
               "it is not a list of the whole workspace")

# What one page read walks before it says it stopped.
DEFAULT_BLOCK_LIMIT = 2000
DEFAULT_DEPTH = 8
# Reads that fail transiently are retried, at most this many attempts and seconds.
READ_ATTEMPTS = 3
MAX_WAIT_SECONDS = 20
_sleep = time.sleep           # tests replace this


# Notion's write limits: blocks per request, characters per text item, items per rich text, bytes per request.
MAX_BLOCKS = 100
MAX_TEXT = 2000
MAX_RICH_ITEMS = 100
MAX_PAYLOAD_BYTES = 400_000   # children per request: under the 500 KB cap with room for the envelope
REQUEST_LIMIT_BYTES = 500_000  # Notion's own cap on a whole request body


def weight(obj) -> int:
    """Bytes as \\u-escaped JSON: the larger of the two encodings httpx versions use for a body."""
    return len(json.dumps(obj).encode("utf-8"))


class NotionError(Exception):
    """What went wrong, and the one command that fixes or explains it.

    `kind` is machine-readable: not_found, unauthorized, forbidden, rate_limited,
    network, ambiguous, invalid. `detail` carries what is known for sure.
    """

    def __init__(self, message: str, next_step: str, kind: str = "", detail: dict | None = None):
        super().__init__(message)
        self.next_step = next_step
        self.kind = kind
        self.detail = detail or {}


class Credential:
    """The key a request carries, and where it came from: "shell" (exported) or "key" (saved)."""

    def __init__(self, token: str, source: str):
        self.token, self.source = token, source

    @property
    def label(self) -> str:
        return f"the {KEY} exported in your shell" if self.source == "shell" else KEY


def credential() -> Credential:
    """NOTION_API_KEY: exported in the shell, else the selected env file, else `co env set --secret`'s store."""
    from ...environment import display_path, load_environment, process_environment, selected_env_file, setting
    load_environment()
    exported = process_environment().get(KEY)
    if exported:
        return Credential(exported, "shell")
    key = setting(KEY)
    if key:
        return Credential(key, "key")
    raise NotionError(f"Notion is not connected in {display_path(selected_env_file())}. Create an internal "
                      f"connection in {KEY_PAGE}, give it pages ({CONTENT_ACCESS}), then save its token with "
                      f"{SET_KEY}. A personal access token works too, and reads everything your account can",
                      SET_KEY, "unauthorized")


def api_key() -> str:
    """The token requests carry now (see credential())."""
    return credential().token


def version() -> str:
    from ...environment import setting
    return setting(VERSION_KEY) or DEFAULT_VERSION


def _http() -> httpx.Client:
    """The HTTP client; tests swap in httpx.MockTransport here."""
    return httpx.Client(timeout=30)


def _wait(response: httpx.Response | None, attempt: int) -> float:
    after = response.headers.get("retry-after", "") if response is not None else ""
    try:
        seconds = float(after)
    except ValueError:
        seconds = 2.0 ** attempt
    return max(0.0, min(seconds, MAX_WAIT_SECONDS))


def call(method: str, path: str, body: dict | None = None, params: dict | None = None) -> dict:
    """One request; return Notion's JSON, or raise NotionError.

    GET and the read-only POSTs (search, query) are retried on 429, 5xx and
    transport failures, within READ_ATTEMPTS and MAX_WAIT_SECONDS. A write is
    retried only on 429, which Notion returns before doing anything; after a
    timeout or 5xx its outcome is unknown and replaying it could create or
    append twice, so it is reported as unknown_outcome instead.
    """
    read = method == "GET" or (method == "POST" and (path == "search" or path.endswith("/query")))
    if not read and body is not None and weight(body) > REQUEST_LIMIT_BYTES:
        # Never send what Notion must refuse: measured in the larger JSON encoding.
        raise NotionError(f"This write is {weight(body):,} bytes as JSON; Notion takes at most "
                          f"{REQUEST_LIMIT_BYTES:,} in one request. Nothing was sent. Shorten the title or a "
                          "property value", "co notion --help", "invalid")
    using = credential()
    response = _send(method, path, body, params, using.token, read)
    if response is None:
        raise NotionError("Notion could not be reached", "co notion check", "network")
    try:
        data = response.json()
    except ValueError:
        data = None
    if not isinstance(data, dict):
        if not read and response.status_code >= 500:
            raise NotionError(f"Notion answered {response.status_code}; the change may or may not have been made",
                              "co notion check", "unknown_outcome", {"request": f"{method} {path}"})
        raise NotionError(f"Notion returned an unreadable response (HTTP {response.status_code})",
                          "co notion check", "invalid_response")
    if response.status_code >= 400 or data.get("object") == "error":
        raise _error(data, response.status_code, write=not read, request=f"{method} {path}", using=using)
    return data


def _send(method: str, path: str, body: dict | None, params: dict | None, token: str, read: bool = True):
    """One request with its retries (see call()); the last response, or None if Notion never answered."""
    headers = {"Authorization": f"Bearer {token}", "Notion-Version": version(), "Content-Type": "application/json"}
    waited = 0.0
    attempts = READ_ATTEMPTS if read else 2
    for attempt in range(attempts):
        response = None
        try:
            with _http() as client:
                response = client.request(method, f"{URL}/{path}", json=body, params=params, headers=headers)
        except httpx.TransportError as error:
            if not read:
                raise NotionError(f"No answer from Notion ({type(error).__name__}); the change may or may not "
                                  "have been made", "co notion check", "unknown_outcome",
                                  {"request": f"{method} {path}"}) from None
            if attempt + 1 >= READ_ATTEMPTS:
                raise NotionError(f"Notion could not be reached ({type(error).__name__})", "co notion check",
                                  "network") from None
        else:
            status = response.status_code
            if not (status == 429 or (read and status in (500, 502, 503, 504))):
                break
        pause = _wait(response, attempt)
        if waited + pause > MAX_WAIT_SECONDS or attempt + 1 >= attempts:
            break
        waited += pause
        _sleep(pause)
    return response


def _error(data: dict, status: int, *, write: bool = False, request: str = "",
           using: Credential | None = None) -> NotionError:
    code = data.get("code", "")
    message = (data.get("message") or "unknown error").rstrip(".")
    if status == 401 or code == "unauthorized":
        if using is not None and using.source == "shell":
            # The exported key is used before a saved one, so saving a new key changes nothing until it is unset.
            return NotionError(f"Notion rejected {using.label}: {message}. Export a new secret from {KEY_PAGE}, or "
                               f"run unset {KEY} to use the saved one", f"unset {KEY} && co notion check",
                               "unauthorized")
        return NotionError(f"Notion rejected {KEY}: {message}. Make a new secret in {KEY_PAGE} and save it with "
                           f"{SET_KEY}", SET_KEY, "unauthorized")
    if status == 403 or code == "restricted_resource":
        return NotionError(f"Notion refused this for the key: {message}. The page may be readable, but the "
                           f"key lacks the capability this needs (read, insert or update content); for an internal connection, "
                           f"turn it on under "
                           f"Capabilities in {KEY_PAGE.split(' → ')[0]}", "co notion check --target <link>", "forbidden")
    if status == 404 or code == "object_not_found":
        return NotionError(f"Notion: {message}. If it exists, this key cannot read it. {SHARE_HINT}",
                           'co notion search "<words from its title>"', "not_found")
    if status == 429 or code == "rate_limited":
        return NotionError("Notion is still rate limiting this key after waiting; run it again in a minute",
                           "co notion check", "rate_limited")
    if write and status >= 500:
        return NotionError(f"Notion answered {status} ({message}); the change may or may not have been made",
                           "co notion check", "unknown_outcome", {"request": request})
    if code == "validation_error":
        return NotionError(f"Notion refused the request: {message}", "co notion --help", "invalid")
    return NotionError(f"Notion: {message}", "co notion check", code)


# -- ids and links ---------------------------------------------------------

# 32 hex characters standing alone: Notion writes `Title-<id>`, so the dash bounds it and
# a title made of hex letters ("Cafe", "Deadbeef") is never read as part of the id.
_HEX32 = re.compile(r"(?<![0-9a-fA-F])[0-9a-fA-F]{32}(?![0-9a-fA-F])")
_UUID = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")


def _dashed(hex32: str) -> str:
    h = hex32.replace("-", "").lower()
    return f"{h[:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:]}"


def _id_in(text: str) -> str | None:
    match = _UUID.search(text) or None
    if match:
        return _dashed(match.group(0))
    found = _HEX32.findall(text)
    return _dashed(found[-1]) if found else None


@dataclass(frozen=True)
class Target:
    """What a link or id names. `id` is the object to act on; `block` an anchor inside it; `view` a database view."""
    id: str
    block: str = ""
    view: str = ""
    peek: bool = False


def parse_target(given: str) -> Target:
    """A Notion link or id, read the way Notion builds its links.

    - `notion.so/ws/Title-<id>` and `<id>` (dashed or not): the page or database.
    - `?v=<view>`: a database view; the database is the object, the view is kept.
    - `?p=<page>` (a page opened in peek view over a database): the page is the object.
    - `#<block>`: a block anchor on the page; the page is still the object.
    Only the path names the object, so a title made of hex letters or a view id never wins.
    """
    text = (given or "").strip()
    if not text:
        raise NotionError("Give a Notion page or database link or id", 'co notion search "<words from its title>"',
                          "invalid")
    if "://" not in text and "/" not in text and "?" not in text and "#" not in text:
        found = _id_in(text)
        if found and len(re.sub(r"[^0-9a-fA-F]", "", text)) == 32:
            return Target(found)
        raise NotionError(f"{given!r} is not a Notion page id or link", 'co notion search "<words from its title>"',
                          "invalid")
    url = urlparse(text if "://" in text else "https://" + text)
    query = parse_qs(url.query)
    view = _id_in(query.get("v", [""])[0]) or ""
    block = _id_in(url.fragment) or ""
    peek = _id_in(query.get("p", [""])[0])
    if peek:
        return Target(peek, block=block, view=view, peek=True)
    tail = url.path.rstrip("/").rsplit("/", 1)[-1]
    found = _id_in(tail)
    if not found:
        raise NotionError(f"{given!r} has no Notion page or database id in it",
                          'co notion search "<words from its title>"', "invalid")
    return Target(found, block=block, view=view)


def page_id(given: str) -> str:
    return parse_target(given).id


# -- text ------------------------------------------------------------------

def plain(rich_text: list | None) -> str:
    return "".join(part.get("plain_text") or (part.get("text") or {}).get("content", "")
                   for part in rich_text or [])


def markdown(rich_text: list | None) -> str:
    """Rich text with its links kept as [text](url): a link is content, and changing its target is a change."""
    out = []
    for part in rich_text or []:
        text = part.get("plain_text") or (part.get("text") or {}).get("content", "")
        href = part.get("href") or ((part.get("text") or {}).get("link") or {}).get("url") or ""
        out.append(f"[{text}]({href})" if text and re.match(r"https?://", href) else text)
    return "".join(out)


def one_line(text: str) -> str:
    """A title as one line, for display: Notion lets a title hold line breaks, and printed as they
    are they split a numbered row in two. --json keeps the title as Notion has it."""
    return " ".join((text or "").split())


def title_of(obj: dict) -> str:
    """The title of a page (its title-typed property), a database or a data source."""
    if obj.get("object") in ("database", "data_source"):
        return plain(obj.get("title")) or obj.get("name") or "(untitled)"
    for prop in (obj.get("properties") or {}).values():
        if prop.get("type") == "title":
            return plain(prop.get("title")) or "(untitled)"
    return "(untitled)"


def trashed(obj: dict) -> bool:
    return bool(obj.get("in_trash") or obj.get("archived"))


def parent_of(obj: dict) -> dict:
    """{type, id} of an object's parent, with data_source/database spelled the same in every version."""
    parent = obj.get("parent") or {}
    if parent.get("data_source_id"):
        return {"type": "data_source", "id": parent["data_source_id"], "database_id": parent.get("database_id", "")}
    kind = parent.get("type", "")
    return {"type": kind.replace("_id", ""), "id": parent.get(kind) if isinstance(parent.get(kind), str) else ""}


def row(obj: dict) -> dict:
    """The fields every list prints and --json returns: full id, type, title, parent, edited, link, trash."""
    parent = parent_of(obj)
    return {"id": obj["id"], "type": obj.get("object", "page"), "title": title_of(obj),
            "parent": parent["type"], "parent_id": parent["id"],
            "edited": obj.get("last_edited_time", ""), "url": obj.get("url", ""), "in_trash": trashed(obj)}


# -- reads: identity, search ---------------------------------------------

def whoami() -> dict:
    return call("GET", "users/me")


def workspace(bot: dict) -> dict:
    """The workspace this secret acts in, as far as Notion says: name, id when given, the bot's own id."""
    inner = bot.get("bot") or {}
    return {"name": inner.get("workspace_name") or "", "id": inner.get("workspace_id") or "",
            "bot_id": bot.get("id", ""), "bot_name": bot.get("name") or ""}


def search(query: str, kind: str | None, first: int, cursor: str = "") -> tuple[list, str]:
    """(results, next_cursor or ''). `kind` is page or database (searched as data sources)."""
    body: dict = {"query": query, "page_size": min(first, 100),
                  "sort": {"direction": "descending", "timestamp": "last_edited_time"}}
    if kind:
        body["filter"] = {"property": "object", "value": "data_source" if kind == "database" else kind}
    if cursor:
        body["start_cursor"] = cursor
    data = call("POST", "search", body)
    return data.get("results", [])[:first], (data.get("next_cursor") or "") if data.get("has_more") else ""


def page(given: str) -> dict:
    return call("GET", f"pages/{page_id(given)}")


# -- data sources ----------------------------------------------------------

def data_source(given: str, source: str = "") -> dict:
    """The data source a database link, a data source id or `source` (id or name) means.

    A database with one data source resolves to it. With several, `source`
    picks one; without it the call refuses and lists them rather than guess.
    Returns the data source object plus `database` (its container, when read).
    """
    target = parse_target(given)
    try:
        found = call("GET", f"databases/{target.id}")
    except NotionError as error:
        if error.kind == "invalid":
            # Notion answers a page id here with a validation error ("is a page, not a database"):
            # a row number from a list of pages or rows. Say which page it is and where databases are.
            try:
                page_ = call("GET", f"pages/{target.id}")
            except NotionError:
                raise error from None
            raise NotionError(f"{title_of(page_)} is a page" + (" (a row of a database)" if parent_of(page_)["type"]
                              == "data_source" else "") + ", not a database. A row number means the last list "
                              "shown; list the databases again", "co notion pages --type database",
                              "invalid") from None
        if error.kind != "not_found":
            raise
        try:
            return {**call("GET", f"data_sources/{target.id}"), "database": None}
        except NotionError as second:
            if second.kind == "not_found":
                raise error from None
            raise
    sources = found.get("data_sources")
    if sources is None:   # an older API version: the database is its own source
        return {**found, "object": "data_source", "database": found}
    if source:
        digits = re.sub(r"[^0-9a-fA-F]", "", source)
        wanted = _dashed(digits) if len(digits) == 32 else ""
        picked = [s for s in sources if (wanted and _dashed(s.get("id", "")) == wanted)
                  or (s.get("name") or "").casefold() == source.strip().casefold()]
        if not picked:
            raise NotionError(f"No data source {source!r} in {title_of(found)}. It has: "
                              + ", ".join(f"{s.get('name') or '(untitled)'} ({s['id']})" for s in sources),
                              f"co notion columns {found['id']}", "ambiguous")
        chosen = picked[0]
    elif len(sources) == 1:
        chosen = sources[0]
    elif not sources:
        raise NotionError(f"{title_of(found)} has no data source this key can read",
                          f"co notion page {found['id']}", "not_found")
    else:
        raise NotionError(f"{title_of(found)} has {len(sources)} data sources: "
                          + ", ".join(f"{s.get('name') or '(untitled)'} ({s['id']})" for s in sources)
                          + ". Pick one with --source", f"co notion columns {found['id']} --source {sources[0]['id']}",
                          "ambiguous")
    return {**call("GET", f"data_sources/{chosen['id']}"), "database": found}


# Notion stops any one query at this many results: has_more and next_cursor turn false and the
# response says request_status.type == "incomplete". Following the cursor never gets past it.
QUERY_RESULT_LIMIT = 10_000


def query(ds_id: str, *, filter: dict | None = None, sorts: list | None = None, first: int = 20,
          cursor: str = "", only: list | None = None) -> tuple[list, str, bool]:
    """(rows, next_cursor or '', capped) from one data source, at most `first` rows.

    `capped` is Notion's own word that the query hit its result limit: there
    are more matching rows, but no cursor reaches them. A caller must narrow the
    query (a filter, a time window), never treat the listing as complete.
    `only` limits the properties returned.
    """
    body: dict = {"page_size": min(first, 100)}
    if filter:
        body["filter"] = filter
    if sorts:
        body["sorts"] = sorts
    if cursor:
        body["start_cursor"] = cursor
    params = {"filter_properties": only} if only is not None else None
    data = call("POST", f"data_sources/{ds_id}/query", body, params=params)
    capped = (data.get("request_status") or {}).get("type") == "incomplete"
    after = (data.get("next_cursor") or "") if data.get("has_more") else ""
    return data.get("results", [])[:first], after, capped


WRITABLE = ("title", "rich_text", "number", "select", "status", "multi_select", "date", "checkbox",
            "url", "email", "phone_number")
# Read but never written by `add`/`update`: they need ids, are computed, or are owned by Notion.
READ_ONLY = ("people", "relation", "files", "formula", "rollup", "created_time", "created_by",
             "last_edited_time", "last_edited_by", "unique_id", "verification", "button", "place")


def columns(ds: dict) -> list:
    """A data source's properties: {name, id, type, options, settable}, title first, then by name."""
    found = []
    for name, prop in (ds.get("properties") or {}).items():
        kind = prop.get("type", "")
        options = [o.get("name", "") for o in (prop.get(kind) or {}).get("options", [])] \
            if kind in ("select", "status", "multi_select") else []
        found.append({"name": name, "id": prop.get("id", ""), "type": kind, "options": options,
                      "settable": kind in WRITABLE})
    return sorted(found, key=lambda c: (c["type"] != "title", c["name"].lower()))


# -- reads: property values -----------------------------------------------

def _person(user: dict) -> dict:
    return {"id": user.get("id", ""), "name": user.get("name"),
            "email": ((user.get("person") or {}).get("email"))}


def _file(entry: dict) -> dict:
    kind = entry.get("type", "")
    body = entry.get(kind) or {}
    return {"name": entry.get("name") or "", "hosted": kind in ("file", "file_upload"), "url": body.get("url", ""),
            "expires": body.get("expiry_time", "")}


def property_value(prop: dict):
    """One property's value as JSON, faithful to its type: 0, false and null survive, ids are kept."""
    kind = prop.get("type")
    value = prop.get(kind)
    if kind in ("title", "rich_text"):
        return plain(value)
    if kind in ("select", "status"):
        return value.get("name") if value else None
    if kind == "multi_select":
        return [v.get("name", "") for v in value or []]
    if kind == "date":
        return {"start": value.get("start"), "end": value.get("end"), "time_zone": value.get("time_zone")} \
            if value else None
    if kind == "people":
        return [_person(p) for p in value or []]
    if kind in ("created_by", "last_edited_by"):
        return _person(value or {})
    if kind == "relation":
        return [r.get("id", "") for r in value or []]
    if kind == "files":
        return [_file(f) for f in value or []]
    if kind == "formula":
        inner = value or {}
        return inner.get(inner.get("type"))
    if kind == "rollup":
        inner = value or {}
        rolled = inner.get(inner.get("type"))
        if inner.get("type") == "array":
            return [property_value(item) for item in rolled or []]
        return rolled
    if kind == "unique_id":
        return f"{(value or {}).get('prefix') or ''}{'-' if (value or {}).get('prefix') else ''}{(value or {}).get('number')}"
    if kind == "verification":
        return (value or {}).get("state")
    return value   # number, checkbox, url, email, phone_number, timestamps: as Notion gave them


def property_text(prop: dict) -> str:
    """One property value as short text, for tables and page headers."""
    value = property_value(prop)
    kind = prop.get("type")
    if value is None or value == "" or value == []:
        return ""
    if kind == "checkbox":
        return "yes" if value else "no"
    if kind == "date":
        return value["start"] + (f" → {value['end']}" if value.get("end") else "")
    if kind == "people":
        return ", ".join(p.get("name") or p.get("id", "") for p in value)
    if kind in ("created_by", "last_edited_by"):
        return value.get("name") or value.get("id", "")
    if kind == "relation":
        return f"{len(value)} linked"
    if kind == "files":
        return ", ".join(f.get("name") or "file" for f in value)
    if isinstance(value, list):
        return ", ".join(str(v) for v in value)
    return str(value)


def _property_items(page_id_: str, prop_id: str) -> list:
    """Every item of a paginated property (relation, people, long text) via the property-item endpoint."""
    items, cursor = [], ""
    while True:
        params = {"page_size": 100, **({"start_cursor": cursor} if cursor else {})}
        data = call("GET", f"pages/{page_id_}/properties/{prop_id}", params=params)
        if data.get("object") != "list":
            return [data]
        items += data.get("results", [])
        if not data.get("has_more"):
            return items
        cursor = data.get("next_cursor") or ""


# A page object returns at most 25 references in these; more means the list was cut.
_REFERENCE_CAP = 25


def full_properties(obj: dict) -> dict:
    """{name: {id, type, value, complete}} with lists past Notion's 25-reference cap fetched in full."""
    out = {}
    for name, prop in (obj.get("properties") or {}).items():
        kind = prop.get("type")
        complete = True
        value = property_value(prop)
        value_list = prop.get(kind) if isinstance(prop.get(kind), list) else None
        cut = prop.get("has_more") or (value_list is not None and kind in ("relation", "people", "title", "rich_text")
                                       and len(value_list) >= _REFERENCE_CAP)
        if cut and not (prop.get("id") and obj.get("id")):
            complete = False
        elif cut:
            items = _property_items(obj["id"], prop["id"])
            if kind == "relation":
                value = [i.get("relation", {}).get("id", "") for i in items]
            elif kind == "people":
                value = [_person(i.get("people") or {}) for i in items]
            elif kind in ("title", "rich_text"):
                value = "".join(plain([i.get(kind) or {}]) for i in items)
        out[name] = {"id": prop.get("id", ""), "type": kind, "value": value, "complete": complete}
    return out


# -- reads: block tree -----------------------------------------------------

MEDIA = ("image", "file", "pdf", "video", "audio")
# Blocks whose text is in rich_text and whose type needs only a prefix.
_PREFIX = {"paragraph": "", "heading_1": "# ", "heading_2": "## ", "heading_3": "### ",
           "heading_4": "#### ", "bulleted_list_item": "- ", "numbered_list_item": "1. ", "quote": "> ",
           "callout": "> ", "toggle": "▸ ", "template": ""}
# Read as a line with no children of their own that matter here.
_KNOWN = {"divider", "to_do", "code", "child_page", "child_database", "table", "table_row", "bookmark",
          "embed", "link_preview", "equation", "column_list", "column", "synced_block", "link_to_page",
          "table_of_contents", "breadcrumb", *MEDIA, *_PREFIX}


def children(block_id: str, limit: int = 1000) -> tuple[list, bool]:
    """A block's direct children in order, following Notion's cursor; (blocks, complete)."""
    found, cursor = [], ""
    while len(found) < limit:
        params = {"page_size": min(100, limit - len(found)), **({"start_cursor": cursor} if cursor else {})}
        data = call("GET", f"blocks/{block_id}/children", params=params)
        found.extend(data.get("results", []))
        if not data.get("has_more"):
            return found[:limit], len(found) <= limit
        cursor = data.get("next_cursor") or ""
    return found[:limit], False


def media(block: dict) -> dict:
    """An image, file, PDF, video or audio block as a descriptor: where it is, whether Notion hosts it, until when."""
    kind = block.get("type", "")
    body = block.get(kind) or {}
    source = body.get("type", "")
    inner = body.get(source) or {}
    return {"block": block.get("id", ""), "kind": kind, "name": body.get("name") or plain(body.get("caption")) or kind,
            "hosted": source in ("file", "file_upload"), "url": inner.get("url", ""),
            "expires": inner.get("expiry_time", "")}


def block_tree(root_id: str, *, max_blocks: int = DEFAULT_BLOCK_LIMIT, max_depth: int = DEFAULT_DEPTH) -> tuple[list, dict]:
    """Every block under `root_id`, depth first, as (depth, block); plus what the read covered.

    Coverage says what is missing rather than leaving it out silently: blocks
    past `max_blocks`, children below `max_depth`, block types this reader does
    not render, and every media file and child page/database found.
    """
    flat, coverage = [], {"blocks": 0, "complete": True, "stopped": [], "unsupported": {}, "media": [],
                          "child_pages": [], "child_databases": []}

    def walk(block_id: str, depth: int) -> None:
        if len(flat) >= max_blocks:
            coverage["complete"] = False
            return
        found, complete = children(block_id, max_blocks - len(flat))
        if not complete:
            coverage["complete"] = False
            coverage["stopped"].append(f"more than {max_blocks} blocks; the rest were not read")
        for block in found:
            if len(flat) >= max_blocks:
                coverage["complete"] = False
                break
            flat.append((depth, block))
            kind = block.get("type", "")
            if kind not in _KNOWN:
                coverage["unsupported"][kind] = coverage["unsupported"].get(kind, 0) + 1
            if kind in MEDIA:
                coverage["media"].append(media(block))
            if kind == "child_page":
                coverage["child_pages"].append({"id": block["id"], "title": (block.get(kind) or {}).get("title", "")})
                continue
            if kind == "child_database":
                coverage["child_databases"].append({"id": block["id"],
                                                    "title": (block.get(kind) or {}).get("title", "")})
                continue
            if block.get("has_children"):
                if depth + 1 >= max_depth:
                    coverage["complete"] = False
                    coverage["stopped"].append(f"children of a {kind} block deeper than {max_depth} levels")
                    continue
                walk(block["id"], depth + 1)

    walk(root_id, 0)
    coverage["blocks"] = len(flat)
    if not coverage["complete"] and not coverage["stopped"]:
        coverage["stopped"].append(f"stopped at {max_blocks} blocks")
    coverage["stopped"] = list(dict.fromkeys(coverage["stopped"]))
    return flat, coverage


def block_text(block: dict) -> str:
    kind = block.get("type", "")
    body = block.get(kind) or {}
    if kind == "divider":
        return "---"
    if kind == "child_page":
        return f"[page] {body.get('title', '')} ({block['id']})"
    if kind == "child_database":
        return f"[database] {body.get('title', '')} ({block['id']})"
    if kind == "to_do":
        return f"- [{'x' if body.get('checked') else ' '}] {markdown(body.get('rich_text'))}"
    if kind == "code":
        return f"```{body.get('language', '')}\n{plain(body.get('rich_text'))}\n```"
    if kind == "table_row":
        return "| " + " | ".join(markdown(cell) for cell in body.get("cells", [])) + " |"
    if kind == "table":
        return ""   # its rows follow
    if kind in MEDIA:
        found = media(block)
        where = "hosted by Notion" + (f", link expires {found['expires']}" if found["expires"] else "") \
            if found["hosted"] else found["url"]
        return f"[{kind}: {found['name']}] ({where})"
    if kind in ("bookmark", "embed", "link_preview"):
        return f"[{kind}] {body.get('url', '')}"
    if kind == "equation":
        return f"$${body.get('expression', '')}$$"
    if kind == "link_to_page":
        target = body.get(body.get("type", "")) or ""
        return f"[link to {body.get('type', 'page').replace('_id', '')}] ({target})"
    if kind in ("column_list", "column", "synced_block", "table_of_contents", "breadcrumb"):
        return ""
    if "rich_text" in body:
        return _PREFIX.get(kind, "") + markdown(body.get("rich_text"))
    return f"[unsupported block: {kind}]"


def render(flat: list) -> str:
    """The tree as indented Markdown-ish text; an empty line is never invented for a layout block."""
    lines = []
    for depth, block in flat:
        text = block_text(block)
        if text == "":
            continue
        indent = "  " * depth
        lines.append("\n".join(indent + line for line in text.splitlines()) if text else indent)
    return "\n".join(lines)


def read_page(given: str, *, max_blocks: int = DEFAULT_BLOCK_LIMIT, max_depth: int = DEFAULT_DEPTH) -> dict:
    """A page, whole as far as the limits allow: row, typed properties, rendered content, coverage."""
    target = parse_target(given)
    obj = call("GET", f"pages/{target.id}")
    flat, coverage = block_tree(obj["id"], max_blocks=max_blocks, max_depth=max_depth)
    properties = full_properties(obj)
    for name, prop in properties.items():
        if prop["type"] == "files":
            coverage["media"] += [{"block": "", "kind": "property", "name": f.get("name") or name, "hosted": f["hosted"],
                                   "url": f["url"], "expires": f["expires"], "property": name} for f in prop["value"]]
    return {**row(obj), "properties": properties, "content": render(flat), "coverage": coverage,
            "anchor": target.block, "created": obj.get("created_time", ""),
            "created_by": (obj.get("created_by") or {}).get("id", ""), "raw": obj, "blocks": flat}


# -- query filters and sorts -----------------------------------------------

_WHERE = re.compile(r"^(.+?)\s*(!=|>=|<=|=|~|>|<)\s*(.*)$", re.S)
# Notion's operator name per (type family, our operator).
_TEXT_OPS = {"=": "equals", "!=": "does_not_equal", "~": "contains"}
_NUMBER_OPS = {"=": "equals", "!=": "does_not_equal", ">": "greater_than", "<": "less_than",
               ">=": "greater_than_or_equal_to", "<=": "less_than_or_equal_to"}
_DATE_OPS = {"=": "equals", ">": "after", "<": "before", ">=": "on_or_after", "<=": "on_or_before"}
_TIMESTAMPS = {"edited": "last_edited_time", "created": "created_time"}


_TRUE = {"yes", "true", "1", "y", "on", "x"}
_FALSE = {"no", "false", "0", "n", "off"}
_DATE = re.compile(r"\d{4}-\d{2}-\d{2}(T[\d:.+\-Z]+)?")


def _column(ds: dict, name: str) -> dict:
    by_name = {c["name"].casefold(): c for c in columns(ds)}
    found = by_name.get(name.strip().casefold())
    if found is None:
        raise NotionError(f"No column {name.strip()!r}. Columns: " + ", ".join(c["name"] for c in columns(ds)),
                          f"co notion columns {ds['id']}", "invalid")
    return found


def _option(column: dict, given: str, ds_id: str) -> str:
    for name in column["options"]:
        if name.casefold() == given.strip().casefold():
            return name
    valid = ", ".join(column["options"]) or "none"
    raise NotionError(f"No {column['name']} option {given!r}. Valid: {valid}", f"co notion columns {ds_id}",
                      "invalid")


def _number(column: dict, raw: str, ds_id: str):
    try:
        number = float(raw)
    except ValueError:
        raise NotionError(f"{column['name']} takes a number, not {raw!r}", f"co notion columns {ds_id}",
                          "invalid") from None
    return int(number) if number.is_integer() else number


def _checkbox(column: dict, raw: str, ds_id: str) -> bool:
    if raw.strip().casefold() not in _TRUE | _FALSE:
        raise NotionError(f"{column['name']} takes yes or no, not {raw!r}", f"co notion columns {ds_id}", "invalid")
    return raw.strip().casefold() in _TRUE


def _condition(ds: dict, clause: str) -> dict:
    match = _WHERE.match(clause.strip())
    if not match:
        raise NotionError(f"--where takes Column=value (or != ~ > < >= <=), not {clause!r}",
                          "co notion db --help", "invalid")
    name, op, raw = match[1].strip(), match[2], match[3].strip()
    if name.casefold() in _TIMESTAMPS:
        if op not in _DATE_OPS or not re.fullmatch(r"\d{4}-\d{2}-\d{2}(T[\d:.+\-Z]+)?", raw):
            raise NotionError(f"{name} takes = > < >= <= and a date like 2026-10-01", "co notion db --help", "invalid")
        stamp = _TIMESTAMPS[name.casefold()]
        return {"timestamp": stamp, stamp: {_DATE_OPS[op]: raw}}
    column = _column(ds, name)
    kind, ds_id = column["type"], ds["id"]
    refuse = NotionError(f"{column['name']} ({kind}) does not take {op}", f"co notion columns {ds_id}", "invalid")
    if kind in ("title", "rich_text", "url", "email", "phone_number"):
        if op not in _TEXT_OPS:
            raise refuse
        if raw == "" and op in ("=", "!="):
            return {"property": column["name"], kind: {"is_empty" if op == "=" else "is_not_empty": True}}
        return {"property": column["name"], kind: {_TEXT_OPS[op]: raw}}
    if kind == "number":
        if op not in _NUMBER_OPS:
            raise refuse
        if raw == "" and op in ("=", "!="):
            return {"property": column["name"], "number": {"is_empty" if op == "=" else "is_not_empty": True}}
        number = _number(column, raw, ds_id)
        return {"property": column["name"], "number": {_NUMBER_OPS[op]: number}}
    if kind in ("select", "status"):
        if op not in ("=", "!="):
            raise refuse
        if raw == "":
            return {"property": column["name"], kind: {"is_empty" if op == "=" else "is_not_empty": True}}
        return {"property": column["name"], kind: {_TEXT_OPS[op]: _option(column, raw, ds_id)}}
    if kind == "multi_select":
        if op not in ("=", "~", "!="):
            raise refuse
        operator = "does_not_contain" if op == "!=" else "contains"
        return {"property": column["name"], kind: {operator: _option(column, raw, ds_id)}}
    if kind == "checkbox":
        if op not in ("=", "!="):
            raise refuse
        value = _checkbox(column, raw, ds_id)
        return {"property": column["name"], "checkbox": {"equals" if op == "=" else "does_not_equal": value}}
    if kind == "date":
        if op not in _DATE_OPS:
            raise refuse
        if raw == "" and op == "=":
            return {"property": column["name"], "date": {"is_empty": True}}
        if not _DATE.fullmatch(raw):
            raise NotionError(f"{column['name']} takes a date like 2026-10-14, not {raw!r}",
                              f"co notion columns {ds_id}", "invalid")
        return {"property": column["name"], "date": {_DATE_OPS[op]: raw}}
    raise NotionError(f"{column['name']} is a {kind} column; co notion db cannot filter on it",
                      f"co notion columns {ds_id}", "invalid")


def build_filter(ds: dict, clauses: list) -> dict | None:
    """--where clauses, all of which must hold, as a Notion filter checked against the real schema."""
    conditions = [_condition(ds, clause) for clause in clauses]
    if not conditions:
        return None
    return conditions[0] if len(conditions) == 1 else {"and": conditions}


def build_sorts(ds: dict, keys: list) -> list:
    """--sort Column (ascending) / -Column (descending); `edited` and `created` sort by those timestamps."""
    sorts = []
    for key in keys:
        direction = "descending" if key.startswith("-") else "ascending"
        name = key.lstrip("-+").strip()
        if name.casefold() in _TIMESTAMPS:
            sorts.append({"timestamp": _TIMESTAMPS[name.casefold()], "direction": direction})
        else:
            sorts.append({"property": _column(ds, name)["name"], "direction": direction})
    return sorts



# -- writes: text to blocks -----------------------------------------------

def _units(text: str) -> int:
    return len(text.encode("utf-16-le")) // 2


def split_text(text: str, limit: int = MAX_TEXT) -> list:
    """Text in pieces of at most `limit` UTF-16 code units — Notion's measure — never splitting a character."""
    pieces, current, size = [], [], 0
    for char in text:
        width = 2 if ord(char) > 0xFFFF else 1
        if size + width > limit:
            pieces.append("".join(current))
            current, size = [], 0
        current.append(char)
        size += width
    if current or not pieces:
        pieces.append("".join(current))
    return pieces


def rich(text: str) -> list:
    """Rich-text items for `text`, each within 2000 units; more than Notion's 100 items is refused, never cut."""
    pieces = split_text(text)
    if len(pieces) > MAX_RICH_ITEMS:
        raise NotionError(f"One value or line is {_units(text):,} characters; Notion takes at most "
                          f"{MAX_TEXT * MAX_RICH_ITEMS:,} in one block or property. Split it", "co notion --help",
                          "invalid")
    return [{"type": "text", "text": {"content": piece}} for piece in pieces]


def _block(kind: str, text: str, **extra) -> dict:
    return {"object": "block", "type": kind, kind: {"rich_text": rich(text), **extra}}


LINE = [(re.compile(r"^(#{1,3})\s+(.*)$"), lambda m: _block(f"heading_{len(m[1])}", m[2])),
        (re.compile(r"^[-*]\s+\[([ xX])\]\s+(.*)$"), lambda m: _block("to_do", m[2], checked=m[1] != " ")),
        (re.compile(r"^[-*]\s+(.*)$"), lambda m: _block("bulleted_list_item", m[1])),
        (re.compile(r"^\d+[.)]\s+(.*)$"), lambda m: _block("numbered_list_item", m[1])),
        (re.compile(r"^>\s?(.*)$"), lambda m: _block("quote", m[1])),
        (re.compile(r"^(?:---+|\*\*\*+)$"), lambda m: {"object": "block", "type": "divider", "divider": {}})]


def text_blocks(text: str) -> list:
    """Markdown-ish text as Notion blocks.

    `#`/`##`/`###` headings, `- ` bullets, `1. ` numbers, `- [ ]` to-dos, `> `
    quotes, `---` dividers and ``` fences become those blocks; other lines join
    into paragraphs, split at blank lines. Inline marks (**, `, links) stay as
    typed. Nothing is dropped: an over-long paragraph is split into several.
    """
    blocks, paragraph, fence, code = [], [], None, []

    def flush():
        if paragraph:
            joined = "\n".join(paragraph)
            for start in range(0, len(joined), MAX_TEXT * MAX_RICH_ITEMS // 2):
                blocks.append(_block("paragraph", joined[start:start + MAX_TEXT * MAX_RICH_ITEMS // 2]))
            paragraph.clear()

    for line in text.replace("\r\n", "\n").split("\n"):
        if fence is not None:
            if line.strip().startswith("```"):
                blocks.append(_block("code", "\n".join(code), language=fence or "plain text"))
                fence, code = None, []
            else:
                code.append(line)
            continue
        stripped = line.strip()
        if stripped.startswith("```"):
            flush()
            fence = stripped[3:].strip()
            continue
        if not stripped:
            flush()
            continue
        for pattern, make in LINE:
            match = pattern.match(stripped)
            if match:
                flush()
                blocks.append(make(match))
                break
        else:
            paragraph.append(line.rstrip())
    flush()
    if fence is not None:   # an unclosed fence keeps its text, as code
        blocks.append(_block("code", "\n".join(code), language=fence or "plain text"))
    return [part for block in blocks for part in _fit(block)]


def preview_text(blocks: list) -> str:
    """The blocks that will be sent, rendered the way `co notion page` will show them afterwards."""
    return render([(0, block) for block in blocks])


# One block's share of a request, leaving room for the envelope around the children.
BLOCK_LIMIT_BYTES = MAX_PAYLOAD_BYTES - 2_000


def _fit(block: dict) -> list:
    """A block small enough to send alone, or the same block split into consecutive ones of its type.

    Splitting happens when the text is made into blocks, so the preview shows
    exactly the blocks that will be sent. A block with no text to divide and
    still too large is refused rather than sent to be rejected.
    """
    if weight(block) <= BLOCK_LIMIT_BYTES:
        return [block]
    kind = block["type"]
    body = block.get(kind) or {}
    items = body.get("rich_text") or []
    if len(items) < 2:
        raise NotionError(f"One {kind} block is {weight(block):,} bytes as JSON, over Notion's request size. "
                          "Nothing was sent. Split the text", "co notion --help", "invalid")
    parts, current = [], []
    for item in items:
        trial = {**block, kind: {**body, "rich_text": current + [item]}}
        if current and weight(trial) > BLOCK_LIMIT_BYTES:
            parts.append(current)
            current = []
        current.append(item)
    parts.append(current)
    return [{**block, kind: {**body, "rich_text": part}} for part in parts]


def batches(blocks: list, *, first_budget: int = MAX_PAYLOAD_BYTES) -> list:
    """Blocks in requests Notion accepts: at most 100 each and under the byte cap.

    Sizes are measured as \\u-escaped JSON, the larger of the two encodings httpx
    versions use, so CJK text stays under the cap whichever one sends it.
    `first_budget` is the room the first request has after what else it carries
    (a new page's properties). A block too large to send alone is refused.
    """
    out, current, size, budget = [], [], 0, first_budget
    for block in blocks:
        block_weight = weight(block)
        if block_weight > BLOCK_LIMIT_BYTES:
            raise NotionError(f"One {block.get('type')} block is {block_weight:,} bytes as JSON, over Notion's "
                              "request size. Nothing was sent", "co notion --help", "invalid")
        if not out and not current and block_weight > budget:
            # The first request has no room for even this block beside what it carries (a large
            # title): it goes empty, and the block opens the next request with a full budget.
            out.append([])
            budget = MAX_PAYLOAD_BYTES
        if current and (len(current) >= MAX_BLOCKS or size + block_weight > budget):
            out.append(current)
            current, size, budget = [], 0, MAX_PAYLOAD_BYTES
        current.append(block)
        size += block_weight
    if current:
        out.append(current)
    return out


def append(target_id: str, blocks: list, *, start_at: int = 0) -> int:
    """Append blocks[start_at:] to a page in batches; return how many were added in total (start_at included).

    Each batch is confirmed before the next is sent. If one fails, NotionError
    says how many blocks are confirmed and how to resume from the first one not.
    """
    written = start_at
    for part in batches(blocks[start_at:]):
        try:
            call("PATCH", f"blocks/{target_id}/children", {"children": part})
        except NotionError as error:
            unknown = error.kind == "unknown_outcome"
            raise NotionError(
                f"{written} of {len(blocks)} blocks are confirmed on the page; the next batch "
                + ("may or may not have been written" if unknown else f"failed: {error}"),
                f"co notion page {target_id}", "partial",
                {"page": target_id, "confirmed_blocks": written, "total_blocks": len(blocks),
                 "next_start": written, "batch_outcome": "unknown" if unknown else "failed"}) from None
        written += len(part)
    return written


def create_page(parent_id: str, title: str, blocks: list, *, data_source_id: str = "",
                properties: dict | None = None) -> dict:
    """A new page under a page (or a row in a data source), its first batch in the create call, the rest appended."""
    parent = ({"type": "data_source_id", "data_source_id": data_source_id} if data_source_id
              else {"type": "page_id", "page_id": parent_id})
    envelope = {"parent": parent, "properties": properties or {"title": {"title": rich(title)}}}
    room = REQUEST_LIMIT_BYTES - 2_000 - weight(envelope)
    if room <= 0:
        raise NotionError(f"The title and properties alone are {weight(envelope):,} bytes as JSON, over Notion's "
                          "request size. Nothing was sent. Shorten them", "co notion --help", "invalid")
    parts = batches(blocks, first_budget=min(MAX_PAYLOAD_BYTES, room))
    body = {**envelope, "children": parts[0] if parts else []}
    created = call("POST", "pages", body)
    first = len(parts[0]) if parts else 0
    if len(parts) > 1:
        try:
            append(created["id"], blocks, start_at=first)
        except NotionError as error:
            error.detail.update(created=created["id"], url=created.get("url", ""))
            error.args = (f"The page was created ({created.get('url') or created['id']}), but " + str(error),)
            raise
    return created


# -- writes: properties ----------------------------------------------------

def write_value(column: dict, raw: str, ds_id: str) -> dict:
    """One `Name=value` as the property object Notion takes, checked against the column's type and options."""
    kind, name = column["type"], column["name"]
    if kind not in WRITABLE:
        raise NotionError(f"{name} is a {kind} column; co notion cannot set it", f"co notion columns {ds_id}",
                          "invalid")
    if kind in ("title", "rich_text"):
        return {kind: rich(raw)}
    if kind == "number":
        try:
            number = float(raw)
        except ValueError:
            raise NotionError(f"{name} takes a number, not {raw!r}", f"co notion columns {ds_id}", "invalid") from None
        return {"number": int(number) if number.is_integer() else number}
    if kind in ("select", "status"):
        return {kind: {"name": _option(column, raw, ds_id)}}
    if kind == "multi_select":
        picked = [_option(column, part, ds_id) for part in raw.split(",") if part.strip()]
        return {"multi_select": [{"name": p} for p in dict.fromkeys(picked)]}
    if kind == "date":
        start, _, end = raw.strip().partition("..")
        for value in filter(None, (start, end)):
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}(T[\d:.+\-Z]+)?", value):
                raise NotionError(f"{name} takes a date like 2026-10-14 (or 2026-10-14..2026-10-20), not {raw!r}",
                                  f"co notion columns {ds_id}", "invalid")
        return {"date": {"start": start, **({"end": end} if end else {})}}
    if kind == "checkbox":
        if raw.strip().casefold() not in _TRUE | _FALSE:
            raise NotionError(f"{name} takes yes or no, not {raw!r}", f"co notion columns {ds_id}", "invalid")
        return {"checkbox": raw.strip().casefold() in _TRUE}
    return {kind: raw.strip()}   # url, email, phone_number


EMPTY = {"title": {"title": []}, "rich_text": {"rich_text": []}, "number": {"number": None},
         "select": {"select": None}, "status": None, "multi_select": {"multi_select": []},
         "date": {"date": None}, "checkbox": {"checkbox": False}, "url": {"url": None},
         "email": {"email": None}, "phone_number": {"phone_number": None}}


def _split_assignment(assignment: str, flag: str, ds: dict) -> tuple[str, str]:
    name, sep, raw = assignment.partition("=")
    if not sep:
        raise NotionError(f"{flag} takes Name=value, not {assignment!r}", f"co notion columns {ds['id']}", "invalid")
    return name, raw


def row_properties(ds: dict, title: str, assignments: list) -> tuple[dict, dict]:
    """A new row's properties from its title and `Name=value` strings; (properties, shown)."""
    title_column = next((c for c in columns(ds) if c["type"] == "title"), None)
    if title_column is None:
        raise NotionError("This data source has no title column", f"co notion columns {ds['id']}", "invalid")
    properties = {title_column["name"]: write_value(title_column, title, ds["id"])}
    shown = {title_column["name"]: title}
    for assignment in assignments:
        name, raw = _split_assignment(assignment, "--set", ds)
        column = _column(ds, name)
        if column["type"] == "title":
            raise NotionError(f"{column['name']} is the title; give it as the second argument, not --set",
                              "co notion add --help", "invalid")
        properties[column["name"]] = write_value(column, raw, ds["id"])
        shown[column["name"]] = raw
    return properties, shown


def property_changes(ds: dict, current: dict, *, set_: list = (), clear: list = (), add: list = (),
                     remove: list = ()) -> tuple[dict, dict]:
    """The PATCH for exactly the named fields, and {column: "old → new"} for the preview.

    --set replaces, --clear empties, --add/--remove change a multi_select's
    options and leave the others. Every value is checked first; a field named
    twice is refused rather than resolved by order.
    """
    properties, shown, touched = {}, {}, set()

    def claim(column: dict) -> None:
        if column["name"] in touched:
            raise NotionError(f"{column['name']} is named twice; give each column once", "co notion update --help",
                              "invalid")
        touched.add(column["name"])

    def old(column: dict) -> str:
        prop = current.get(column["name"])
        return property_text(prop) if prop else ""

    for assignment in set_:
        name, raw = _split_assignment(assignment, "--set", ds)
        column = _column(ds, name)
        claim(column)
        properties[column["name"]] = write_value(column, raw, ds["id"])
        shown[column["name"]] = f"{old(column) or '(empty)'} → {raw}"
    for name in clear:
        column = _column(ds, name)
        claim(column)
        if column["type"] not in WRITABLE or column["type"] in ("title", "status"):
            raise NotionError(f"{column['name']} ({column['type']}) cannot be cleared by co notion",
                              f"co notion columns {ds['id']}", "invalid")
        properties[column["name"]] = EMPTY[column["type"]]
        shown[column["name"]] = f"{old(column) or '(empty)'} → (empty)"
    changes: dict = {}
    for flag, entries in (("--add", add), ("--remove", remove)):
        for assignment in entries:
            name, raw = _split_assignment(assignment, flag, ds)
            column = _column(ds, name)
            if column["type"] != "multi_select":
                raise NotionError(f"{flag} changes a multi_select column; {column['name']} is {column['type']}. "
                                  "Use --set", "co notion update --help", "invalid")
            if column["name"] in touched:
                claim(column)   # already set or cleared: refused
            entry = changes.setdefault(column["name"], (column, [], []))
            entry[1 if flag == "--add" else 2].extend(
                _option(column, part, ds["id"]) for part in raw.split(",") if part.strip())
    for name, (column, added, removed) in changes.items():
        touched.add(name)
        before = property_value(current[name]) if name in current else []
        after = [v for v in before if v not in removed] + [v for v in dict.fromkeys(added) if v not in before]
        properties[name] = {"multi_select": [{"name": v} for v in after]}
        shown[name] = f"{', '.join(before) or '(empty)'} → {', '.join(after) or '(empty)'}"
    return properties, shown


def update_page(page_id_: str, properties: dict) -> dict:
    """PATCH exactly these properties. Values are absolute, so rerunning the same command sets the same values."""
    return call("PATCH", f"pages/{page_id_}", {"properties": properties})

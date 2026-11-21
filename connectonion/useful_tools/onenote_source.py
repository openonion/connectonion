"""Read-only, explicitly scoped OneNote collection for co rem.

Uses the Microsoft credential record and Outlook's refresh/retry implementation.
Graph traffic is GET-only; page media are described, never fetched. Source config
is an import declaration, not automatic registration with rem's runtime registry.
"""

import math
import time
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import quote, urlsplit

import httpx

from ..provider_credentials import ProviderCredentialError
from .adapter import AdapterResult, onenote_pages_to_records, media_ref, validate_record as contract_problems
from .onenote import TIMEOUT, _page_text
from .outlook import Outlook

READ_SCOPES = {"Notes.Read", "Notes.Read.All", "Notes.ReadWrite", "Notes.ReadWrite.All"}
MAX_PAGES = 1000
MAX_SELECTED = 1000
CONTENT_RETRIES = 2
MAX_CONTENT_RETRY_WAIT = 30
TRANSIENT_CONTENT_STATUSES = {429, 503, 504}


class InterruptedOneNoteImport(ProviderCredentialError):
    """A fatal credential failure with valid records collected before the stop."""

    def __init__(self, cause: ProviderCredentialError, partial_result: AdapterResult):
        super().__init__(cause.code, str(cause).split("\nNext:", 1)[0], cause.next_command, cause.status)
        self.partial_result = partial_result
        self.saved_results = {}


def _retry_delay(header: str | None, attempt: int) -> float:
    """Honor Retry-After seconds or HTTP-date; otherwise use exponential backoff."""
    if header:
        try:
            wait = float(header)
        except ValueError:
            try:
                wait = parsedate_to_datetime(header).timestamp() - time.time()
            except (TypeError, ValueError, OverflowError):
                return 2 ** attempt
        if math.isfinite(wait) and wait >= 0:
            return wait
    return 2 ** attempt


def _id(value: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > 2048:
        raise ValueError("A nonempty OneNote ID is required. List IDs with co onenote source.")
    return quote(value, safe="")


def _selected_ids(page_ids: list[str]) -> list[str]:
    selected = list(dict.fromkeys(page_ids))
    if not selected or len(selected) > MAX_SELECTED:
        raise ValueError(f"Select between 1 and {MAX_SELECTED} page IDs; use co onenote source pages.")
    for page_id in selected:
        _id(page_id)
    return selected


def _named(rows: list[dict], value: str, kind: str) -> dict:
    exact = [row for row in rows if row.get("id") == value]
    matches = exact or [row for row in rows if row.get("displayName") == value]
    if len(matches) != 1:
        raise ValueError(f"Unknown, inaccessible or ambiguous {kind}. "
                         "Use an ID from co onenote source notebooks/sections.")
    return matches[0]


class OneNoteSource:
    """Read-only source; existing broader Microsoft grants are accepted, never requested."""

    def __init__(self):
        # Do not instantiate Outlook's mail tools or require Mail scopes.
        self._graph = Outlook.__new__(Outlook)
        credentials = self._graph._credentials
        credentials.require_configured()
        if not credentials.scopes & READ_SCOPES:
            raise ProviderCredentialError(
                "missing_scope", "OneNote requires Notes.Read. Reconnect using the client's Microsoft flow. "
                "If consent still omits it, wait for client support (#1886); no separate Azure app is needed.",
                credentials.auth_command)
        self._graph._access_token = None
        self._account = None

    def _json(self, endpoint: str, **kwargs) -> dict:
        try:
            result = self._graph._request("GET", endpoint, timeout=TIMEOUT, **kwargs)
        except httpx.RequestError:
            raise ProviderCredentialError("unavailable", "Could not reach Microsoft OneNote. Retry the source command.",
                                          "co onenote source verify") from None
        except (TypeError, ValueError) as error:
            if isinstance(error, ProviderCredentialError):
                if error.code == "provider_unavailable":
                    raise ProviderCredentialError(error.code,
                        "Microsoft OneNote is unavailable; wait before retrying and honor Retry-After if provided.",
                        "co onenote source verify", status=error.status) from error
                raise
            raise ValueError("OneNote returned malformed metadata. Retry the source command.") from None
        if not isinstance(result, dict):
            raise ValueError("OneNote returned malformed metadata. Retry the source command.")
        return result

    def verify_connection(self) -> dict:
        """Verify the selected Microsoft account and OneNote access without exposing tokens."""
        if self._account is None:
            # /me requires User.Read, already granted by co auth microsoft.
            profile = self._json("/me", params={"$select": "id"})
            account = f"{Outlook.GRAPH_API_URL}/users/{_id(profile.get('id'))}"
            self._items("/me/onenote/notebooks", limit=1, params={"$top": 1, "$select": "id"})
            self._account = account
        return {"account": self._account, "read_only": True}

    def _items(self, endpoint: str, *, limit: int | None = None, params=None) -> tuple[list[dict], bool]:
        """Follow the exact collection's Graph nextLink, with loop and page guards."""
        rows, seen = [], set()
        collection = urlsplit(endpoint).path
        for _ in range(MAX_PAGES):
            if endpoint in seen:
                raise ValueError("OneNote pagination repeated a link; no complete result is available.")
            seen.add(endpoint)
            result = self._json(endpoint, **({"params": params} if params is not None else {}))
            params = None
            batch = result.get("value")
            if not isinstance(batch, list) or any(not isinstance(row, dict) or not row.get("id") for row in batch):
                raise ValueError("OneNote returned malformed pagination data. Retry the listing.")
            link = result.get("@odata.nextLink")
            rows.extend(batch)
            if limit is not None and len(rows) >= limit:
                return rows[:limit], bool(link or len(rows) > limit)
            if not link:
                return rows, False
            parsed = urlsplit(link) if isinstance(link, str) else None
            if (parsed is None or parsed.scheme != "https" or parsed.netloc != "graph.microsoft.com"
                    or parsed.fragment or parsed.path != "/v1.0" + collection):
                raise ValueError("OneNote pagination points outside the selected Graph collection; refused.")
            endpoint = parsed.path.removeprefix("/v1.0") + ("?" + parsed.query if parsed.query else "")
        raise ValueError("OneNote pagination exceeded its safety bound; no complete result is available.")

    def notebooks(self) -> list[dict]:
        """All accessible notebooks, including later result pages."""
        rows, _ = self._items("/me/onenote/notebooks", params={"$select": "id,displayName", "$top": 100})
        return [{"id": row["id"], "displayName": row.get("displayName") or "(untitled)"} for row in rows]

    def sections(self, notebook: str) -> list[dict]:
        """All sections within the chosen notebook, including nested section groups."""
        selected = _named(self.notebooks(), notebook, "notebook")
        pending = [f"/me/onenote/notebooks/{_id(selected['id'])}"]
        seen, rows = set(), []
        while pending:
            parent = pending.pop()
            if parent in seen or len(seen) >= MAX_PAGES:
                raise ValueError("OneNote section group pagination repeated or exceeded its safety bound.")
            seen.add(parent)
            sections, _ = self._items(parent + "/sections", params={"$select": "id,displayName", "$top": 100})
            rows.extend(sections)
            groups, _ = self._items(parent + "/sectionGroups", params={"$select": "id,displayName", "$top": 100})
            pending.extend(f"/me/onenote/sectionGroups/{_id(group['id'])}" for group in groups)
        return [{"id": row["id"], "displayName": row.get("displayName") or "(untitled)"} for row in rows]

    def scope(self, notebook: str, section: str) -> dict:
        selected = _named(self.notebooks(), notebook, "notebook")
        chosen = _named(self.sections(selected["id"]), section, "section")
        return {"notebook": selected["id"], "section": chosen["id"]}

    def pages(self, notebook: str, section: str, *, limit: int = 100) -> dict:
        """Bounded listing; explicitly report whether later pages remain."""
        if not isinstance(limit, int) or not 1 <= limit <= MAX_SELECTED:
            raise ValueError(f"Page limit must be between 1 and {MAX_SELECTED}.")
        scope = self.scope(notebook, section)
        rows, truncated = self._items(f"/me/onenote/sections/{_id(scope['section'])}/pages", limit=limit,
                                     params={"$top": min(limit, 100), "$select": "id,title,lastModifiedDateTime",
                                             "$orderby": "lastModifiedDateTime desc"})
        return {"pages": rows, "truncated": truncated, "limit": limit, "scope": scope}

    def selected_page(self, page_id: str, scope: dict) -> dict:
        """Read metadata only, rejecting pages outside the explicitly chosen scope."""
        page = self._json(f"/me/onenote/pages/{_id(page_id)}", params={"$expand": "parentNotebook,parentSection"})
        if (page.get("id") != page_id or (page.get("parentNotebook") or {}).get("id") != scope["notebook"]
                or (page.get("parentSection") or {}).get("id") != scope["section"]):
            raise ValueError("Page is outside the selected notebook/section or has malformed scope metadata.")
        return page

    def _content(self, page_id: str) -> str:
        """HTML GET with bounded transient retries and at most one auth refresh."""
        url = f"{Outlook.GRAPH_API_URL}/me/onenote/pages/{_id(page_id)}/content"
        try:
            response = self._content_response(url)
        except httpx.RequestError:
            raise ProviderCredentialError("unavailable", "Could not read the OneNote page. Check your network connection and retry the source command.",
                                          "co onenote source verify") from None
        if response.status_code != 200:
            code = {401: "reauth_required", 403: "permission_denied", 404: "not_found"}.get(response.status_code, "unavailable")
            if response.status_code == 403:
                raise ProviderCredentialError(code,
                    "OneNote page permission denied (HTTP 403). Check your account's read access to the selected page.",
                    "co onenote source pages --help", status=403)
            if response.status_code in TRANSIENT_CONTENT_STATUSES:
                raise ProviderCredentialError(code,
                    f"OneNote page unavailable (HTTP {response.status_code}); retries exhausted. "
                    "Wait before retrying the import; honor Retry-After if provided.",
                    "co onenote source sync --help", status=response.status_code)
            raise ProviderCredentialError(code, f"OneNote page unavailable (HTTP {response.status_code}).",
                                          (self._graph._credentials.auth_command if response.status_code == 401
                                           else "co onenote source pages --help"), status=response.status_code)
        if "text/html" not in response.headers.get("Content-Type", "").lower():
            raise ValueError("OneNote returned non-HTML page content; page skipped.")
        return response.text

    def _content_response(self, url: str) -> httpx.Response:
        """Only retry safe HTML GETs; the refresh does not reset the retry budget."""
        refreshed = False
        for attempt in range(CONTENT_RETRIES + 1):
            response = httpx.request("GET", url,
                headers={"Authorization": f"Bearer {self._graph._get_access_token()}"},
                timeout=TIMEOUT, follow_redirects=False)
            if response.status_code == 401 and not refreshed:
                refresh_token = self._graph._credentials.get("REFRESH_TOKEN")
                if not refresh_token:
                    # Let _content report the 401 and login recovery; do not
                    # attempt a broker refresh with an incomplete credential.
                    return response
                self._graph._access_token = self._graph._refresh_via_backend(refresh_token)
                refreshed = True
                response = httpx.request("GET", url,
                    headers={"Authorization": f"Bearer {self._graph._get_access_token()}"},
                    timeout=TIMEOUT, follow_redirects=False)
            if response.status_code not in TRANSIENT_CONTENT_STATUSES or attempt == CONTENT_RETRIES:
                return response
            wait = _retry_delay(response.headers.get("Retry-After"), attempt)
            if wait > MAX_CONTENT_RETRY_WAIT:
                raise ProviderCredentialError("unavailable",
                    f"OneNote page unavailable (HTTP {response.status_code}); Retry-After exceeds "
                    f"the {MAX_CONTENT_RETRY_WAIT}s automatic wait limit. Wait before retrying the import; "
                    "honor the server's Retry-After.", "co onenote source sync --help", status=response.status_code)
            time.sleep(wait)

    def collect(self, notebook: str, section: str, page_ids: list[str], *,
                resolved: tuple[dict, str] | None = None, unchanged=None) -> AdapterResult:
        """Import only explicit pages whose current parent matches the selected scope."""
        selected = _selected_ids(page_ids)
        scope, account = resolved or (self.scope(notebook, section), self.verify_connection()["account"])
        result = AdapterResult()
        for index, page_id in enumerate(selected):
            try:
                page = self.selected_page(page_id, scope)
                if unchanged and unchanged(page):
                    continue
                content = self._content(page_id)
                descriptors = media_metadata(content)
                page.update({"text": _page_text(content), "scope": scope,
                             "title": page.get("title") or "(untitled)",
                             "media": [media_ref(item["name"], item["mime_type"], item["size"])
                                       for item in descriptors],
                             "media_fetch_references": descriptors})
                if not ((page.get("links") or {}).get("oneNoteWebUrl") or {}).get("href") and not page.get("contentUrl"):
                    page["contentUrl"] = f"{Outlook.GRAPH_API_URL}/me/onenote/pages/{page_id}"
                adapted = onenote_pages_to_records([page], account)
                for record in adapted.records:
                    validate_record(record)
                result.records.extend(adapted.records)
                result.errors.update(adapted.errors)
            except ProviderCredentialError as error:
                if error.code in {"reauth_required", "not_configured", "incomplete_record", "record_changed"}:
                    if result.records:
                        for pending in selected[index:]:
                            result.errors[pending] = f"Not imported because OneNote authentication stopped: {error}"
                        raise InterruptedOneNoteImport(error, result) from error
                    raise
                result.errors[page_id] = str(error)
            except (ValueError, TypeError, AttributeError):
                result.errors[page_id] = "Page has invalid metadata, content or scope; relist with co onenote source pages."
        return result


def media_metadata(content: str) -> list[dict]:
    """Extract attachment/image descriptors only; HTML parsing performs no network I/O."""
    from bs4 import BeautifulSoup
    media = []
    for element in BeautifulSoup(content, "html.parser").find_all(["img", "object"]):
        image = element.name == "img"
        size = element.get("data-size")
        reference = element.get("data-fullres-src") or element.get("src" if image else "data") or ""
        # Do not persist embedded binary data, JavaScript, or query credentials.
        parsed = urlsplit(reference)
        reference = parsed._replace(query="", fragment="").geturl() if parsed.scheme == "https" else ""
        media.append({"kind": "image" if image else "attachment",
                      "name": element.get("alt" if image else "data-attachment") or "",
                      "mime_type": element.get("data-fullres-src-type" if image else "type") or element.get("data-src-type") or "",
                      "size": int(size) if isinstance(size, str) and size.isdigit() else None,
                      "status": "metadata_only", "fetch_reference": reference})
    return media


def validate_record(record: dict) -> None:
    """Validate through the same contract used by all source consumers."""
    problems = contract_problems(record)
    if problems:
        raise ValueError("Invalid shared record: " + "; ".join(problems))
    if record.get("source") != "onenote":
        raise ValueError("Invalid OneNote source record.")


def sync_onenote(source: OneNoteSource, notebook: str, section: str, page_ids: list[str], source_dir: Path,
                 *, mode: str = "daily", export_id: str | None = None, full: bool = False, lock_held: bool = False) -> dict:
    """Collect and persist an explicitly classified import; see onenote_storage."""
    from .onenote_storage import prepare_import
    source_dir = Path(source_dir)
    target = prepare_import(source_dir, mode, export_id)
    selected = _selected_ids(page_ids)
    if full and mode != "daily":
        raise ValueError("--full is only valid with daily imports; exports already read selected bodies.")
    return _sync(source, notebook, section, selected, source_dir, target, mode, export_id, full, lock_held)


def _sync(source, notebook, section, page_ids, source_dir, target, mode, export_id, full, lock_held=False):
    import shlex
    from ..environment import selected_command
    from .adapter import record_id
    from .onenote_scope import source_config
    from .onenote_storage import daily_checkpoint, page_version, restore_source_config, snapshot_version, write_import

    command = ["co", "onenote", "source", "sync", notebook, section, *page_ids,
               "--mode", mode, "--output", str(source_dir)]
    if export_id:
        command.extend(["--export-id", export_id])
    if full:
        command.append("--full")
    command = selected_command(shlex.join(command))

    scope = source.scope(notebook, section)
    account = source.verify_connection()["account"]
    declared = {**scope, "pages": sorted(set(page_ids))}
    source_config(source_dir, account, declared, command, daily=mode == "daily")
    versions, skipped = set(), set()
    if mode == "daily":
        versions = daily_checkpoint(source_dir, account, scope, full=full)

    def unchanged(page):
        stamp = page_version(page.get("lastModifiedDateTime"))
        if not full and stamp and (record_id("onenote", account, page["id"]), stamp) in versions:
            skipped.add(page["id"])
            return True
        return False

    options = {"resolved": (scope, account)}
    if mode == "daily":
        options["unchanged"] = unchanged
    interrupted = None
    try:
        result = source.collect(notebook, section, page_ids, **options)
    except InterruptedOneNoteImport as error:
        result = error.partial_result
        interrupted = error
    # Failed reads must not create a lock directory or suggest a successful import.
    if not result.records and not skipped:
        return {"records": 0, "written": 0, "skipped": 0, "errors": result.errors,
                "jsonl": None, "source_yaml": None, "mode": mode}
    from ..rem.files import maintenance_lock
    from .onenote_storage import prepare_import
    from contextlib import nullcontext
    with (nullcontext() if lock_held else maintenance_lock(source_dir)):
        # Collection happens outside the writer lock. Recheck ownership and all
        # committed versions here so concurrent imports cannot overwrite/double-write.
        target = prepare_import(source_dir, mode, export_id)
        source_config(source_dir, account, declared, command, daily=mode == "daily")
        if mode == "daily":
            versions = daily_checkpoint(source_dir, account, scope, full=full)
        fresh = []
        for record in result.records:
            if snapshot_version(record, full=full) in versions:
                skipped.add(record["external_id"])
            else:
                fresh.append(record)
        result.records = fresh
        if fresh:
            summary = write_import(result, source_dir, target, declared, mode, export_id, command)
            summary["skipped"] += len(skipped)
        else:
            summary = {"records": 0, "written": 0, "skipped": len(skipped), "errors": result.errors,
                       "jsonl": None, "source_yaml": None, "mode": mode}
            if skipped:
                summary["source_yaml"] = str(restore_source_config(source_dir, account, declared, command))
    if interrupted is not None:
        retry = "After co auth microsoft, retry the same notebook/section/page selection "
        retry += ("with a new --export-id; the original export is preserved."
                  if mode == "export" else "using the same --output; already stored versions will be skipped.")
        summary["note"] = " ".join(part for part in (summary.get("note", ""), retry) if part)
        interrupted.saved_results = summary
        raise interrupted
    return summary

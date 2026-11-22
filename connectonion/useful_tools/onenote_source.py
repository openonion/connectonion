"""Read selected OneNote pages through Microsoft Graph for the CLI JSON source."""

from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qsl, quote, unquote, urlsplit

import httpx

from ..credentials import AmbientCredentialError
from ..environment import EnvironmentError
from ..provider_credentials import ProviderCredentialError
from ..rem.files import KEY_SHAPES, RemError, read_json, state_path
from .onenote import TIMEOUT, _page_text
from .outlook import Outlook

READ_SCOPES = {"Notes.Read", "Notes.Read.All", "Notes.ReadWrite", "Notes.ReadWrite.All"}
MAX_SELECTED = 1000
MAX_BODY_BYTES = 2 * 1024 * 1024


class OneNoteSourceError(ValueError):
    """An error safe to include in the CLI's JSON diagnostics."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _object(value) -> dict:
    return value if isinstance(value, dict) else {}


def _id(value) -> bool:
    return (isinstance(value, str) and 0 < len(value) <= 2048
            and all(character.isascii() and character.isprintable() and not character.isspace()
                    for character in value)
            and value not in {".", ".."} and not KEY_SHAPES.search(value))


def _approved_scope(root: Path) -> tuple[dict, str]:
    # This command consumes approval. Only the REM source workflow may write it.
    try:
        saved = read_json(state_path(root, "subscriptions.json"), {})
    except (RemError, OSError, ValueError, TypeError):
        raise OneNoteSourceError("invalid_scope", "Cannot read REM source approval.") from None

    source = _object(_object(saved).get("onenote"))
    if (source.get("enabled") is not True or source.get("consented") is not True
            or source.get("unsubscribed") is True):
        raise OneNoteSourceError("approval_required", "Approve the OneNote selection in co rem sources first.")
    selection = _object(_object(source.get("remote")).get("selection"))
    identity = _object(source.get("import_identity"))
    scope = _object(identity.get("scope"))
    account = identity.get("account")
    pages = selection.get("pages")
    if (not isinstance(pages, list) or not 1 <= len(pages) <= MAX_SELECTED
            or not all(_id(page) for page in pages)
            or not all(_id(selection.get(key)) for key in ("notebook", "section"))
            or selection != scope or not isinstance(account, str) or not account):
        raise OneNoteSourceError("invalid_scope", "OneNote requires an approved account and explicit page IDs.")
    return selection, account


def _timestamp(value, *, argument: bool = False) -> datetime:
    code = "invalid_since" if argument else "invalid_response"
    message = ("Use an ISO 8601 timestamp with a timezone for --since." if argument
               else "OneNote did not return a valid modification time.")
    try:
        if not isinstance(value, str) or "T" not in value:
            raise ValueError
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None:
            raise ValueError
        return parsed.astimezone(timezone.utc)
    except (ValueError, OverflowError):
        raise OneNoteSourceError(code, message) from None


def _provider_error(status: int | None, code: str | None = None) -> OneNoteSourceError:
    if status == 401 or code == "reauth_required":
        return OneNoteSourceError("reauth_required", "Microsoft sign-in expired. Run co auth microsoft.")
    if status == 403 or code == "permission_denied":
        return OneNoteSourceError("permission_denied", "Microsoft denied access to the OneNote selection.")
    if status == 404:
        return OneNoteSourceError("not_found", "An approved OneNote page is missing or inaccessible.")
    if status == 429:
        return OneNoteSourceError("rate_limited", "Microsoft limited OneNote requests. Retry later.")
    if code in {"missing_scope", "not_configured"}:
        return OneNoteSourceError(code, "Microsoft sign-in requires OneNote access. Run co auth microsoft.")
    return OneNoteSourceError("unavailable", "Could not complete the Microsoft OneNote request. Retry later.")


def _credential_error() -> OneNoteSourceError:
    return OneNoteSourceError("credential_unavailable",
                              "Microsoft credentials could not be loaded or refreshed. Check co auth microsoft.")


def _safe_text(value: str) -> str:
    if KEY_SHAPES.search(value):
        return "[withheld: possible credential]"
    return value


def _page_link(page: dict) -> str:
    error = OneNoteSourceError("invalid_response", "OneNote did not return a usable original page link.")
    value = _object(_object(page.get("links")).get("oneNoteWebUrl")).get("href")
    if isinstance(value, str) and not any(ord(ch) < 33 for ch in value):
        try:
            parsed = urlsplit(value)
            host = parsed.hostname or ""
            allowed = ("onenote.com", "onedrive.com", "live.com", "sharepoint.com")
            fields = {key.lower() for key, _ in parse_qsl(parsed.query + "&" + parsed.fragment)}
            if (parsed.scheme == "https" and any(host == dom or host.endswith("." + dom) for dom in allowed)
                    and parsed.username is None and parsed.password is None and parsed.port in (None, 443)
                    and not fields & {"access_token", "authkey", "token", "sig", "code", "tempauth"}
                    and not KEY_SHAPES.search(unquote(value))):
                return value
        except ValueError:
            raise error from None
    raise error


class OneNoteSource:
    """Account-bound Graph GETs. Approval is checked before credentials or page content."""

    def __init__(self, root: Path, page_id: str | None = None):
        self.selection, account = _approved_scope(root)
        if page_id is not None and page_id not in self.selection["pages"]:
            raise OneNoteSourceError("out_of_scope", "This page ID is outside the approved OneNote selection.")

        self.graph = Outlook.__new__(Outlook)
        try:
            credentials = self.graph._credentials
            credentials.require_configured()
            if not credentials.scopes & READ_SCOPES:
                raise _provider_error(None, "missing_scope")
        except ProviderCredentialError as error:
            raise _provider_error(error.status, error.code) from None
        except (AmbientCredentialError, EnvironmentError):
            raise _credential_error() from None
        self.graph._access_token = None
        identity = self._metadata("/me", params={"$select": "id"}).get("id")
        if not _id(identity) or account != f"{self.graph.GRAPH_API_URL}/users/{quote(identity, safe='')}":
            raise OneNoteSourceError("account_mismatch", "The signed-in Microsoft account differs from REM approval.")

    def _metadata(self, endpoint: str, *, params: dict) -> dict:
        try:
            result = self.graph._request("GET", endpoint, timeout=TIMEOUT, params=params)
        except ProviderCredentialError as error:
            raise _provider_error(error.status, error.code) from None
        except (AmbientCredentialError, EnvironmentError):
            raise _credential_error() from None
        except httpx.RequestError:
            raise _provider_error(None) from None
        except ValueError:
            raise OneNoteSourceError("invalid_response", "OneNote returned invalid metadata.") from None
        if not isinstance(result, dict):
            raise OneNoteSourceError("invalid_response", "OneNote returned invalid metadata.")
        return result

    def _page(self, page_id: str) -> tuple[dict, datetime]:
        page = self._metadata(f"/me/onenote/pages/{quote(page_id, safe='')}",
                              params={"$expand": "parentNotebook,parentSection"})
        if (page.get("id") != page_id
                or _object(page.get("parentNotebook")).get("id") != self.selection["notebook"]
                or _object(page.get("parentSection")).get("id") != self.selection["section"]):
            raise OneNoteSourceError("out_of_scope", "OneNote could not verify the approved page location.")
        return page, _timestamp(page.get("lastModifiedDateTime"))

    @staticmethod
    def _summary(page: dict, modified: datetime) -> dict:
        title = page.get("title")
        if not isinstance(title, str):
            raise OneNoteSourceError("invalid_response", "OneNote did not return a valid page title.")
        time = modified.isoformat().replace("+00:00", "Z")
        # Graph's lastModifiedDateTime is the only documented page revision marker.
        return {"id": page["id"], "title": _safe_text(title), "time": time, "version": time}

    def changes(self, since: datetime) -> list[dict]:
        """Look up only approved IDs, without listing the notebook or touching HTML."""
        changes = []
        for page_id in dict.fromkeys(self.selection["pages"]):
            page, modified = self._page(page_id)
            if modified > since:
                changes.append(self._summary(page, modified))
        return sorted(changes, key=lambda row: (_timestamp(row["time"]), row["id"]))

    def _content(self, page_id: str) -> str:
        url = f"{self.graph.GRAPH_API_URL}/me/onenote/pages/{quote(page_id, safe='')}/content"
        try:
            response_code, body = self._read_html(url)
            refresh = self.graph._credentials.get("REFRESH_TOKEN") if response_code == 401 else None
            if refresh:
                self.graph._access_token = self.graph._refresh_via_backend(refresh)
                response_code, body = self._read_html(url)
        except ProviderCredentialError as error:
            raise _provider_error(error.status, error.code) from None
        except (AmbientCredentialError, EnvironmentError):
            raise _credential_error() from None
        except httpx.RequestError:
            raise _provider_error(None) from None
        if response_code != 200:
            raise _provider_error(response_code)
        return _safe_text(_page_text(body))

    def _read_html(self, url: str) -> tuple[int, str]:
        headers = {"Authorization": f"Bearer {self.graph._get_access_token()}"}
        with httpx.stream("GET", url, headers=headers, timeout=TIMEOUT, follow_redirects=False) as response:
            if response.status_code != 200:
                return response.status_code, ""
            if response.headers.get("Content-Type", "").split(";")[0].strip().lower() != "text/html":
                raise OneNoteSourceError("invalid_response", "OneNote did not return page HTML.")
            body = bytearray()
            for chunk in response.iter_bytes(chunk_size=65536):
                body.extend(chunk)
                if len(body) > MAX_BODY_BYTES:
                    raise OneNoteSourceError("content_limit", "OneNote page exceeds the readable size limit.")
        try:
            return 200, body.decode("utf-8")
        except UnicodeError:
            raise OneNoteSourceError("invalid_response", "OneNote page is not valid UTF-8.") from None

    def show(self, page_id: str) -> dict:
        if page_id not in self.selection["pages"]:
            raise OneNoteSourceError("out_of_scope", "This page ID is outside the approved OneNote selection.")
        page, modified = self._page(page_id)
        summary = self._summary(page, modified)
        link = _page_link(page)
        text = self._content(page_id)
        _, current = self._page(page_id)
        if current != modified:
            raise OneNoteSourceError("changed_during_read", "The OneNote page changed during the read. Retry.")
        # Microsoft Graph v1.0 does not expose a page author.
        return {**summary, "text": text, "author": None, "link": link}


def page_changes(root: Path, since: str) -> list[dict]:
    cutoff = _timestamp(since, argument=True)
    return OneNoteSource(root).changes(cutoff)


def show_page(root: Path, page_id: str) -> dict:
    return OneNoteSource(root, page_id).show(page_id)

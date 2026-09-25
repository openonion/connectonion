"""
Purpose: Record what each tab actually sent and received, so a skill can read the network layer the way it already reads the DOM, and save it as a standard HAR file
LLM-Note:
  Dependencies: imports from [asyncio, base64, json, re, time, urllib.parse, datetime, pathlib] | imported by [_async_browser.py] | tested by [tests/unit/test_browser_network_log.py]
  Data flow: page.on("requestfinished"/"requestfailed") → _record() → a bounded per-tab list (and, while `har start` is on, the tab's HAR buffer) | `network requests` / `network request` read the list back | `network har stop` turns the buffer into HAR 1.2 JSON
  State/Effects: one list per tab key, capped at MAX_RECORDS | one HAR buffer per recording tab, capped at HAR_MAX_ENTRIES | bodies over INLINE_LIMIT are written under ~/.co/browser_network/ | nothing is sent anywhere
  Integration: AsyncBrowserCore attaches every page it creates; the `network` and `cookies` verbs read it | the surface follows vercel-labs/agent-browser (`network requests|request|har start|har stop`) so an agent that knows one knows the other
  Performance: metadata is free; outside a HAR recording a body is read only for xhr/fetch/document responses with a textual content type, which is what keeps a page full of images and video segments from costing anything
  Errors: a handler that raises would be swallowed by Playwright and lose the record silently, so every one catches and stores the reason on the record instead

Header values are shaped rather than printed. The consumer of this log is a
skill, and a skill feeds an LLM: `cookie` and `authorization` are exactly the
values that must not reach a prompt by accident. But hiding them entirely would
defeat the purpose — that an endpoint needs an `x-sign` of 32 hex characters is
most of what somebody reverse-engineering it wants to know. So the default
prints the name and the shape, and `--raw` prints the value.
"""

import asyncio
import base64
import json
import re
import time
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

# Per tab. A page doing long-polling fills this in minutes, and the newest
# records are the ones anybody wants, so the oldest are dropped.
MAX_RECORDS = 500

# A body under this is kept in memory. Over it, the body goes to a file and the
# record keeps a preview and the path: a 400 KiB JSON response is worth having,
# but not worth holding five hundred of.
INLINE_LIMIT = 64 * 1024
PREVIEW_CHARS = 2000

# Past this a body is not stored at all. Nothing a page returns as text above
# eight megabytes is being read by a person or a model.
FILE_LIMIT = 8 * 1024 * 1024

# Only these carry a request worth reading. Images, fonts, media, stylesheets
# and video segments are listed — they are part of what the page did — but
# their bodies are never fetched.
BODY_TYPES = {"xhr", "fetch", "document"}

# What `network har start --content` accepts, as in agent-browser: text bodies
# embedded (the default), every body embedded with binary as base64, or none.
HAR_CONTENT = ("text", "all", "none")

# A recording is for one task, but a tab left recording on a streaming page
# would grow without a limit. Past this the oldest entries are dropped and the
# HAR says how many.
HAR_MAX_ENTRIES = 5000

_TEXTUAL = re.compile(
    r"application/(json|javascript|xml|x-www-form-urlencoded|graphql)"
    r"|text/|\+json|\+xml",
    re.I,
)

# Names whose value is shaped rather than printed.
_SECRET_HEADERS = {
    "authorization",
    "proxy-authorization",
    "cookie",
    "set-cookie",
    "x-api-key",
    "x-auth-token",
    "x-csrf-token",
    "x-xsrf-token",
    "x-session-token",
}

_HEX = re.compile(r"^[0-9a-f]+$", re.I)
_B64ISH = re.compile(r"^[A-Za-z0-9_\-+/=.]+$")


def shape(name: str, value: str) -> str:
    """A header value described rather than disclosed.

    Shape is the part that is reusable knowledge — `<32 hex>` says which hash
    produced it; the digits say nothing except to whoever wants the session.
    """
    lowered = name.lower()
    if lowered not in _SECRET_HEADERS and not _looks_opaque(lowered, value):
        return value
    if lowered in ("cookie", "set-cookie"):
        pairs = [part for part in value.split(";") if "=" in part]
        return f"<{len(pairs)} pairs, {len(value)} bytes>"
    for scheme in ("Bearer ", "Basic ", "Token "):
        if value.startswith(scheme):
            return f"{scheme}<{len(value) - len(scheme)} chars>"
    if _HEX.match(value):
        return f"<{len(value)} hex>"
    if _B64ISH.match(value):
        return f"<{len(value)} chars, base64-ish>"
    return f"<{len(value)} chars>"


def _looks_opaque(lowered_name: str, value: str) -> bool:
    """A long unbroken token in a header nobody standardised is a secret too.

    `x-sign`, `x-bogus`, `x-gorgon` — every site invents its own name, so a name
    list alone would print the one header the operator most needs shaped.
    """
    if len(value) < 24 or " " in value:
        return False
    return bool(
        re.search(r"sign|token|secret|auth|sess|key|nonce|bogus|gorgon", lowered_name)
    )


class NetworkLog:
    """One bounded record of request/response pairs per tab."""

    def __init__(self, home: Optional[Path] = None) -> None:
        self._by_tab: Dict[Optional[str], List[dict]] = {}
        self._counters: Dict[Optional[str], int] = {}
        self._attached: set = set()
        self._home = home or Path.home()
        # key -> {"content", "since", "entries", "dropped"} while `har start` is on.
        # Entries are the same record dicts as the list, so a body read for one
        # is there for the other; the list's 500 cap does not cut a recording.
        self._har: Dict[Optional[str], Dict[str, Any]] = {}

    # ---- capture ----------------------------------------------------------

    def attach(self, page, key: Optional[str]) -> None:
        """Start recording one page. Attaching the same page twice is a no-op.

        A page that cannot emit events is left alone rather than raising. This
        is instrumentation: losing the log costs an operator one diagnostic,
        while failing here would cost them the navigation that was the point.
        The capability is asked for directly instead of being discovered by
        catching AttributeError, so a real failure still surfaces.
        """
        if not callable(getattr(page, "on", None)):
            return
        token = (id(page), key)
        if token in self._attached:
            return
        self._attached.add(token)

        def finished(request):
            asyncio.ensure_future(self._on_finished(request, key))

        def failed(request):
            asyncio.ensure_future(self._on_failed(request, key))

        page.on("requestfinished", finished)
        page.on("requestfailed", failed)

    def forget(self, key: Optional[str]) -> None:
        """Drop a closed tab's records so a long-lived daemon does not grow."""
        self._by_tab.pop(key, None)
        self._counters.pop(key, None)
        self._har.pop(key, None)

    # ---- HAR recording ------------------------------------------------------

    def har_start(self, key: Optional[str], content: str = "text") -> Optional[dict]:
        """Begin recording this tab. Returns the recording already running, if
        one is, and changes nothing — a second start silently discarding the
        first would lose the part of the task that already happened."""
        if content not in HAR_CONTENT:
            raise ValueError(f"--content must be one of {', '.join(HAR_CONTENT)}, not {content!r}")
        running = self._har.get(key)
        if running is not None:
            return running
        self._har[key] = {"content": content, "since": time.time(), "entries": [], "dropped": 0}
        return None

    def har_state(self, key: Optional[str]) -> Optional[dict]:
        return self._har.get(key)

    def har_stop(self, key: Optional[str]) -> Optional[dict]:
        """End this tab's recording and hand back what it captured."""
        return self._har.pop(key, None)

    async def _on_finished(self, request, key: Optional[str]) -> None:
        record = self._start_record(request, key)
        try:
            response = await request.response()
            if response is None:
                record["error"] = "no response"
                return
            record["status"] = response.status
            record["status_text"] = getattr(response, "status_text", "") or ""
            record["ok"] = response.ok
            record["resp_headers"] = dict(await response.all_headers())
            await self._capture_body(record, response, key)
        except Exception as exc:  # a lost body must not lose the record
            record["error"] = f"{type(exc).__name__}: {exc}"
        finally:
            self._append(key, record)

    async def _on_failed(self, request, key: Optional[str]) -> None:
        record = self._start_record(request, key)
        failure = getattr(request, "failure", None)
        record["error"] = str(failure) if failure else "request failed"
        self._append(key, record)

    def _start_record(self, request, key: Optional[str]) -> dict:
        try:
            headers = dict(request.headers)
        except Exception:
            headers = {}
        try:
            post = request.post_data
        except Exception:
            post = None
        return {
            "n": None,
            "at": time.time(),
            # When the request went out, which HAR needs and `at` is not: `at`
            # is when it finished and was recorded.
            "started": _started(request),
            "method": getattr(request, "method", ""),
            "url": getattr(request, "url", ""),
            "kind": getattr(request, "resource_type", ""),
            "status": None,
            "status_text": "",
            "ok": None,
            "duration_ms": _duration_ms(request),
            "req_headers": headers,
            "req_body": post,
            "resp_headers": {},
            "resp_body": None,
            "resp_body_b64": None,
            "resp_size": None,
            "body_file": None,
            "truncated": False,
            "error": None,
        }

    def _body_mode(self, record: dict, key: Optional[str]) -> Optional[str]:
        """Which bodies to read: None, textual ones, or any.

        Outside a recording, only the request types somebody reads. While a
        HAR is recording, what `--content` asked for: `text` widens it to every
        textual body (scripts and stylesheets included, as a HAR from DevTools
        would carry), `all` to binary too, `none` changes nothing — the list
        still wants its xhr bodies.
        """
        har = self._har.get(key)
        if har is not None and har["content"] == "all":
            return "any"
        if record["kind"] in BODY_TYPES:
            return "text"
        if har is not None and har["content"] == "text":
            return "text"
        return None

    async def _capture_body(self, record: dict, response, key: Optional[str] = None) -> None:
        """Read a response body when it is one somebody would want to read."""
        mode = self._body_mode(record, key)
        if mode is None:
            return
        content_type = record["resp_headers"].get("content-type", "")
        textual = not content_type or bool(_TEXTUAL.search(content_type))
        if not textual and mode != "any":
            return
        body = await response.body()
        record["resp_size"] = len(body)
        if len(body) > FILE_LIMIT:
            record["truncated"] = True
            if textual:
                record["resp_body"] = body[:PREVIEW_CHARS].decode("utf-8", "replace")
            return
        if not textual:
            # Kept as base64 for the HAR only; the list shows no image bytes.
            record["resp_body_b64"] = base64.b64encode(body).decode("ascii")
            return
        text = body.decode("utf-8", "replace")
        if len(body) <= INLINE_LIMIT:
            record["resp_body"] = text
            return
        record["body_file"] = await asyncio.to_thread(self._write_body, record, text)
        record["resp_body"] = text[:PREVIEW_CHARS]
        record["truncated"] = True

    def _write_body(self, record: dict, text: str) -> str:
        out = self._home / ".co" / "browser_network"
        out.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y%m%d_%H%M%S", time.localtime(record["at"]))
        path = out / f"{stamp}_{abs(hash(record['url'])) % 10**8}.txt"
        path.write_text(text, encoding="utf-8")
        return str(path)

    def _append(self, key: Optional[str], record: dict) -> None:
        records = self._by_tab.setdefault(key, [])
        self._counters[key] = self._counters.get(key, 0) + 1
        record["n"] = self._counters[key]
        records.append(record)
        if len(records) > MAX_RECORDS:
            del records[: len(records) - MAX_RECORDS]
        har = self._har.get(key)
        # `at` is when the event fired; the body read after it is async, so a
        # request that finished just before `har start` is appended just after
        # it. Found on real Chrome: the page loaded before recording landed in
        # the HAR. A recording holds what happened while it was on.
        if har is not None and record["at"] >= har["since"]:
            har["entries"].append(record)
            if len(har["entries"]) > HAR_MAX_ENTRIES:
                over = len(har["entries"]) - HAR_MAX_ENTRIES
                del har["entries"][:over]
                har["dropped"] += over

    # ---- reading ----------------------------------------------------------

    def clear(self, key: Optional[str]) -> int:
        """Forget this tab's records and return how many were dropped.

        The counter keeps going: an index printed before a clear never means a
        different request afterwards.
        """
        dropped = len(self._by_tab.get(key, []))
        self._by_tab[key] = []
        return dropped

    def select(
        self,
        key: Optional[str],
        *,
        url_contains: str = "",
        method: str = "",
        kind: str = "",
        status: str = "",
        since: float = 0.0,
        limit: int = 30,
    ) -> List[dict]:
        """`kind` is a comma list (`xhr,fetch`); `status` is `200`, `2xx` or `400-499`."""
        found = []
        cutoff = time.time() - since if since else 0.0
        kinds = parse_kinds(kind)
        wanted_status = parse_status(status)
        for record in self._by_tab.get(key, []):
            if url_contains and url_contains not in record["url"]:
                continue
            if method and record["method"].upper() != method.upper():
                continue
            if kinds and record["kind"] not in kinds:
                continue
            if wanted_status and not wanted_status(record["status"]):
                continue
            if cutoff and record["at"] < cutoff:
                continue
            found.append(record)
        return found[-limit:] if limit else found

    def find(self, key: Optional[str], index: int) -> Optional[dict]:
        for record in self._by_tab.get(key, []):
            if record["n"] == index:
                return record
        return None


# Playwright's request.resource_type values — the whole vocabulary --type can match.
RESOURCE_TYPES = (
    "document", "stylesheet", "image", "media", "font", "script", "texttrack",
    "xhr", "fetch", "eventsource", "websocket", "manifest", "other",
)


def parse_kinds(spec) -> set:
    """`xhr,fetch` as a set; a word Playwright never reports is a usage error.

    Like --status: a typo that matched nothing read as "the page made no such
    requests".
    """
    kinds = {part.strip().lower() for part in str(spec or "").split(",") if part.strip()}
    unknown = sorted(kinds - set(RESOURCE_TYPES))
    if unknown:
        raise ValueError(f"--type takes a comma list of {', '.join(RESOURCE_TYPES)}, "
                         f"not {', '.join(map(repr, unknown))}")
    return kinds


def parse_status(spec) -> Optional[Any]:
    """`200`, `2xx` or `400-499` as a predicate on a status code; None for no filter.

    A spec that is none of those is a usage error, not an empty result: a typo
    that silently matched nothing would read as "the page sent no errors".
    """
    text = str(spec or "").strip().lower()
    if not text:
        return None
    if re.fullmatch(r"\d{3}", text):
        code = int(text)
        return lambda status: status == code
    if re.fullmatch(r"[1-5]xx", text):
        hundred = int(text[0])
        return lambda status: status is not None and status // 100 == hundred
    found = re.fullmatch(r"(\d{3})-(\d{3})", text)
    if found:
        low, high = int(found.group(1)), int(found.group(2))
        return lambda status: status is not None and low <= status <= high
    raise ValueError(f"--status takes 200, 2xx or 400-499, not {spec!r}")


def _started(request) -> float:
    """Epoch seconds when the request went out. Playwright's startTime is epoch
    milliseconds; without timing, the moment we saw it is the honest fallback."""
    try:
        timing = request.timing or {}
    except Exception:  # Playwright raises once the request is gone; same fallback
        return time.time()
    start = timing.get("startTime")
    return start / 1000.0 if start and start > 0 else time.time()


def _duration_ms(request) -> Optional[int]:
    """How long the request took, in milliseconds.

    `responseEnd` is already relative to `startTime` — startTime is an absolute
    epoch, everything else is an offset from it. Subtracting one from the other
    yields a large negative number, which is what the first real page showed
    after the offline tests passed: the fake had returned startTime 0, encoding
    the wrong assumption instead of catching it.
    """
    try:
        timing = request.timing
    except Exception:
        return None
    if not timing:
        return None
    end = timing.get("responseEnd", -1)
    if end is None or end < 0:
        return None
    return int(end)


# ---- rendering ------------------------------------------------------------


def render_list(records: List[dict], as_json: bool = False) -> str:
    """One line per request, newest last, id first so `cut -f1` feeds `request`."""
    if as_json:
        return json.dumps(
            [_public(record, raw=False) for record in records],
            indent=2,
            ensure_ascii=False,
        )
    if not records:
        return "no requests recorded"
    rows = ["#\tmethod\tstatus\tkind\tsize\ttook\turl"]
    for record in records:
        status = record["status"] if record["status"] is not None else "—"
        size = _human(record["resp_size"])
        took = f"{record['duration_ms']}ms" if record["duration_ms"] is not None else "—"
        note = f"  ({record['error']})" if record["error"] else ""
        rows.append(
            f"{record['n']}\t{record['method']}\t{status}\t{record['kind']}\t"
            f"{size}\t{took}\t{record['url']}{note}"
        )
    return "\n".join(rows)


def render_one(record: dict, raw: bool = False) -> str:
    """One request in full: what went out, what came back."""
    out = [
        f"#{record['n']}  {record['method']} {record['url']}",
        f"kind={record['kind']}  "
        f"status={record['status'] if record['status'] is not None else 'no response'}  "
        f"size={_human(record['resp_size'])}  took="
        f"{record['duration_ms'] if record['duration_ms'] is not None else '—'}ms",
    ]
    if record["error"]:
        out.append(f"error: {record['error']}")
    out.append("")
    out.append("--- request headers ---")
    out.extend(_headers(record["req_headers"], raw))
    if record["req_body"]:
        out += ["", "--- request body ---", record["req_body"]]
    out += ["", "--- response headers ---"]
    out.extend(_headers(record["resp_headers"], raw))
    if record["resp_body"] is not None:
        out += ["", "--- response body ---", record["resp_body"]]
        if record["truncated"]:
            where = record["body_file"] or "not stored (over the size limit)"
            out.append(f"\n[truncated — full body: {where}]")
    if not raw:
        out.append("\nHeader values are shaped, not shown. Add --raw for the values.")
    return "\n".join(out)


def _headers(headers: Dict[str, str], raw: bool) -> List[str]:
    if not headers:
        return ["(none)"]
    return [
        f"  {name}: {value if raw else shape(name, value)}"
        for name, value in sorted(headers.items())
    ]


def _public(record: dict, raw: bool) -> Dict[str, Any]:
    copy = dict(record)
    # Base64 image bytes are for the HAR file, not for a listing a model reads.
    copy.pop("resp_body_b64", None)
    if not raw:
        copy["req_headers"] = {
            name: shape(name, value) for name, value in record["req_headers"].items()
        }
        copy["resp_headers"] = {
            name: shape(name, value) for name, value in record["resp_headers"].items()
        }
    return copy


def _human(size: Optional[int]) -> str:
    if size is None:
        return "—"
    if size < 1024:
        return f"{size}B"
    if size < 1024 * 1024:
        return f"{size / 1024:.1f}K"
    return f"{size / (1024 * 1024):.1f}M"


# ---- HAR 1.2 ----------------------------------------------------------------
#
# The format Chrome DevTools, Charles and Playwright's route_from_har() read.
# Spec: http://www.softwareishard.com/blog/har-12-spec/ . Unknown numbers are
# -1 where the spec allows it; httpVersion is left empty because Playwright
# does not report it and a guessed "HTTP/1.1" on an h2 request would be a lie.


def to_har(recording: dict, *, raw: bool, tab: str, creator_version: str) -> dict:
    """One tab's recording as a HAR document."""
    notes = [f"co browser -t {tab} network har", f"content={recording['content']}"]
    if not raw:
        notes.append("header and cookie values are shaped; `network har stop --raw` keeps them")
    if recording.get("dropped"):
        notes.append(f"{recording['dropped']} oldest entries dropped past {HAR_MAX_ENTRIES}")
    return {
        "log": {
            "version": "1.2",
            "creator": {"name": "connectonion co browser", "version": creator_version},
            "comment": "; ".join(notes),
            "pages": [],
            "entries": [
                _har_entry(record, raw=raw, content=recording["content"])
                for record in recording["entries"]
            ],
        }
    }


def _har_entry(record: dict, *, raw: bool, content: str) -> dict:
    took = record["duration_ms"] if record["duration_ms"] is not None else 0
    started = datetime.fromtimestamp(record.get("started") or record["at"], timezone.utc)
    req_headers = record["req_headers"] or {}
    resp_headers = record["resp_headers"] or {}
    request = {
        "method": record["method"],
        "url": record["url"],
        "httpVersion": "",
        "cookies": _request_cookies(req_headers, raw),
        "headers": _har_headers(req_headers, raw),
        "queryString": [
            {"name": name, "value": value}
            for name, value in urllib.parse.parse_qsl(
                urllib.parse.urlsplit(record["url"]).query, keep_blank_values=True)
        ],
        "headersSize": -1,
        "bodySize": len(record["req_body"].encode("utf-8")) if record["req_body"] else 0,
    }
    if record["req_body"]:
        request["postData"] = {"mimeType": _header(req_headers, "content-type"),
                               "text": record["req_body"]}
    response = {
        "status": record["status"] or 0,
        "statusText": record.get("status_text") or "",
        "httpVersion": "",
        "cookies": _response_cookies(resp_headers, raw),
        "headers": _har_headers(resp_headers, raw),
        "content": _har_content(record, content),
        "redirectURL": _header(resp_headers, "location"),
        "headersSize": -1,
        "bodySize": -1,
    }
    entry = {
        "startedDateTime": started.isoformat(timespec="milliseconds").replace("+00:00", "Z"),
        "time": took,
        "request": request,
        "response": response,
        "cache": {},
        "timings": {"blocked": -1, "dns": -1, "connect": -1, "ssl": -1,
                    "send": 0, "wait": took, "receive": 0},
        # DevTools' own extension, so its Network panel groups by type.
        "_resourceType": record["kind"],
    }
    if record["error"]:
        entry["_error"] = record["error"]
    return entry


def _har_content(record: dict, content: str) -> dict:
    body = {
        "size": record["resp_size"] if record["resp_size"] is not None else 0,
        "mimeType": _header(record["resp_headers"] or {}, "content-type"),
    }
    if content == "none":
        return body
    if record.get("resp_body_b64"):
        body["text"] = record["resp_body_b64"]
        body["encoding"] = "base64"
    elif record["body_file"]:
        # The full body went to a file when it was captured; the record holds
        # only a preview, and a HAR with a preview is a HAR that lies.
        body["text"] = Path(record["body_file"]).read_text(encoding="utf-8")
    elif record["truncated"]:
        body["comment"] = f"body over {FILE_LIMIT // (1024 * 1024)} MiB was not stored"
    elif record["resp_body"] is not None:
        body["text"] = record["resp_body"]
    return body


def _header(headers: Dict[str, str], name: str) -> str:
    for key, value in headers.items():
        if key.lower() == name:
            return value
    return ""


def _har_headers(headers: Dict[str, str], raw: bool) -> List[dict]:
    """Playwright joins repeated headers with a newline; HAR lists each once."""
    out = []
    for name, value in sorted(headers.items()):
        for part in str(value).split("\n"):
            out.append({"name": name, "value": part if raw else shape(name, part)})
    return out


def cookie_value(value: str, raw: bool) -> str:
    return value if raw else f"<{len(value)} chars>"


def _request_cookies(headers: Dict[str, str], raw: bool) -> List[dict]:
    cookies = []
    for part in _header(headers, "cookie").split(";"):
        name, eq, value = part.strip().partition("=")
        if eq and name:
            cookies.append({"name": name, "value": cookie_value(value, raw)})
    return cookies


def _response_cookies(headers: Dict[str, str], raw: bool) -> List[dict]:
    cookies = []
    for line in _header(headers, "set-cookie").split("\n"):
        first, *attributes = [piece.strip() for piece in line.split(";")]
        name, eq, value = first.partition("=")
        if not (eq and name):
            continue
        cookie = {"name": name, "value": cookie_value(value, raw)}
        for attribute in attributes:
            key, _, attr_value = attribute.partition("=")
            lowered = key.lower()
            if lowered in ("path", "domain", "expires"):
                cookie[lowered] = attr_value
            elif lowered == "httponly":
                cookie["httpOnly"] = True
            elif lowered == "secure":
                cookie["secure"] = True
        cookies.append(cookie)
    return cookies


# ---- cookies ------------------------------------------------------------------


def render_cookies(cookies: List[dict], *, raw: bool = False, as_json: bool = False) -> str:
    """Cookies as the browser holds them, values shaped unless `raw`.

    Same rule as the headers: which cookies a site sets, and on which domain
    and path, is what somebody debugging a login needs; the value is the
    login itself.
    """
    public = []
    for cookie in cookies:
        shown = dict(cookie)
        shown["value"] = cookie_value(str(cookie.get("value", "")), raw)
        public.append(shown)
    if as_json:
        return json.dumps(public, indent=2, ensure_ascii=False)
    if not public:
        return "no cookies"
    rows = []
    for cookie in public:
        flags = " ".join(filter(None, [
            "HttpOnly" if cookie.get("httpOnly") else "",
            "Secure" if cookie.get("secure") else "",
            f"SameSite={cookie['sameSite']}" if cookie.get("sameSite") else "",
        ]))
        rows.append(f"{cookie.get('name', '')}\t{cookie.get('domain', '')}\t{cookie.get('path', '')}\t"
                    f"{_expiry(cookie.get('expires'))}\t{flags}\t{cookie['value']}")
    rows.append("name\tdomain\tpath\texpires\tflags\tvalue")
    if not raw:
        rows.append("Values are shaped, not shown. Add --raw for the values.")
    return "\n".join(rows)


def _expiry(expires) -> str:
    if expires is None or expires < 0:
        return "session"
    return datetime.fromtimestamp(expires, timezone.utc).strftime("%Y-%m-%d")

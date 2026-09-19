"""
Purpose: Record what each tab actually sent and received, so a skill can read the network layer the way it already reads the DOM
LLM-Note:
  Dependencies: imports from [asyncio, json, re, time, pathlib] | imported by [_async_browser.py] | tested by [tests/unit/test_browser_network_log.py]
  Data flow: page.on("requestfinished"/"requestfailed") → _record() → a bounded per-tab list | requests()/request() read that list back
  State/Effects: one list per tab key, capped at MAX_RECORDS | bodies over INLINE_LIMIT are written under ~/.co/browser_network/ | nothing is sent anywhere
  Integration: AsyncBrowserCore.attach_network() on every page it creates; the `requests` and `request` verbs read it
  Performance: metadata is free; a body is read only for xhr/fetch/document responses with a textual content type, which is what keeps a page full of images and video segments from costing anything
  Errors: a handler that raises would be swallowed by Playwright and lose the record silently, so every one catches and stores the reason on the record instead

Header values are shaped rather than printed. The consumer of this log is a
skill, and a skill feeds an LLM: `cookie` and `authorization` are exactly the
values that must not reach a prompt by accident. But hiding them entirely would
defeat the purpose — that an endpoint needs an `x-sign` of 32 hex characters is
most of what somebody reverse-engineering it wants to know. So the default
prints the name and the shape, and `--raw` prints the value.
"""

import asyncio
import json
import re
import time
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

    async def _on_finished(self, request, key: Optional[str]) -> None:
        record = self._start_record(request, key)
        try:
            response = await request.response()
            if response is None:
                record["error"] = "no response"
                return
            record["status"] = response.status
            record["ok"] = response.ok
            record["resp_headers"] = dict(await response.all_headers())
            await self._capture_body(record, response)
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
            "method": getattr(request, "method", ""),
            "url": getattr(request, "url", ""),
            "kind": getattr(request, "resource_type", ""),
            "status": None,
            "ok": None,
            "duration_ms": _duration_ms(request),
            "req_headers": headers,
            "req_body": post,
            "resp_headers": {},
            "resp_body": None,
            "resp_size": None,
            "body_file": None,
            "truncated": False,
            "error": None,
        }

    async def _capture_body(self, record: dict, response) -> None:
        """Read a response body when it is one somebody would want to read."""
        if record["kind"] not in BODY_TYPES:
            return
        content_type = record["resp_headers"].get("content-type", "")
        if content_type and not _TEXTUAL.search(content_type):
            return
        body = await response.body()
        record["resp_size"] = len(body)
        if len(body) > FILE_LIMIT:
            record["truncated"] = True
            record["resp_body"] = body[:PREVIEW_CHARS].decode("utf-8", "replace")
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
        status: int = 0,
        since: float = 0.0,
        limit: int = 30,
    ) -> List[dict]:
        found = []
        cutoff = time.time() - since if since else 0.0
        for record in self._by_tab.get(key, []):
            if url_contains and url_contains not in record["url"]:
                continue
            if method and record["method"].upper() != method.upper():
                continue
            if kind and record["kind"] != kind:
                continue
            if status and record["status"] != status:
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
    rows = []
    for record in records:
        status = record["status"] if record["status"] is not None else "—"
        size = _human(record["resp_size"])
        took = f"{record['duration_ms']}ms" if record["duration_ms"] is not None else "—"
        note = f"  ({record['error']})" if record["error"] else ""
        rows.append(
            f"{record['n']}\t{record['method']}\t{status}\t{record['kind']}\t"
            f"{size}\t{took}\t{record['url']}{note}"
        )
    rows.append("#\tmethod\tstatus\tkind\tsize\ttook\turl")
    return "\n".join(rows)


def render_one(record: dict, raw: bool = False) -> str:
    """One request in full: what went out, what came back."""
    out = [
        f"#{record['n']}  {record['method']} {record['url']}",
        f"kind={record['kind']}  status={record['status']}  "
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

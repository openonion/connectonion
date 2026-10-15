"""The owner's live co rem on this computer: GET /rem and POST /rem/translate.

`co rem open` opens http://127.0.0.1:<port>/rem?token=<t>. The token is the
secret in the Host's identity directory (`rem-reader-token`, mode 600), so
whoever can read it can already read the Host's key and the notebook: the same
owner the signed WIKI_READ path admits, proven by the file system instead of a
browser key. The first request trades it for a SameSite=Strict, HttpOnly
cookie and redirects to the bare /rem, so the token leaves the address bar.

Only loopback clients, and only a Host header naming loopback (a rebound DNS
name gets nothing), are answered. A translation runs in a worker thread; the
page polls the same POST until it is ready or failed.
"""

import asyncio
import hmac
import json
from http.cookies import SimpleCookie
from urllib.parse import parse_qs, urlsplit

from ..asgi.http import read_body

COOKIE = "co_rem"
LOOPBACK = {"127.0.0.1", "::1"}
LOOPBACK_NAMES = LOOPBACK | {"localhost"}
SECURITY_HEADERS = [[b"cache-control", b"no-store"], [b"x-frame-options", b"DENY"],
                    [b"referrer-policy", b"no-referrer"], [b"x-content-type-options", b"nosniff"]]
# One translation per (notebook, page, language) at a time; the Host runs one worker.
TASKS: dict[tuple, asyncio.Task] = {}


async def _reply(send, status: int, body: str, kind: str = "text/plain", headers=()):
    await send({"type": "http.response.start", "status": status,
                "headers": [[b"content-type", f"{kind}; charset=utf-8".encode()], *SECURITY_HEADERS, *headers]})
    await send({"type": "http.response.body", "body": body.encode("utf-8")})


def _headers(scope) -> dict:
    return {key.decode("latin-1").lower(): value.decode("latin-1") for key, value in scope.get("headers") or []}


def _local(scope, headers: dict) -> bool:
    client = (scope.get("client") or ("",))[0]
    return client in LOOPBACK and urlsplit("//" + headers.get("host", "")).hostname in LOOPBACK_NAMES


def _same(given: str, token: str) -> bool:
    return bool(given) and hmac.compare_digest(given.encode(), token.encode())


async def handle_rem_http(scope, receive, send, routes):
    headers = _headers(scope)
    root, directory = routes.get("rem_root"), routes.get("identity_dir")
    if not _local(scope, headers) or root is None or directory is None:
        await _reply(send, 404, "not found")
        return
    if not root.is_dir():
        await _reply(send, 404, "co rem is not available on this Host: run `co rem init`")
        return
    from ...rem.live_host import reader_token
    token = await asyncio.to_thread(reader_token, directory)
    given = parse_qs(scope.get("query_string", b"").decode("latin-1")).get("token", [""])[0]
    if scope["method"] == "GET" and scope["path"] == "/rem" and _same(given, token):
        cookie = f"{COOKIE}={token}; HttpOnly; SameSite=Strict; Path=/rem"
        await _reply(send, 303, "", headers=[[b"location", b"/rem"], [b"set-cookie", cookie.encode()]])
        return
    jar = SimpleCookie(headers.get("cookie", ""))
    if not _same(jar[COOKIE].value if COOKIE in jar else "", token):
        await _reply(send, 401, "Open co rem with `co rem open` on this computer.")
        return
    if scope["method"] == "GET" and scope["path"] == "/rem":
        from ...rem.reader import render
        await _reply(send, 200, await asyncio.to_thread(render, root, live=True), "text/html")
    elif scope["method"] == "POST" and scope["path"] == "/rem/translate":
        await _translate(scope, receive, send, root, headers)
    else:
        await _reply(send, 404, "not found")


async def _translate(scope, receive, send, root, headers):
    # A form post cannot send this type; a cross-site fetch would need a preflight we never grant.
    if headers.get("content-type", "").split(";")[0].strip() != "application/json":
        await _reply(send, 415, "application/json required")
        return
    body = json.loads(await read_body(receive, 4096) or b"{}")
    page, language = body.get("page"), body.get("language")
    from ...rem.config import LANGUAGE
    from ...rem.files import Notebook
    if not isinstance(language, str) or not LANGUAGE.fullmatch(language):
        await _reply(send, 400, json.dumps({"state": "failed", "error": "language must be a tag such as zh or ja"}),
                     "application/json")
        return
    if page not in await asyncio.to_thread(Notebook(root).list):
        await _reply(send, 400, json.dumps({"state": "failed", "error": "no such page"}), "application/json")
        return
    await _reply(send, 200, json.dumps(_progress(root, page, language), ensure_ascii=False), "application/json")


def _progress(root, page: str, language: str) -> dict:
    """Start the translation once; later polls read where it is."""
    from ...rem.translate import cached, translate
    key = (str(root), page, language)
    task = TASKS.get(key)
    if task is None and (text := cached(root, page, language)) is not None:
        return {"state": "ready", "text": text}
    if task is None:
        task = TASKS[key] = asyncio.get_running_loop().create_task(asyncio.to_thread(translate, root, page, language))
    if not task.done():
        return {"state": "running"}
    del TASKS[key]
    if task.exception() is not None:
        return {"state": "failed", "error": str(task.exception())}
    return {"state": "ready", "text": task.result()}

"""The owner's live co rem on this computer: GET /rem and POST /rem/translate.

`co rem open` opens http://127.0.0.1:<port>/rem?token=<t>. /rem and
/rem/data.json answer from the pages saved outside the notebook (reader.py,
`cached_page`); /rem/version tells the open page when a newer one has landed.
The token is the secret in the Host's identity directory (`rem-reader-token`, mode 600), so
whoever can read it can already read the Host's key and the notebook: the same
owner the signed WIKI_READ path admits, proven by the file system instead of a
browser key. The first request trades it for a SameSite=Strict, HttpOnly
cookie and redirects to the bare /rem, so the token leaves the address bar.

POST /rem/task hands any unfinished row to Codex or Claude and follows it
(run, status, stop, undo, result); POST /rem/talk is a conversation with the
agent about a row or an archived session (begin, say, read); POST /rem/review
records the owner's verdict on a review in 问题与关联 (reviews.decide); POST /rem/sender
ignores one mail sender from Today and the night's drafts, or undoes it (threads.ignore_sender).

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
        # D-60: no command here either. The page has no language of its own, so English.
        await _reply(send, 401, "This page's session has ended. Open REM again from your computer.")
        return
    if scope["method"] == "GET" and scope["path"] in ("/rem", "/rem/data.json"):
        from ...rem.reader import cached_page
        # The saved page at once; a stale one is rebuilt by a detached process
        # and the open page reloads when /rem/version names a newer render.
        name = "live.html" if scope["path"] == "/rem" else "data.json"
        page, _ = await asyncio.to_thread(cached_page, root, name)
        await _reply(send, 200, page, "text/html" if name == "live.html" else "application/json")
    elif scope["method"] == "GET" and scope["path"] == "/rem/version":
        from ...rem.reader import latest
        await _reply(send, 200, json.dumps(await asyncio.to_thread(latest, root)), "application/json")
    elif scope["method"] == "POST" and scope["path"] == "/rem/translate":
        await _translate(scope, receive, send, root, headers)
    elif scope["method"] == "GET" and scope["path"] == "/rem/thread":
        from ...rem.threads import listing
        await _reply(send, 200, json.dumps(await asyncio.to_thread(listing, root)), "application/json")
    elif scope["method"] == "POST" and scope["path"] in ("/rem/draft", "/rem/thread", "/rem/translation-request", "/rem/language", "/rem/approve", "/rem/task", "/rem/talk", "/rem/review", "/rem/sender"):
        await _action(scope, receive, send, root, headers)
    else:
        await _reply(send, 404, "not found")


async def _action(scope, receive, send, root, headers):
    if headers.get("content-type", "").split(";")[0].strip() != "application/json":
        await _reply(send, 415, "application/json required")
        return
    try:
        body = json.loads(await read_body(receive, 65536 if scope["path"] in ("/rem/thread", "/rem/approve", "/rem/talk", "/rem/review") else 4096) or b"{}")
    except (ValueError, UnicodeDecodeError):
        await _reply(send, 400, json.dumps({"error": "Invalid JSON"}), "application/json")
        return
    if not isinstance(body, dict):
        await _reply(send, 400, json.dumps({"error": "JSON object required"}), "application/json")
        return
    from ...rem.files import RemError
    from ...rem import drafts, threads, translate
    if scope["path"] == "/rem/task":
        from ...rem import tasks
        action = body.get("action", "status")
        if action == "run":
            # 交给 Codex / 交给 Claude on any pending item: {"key": obligation key, "agent": "codex"|"claude"}.
            if not isinstance(body.get("key"), str) or body.get("agent", "codex") not in tasks.AGENTS:
                await _reply(send, 400, json.dumps({"error": "Expected the item key and agent codex or claude"}), "application/json")
                return
            operation = lambda: tasks.dispatch(root, body["key"], agent=body.get("agent", "codex"))
        elif not isinstance(body.get("id"), str) or action not in ("status", "stop", "undo", "result"):
            await _reply(send, 400, json.dumps({"error": "Expected task id and action status, stop, undo or result"}), "application/json")
            return
        else:
            operation = lambda: getattr(tasks, action)(root, body['id'])
    elif scope["path"] == "/rem/review":
        from ...rem import reviews
        # Exactly the verdicts reviews.decide accepts; it then checks the verdict fits the row's kind.
        if (not isinstance(body.get("id"), str) or not body["id"] or body.get("verdict") not in ("yes", "no", "answer")
                or not isinstance(body.get("response", ""), str)):
            await _reply(send, 400, json.dumps({"error": "Expected the review id and verdict yes, no or answer"}), "application/json")
            return
        # An id the notebook no longer holds is its own answer, not "already decided".
        if not any(row["id"] == body["id"] for row in await asyncio.to_thread(reviews.listing, root)):
            await _reply(send, 404, json.dumps({"error": "No such review"}), "application/json")
            return
        operation = lambda: reviews.decide(root, body["id"], body["verdict"], author="owner", response=body.get("response", ""))
    elif scope["path"] == "/rem/talk":
        operation = _talk(root, body)
        if operation is None:
            await _reply(send, 400, json.dumps({"error": "Expected begin with a key or session, say with an id and text, or read with an id"}), "application/json")
            return
    elif scope["path"] == "/rem/approve":
        from ...rem import approvals
        if (body.get("action", "approve") not in ("approve", "undo")
                or not isinstance(body.get("ids"), list) or len(body["ids"]) > 500
                or any(not isinstance(key, str) for key in body["ids"])
                or not isinstance(body.get("bodies", {}), dict)
                or any(not isinstance(k, str) or not isinstance(v, str) for k, v in body.get("bodies", {}).items())):
            await _reply(send, 400, json.dumps({"error": "Expected selected ids and reply bodies"}), "application/json")
            return
        operation = lambda: (approvals.undo(root, body["ids"]) if body.get("action") == "undo"
                             else approvals.approve(root, body["ids"], bodies=body.get("bodies")))
    elif scope["path"] == "/rem/thread":
        if (not isinstance(body.get("key"), str) or "\n" not in body["key"]
                or body.get("state") not in ("done", "skipped", "open")
                or not isinstance(body.get("device"), (str, type(None)))
                or not isinstance(body.get("keys"), (list, type(None)))
                or any(not isinstance(key, str) for key in body.get("keys") or [])
                or not isinstance(body.get("versions"), (dict, type(None)))
                or any(not isinstance(k, str) or not isinstance(v, str) for k, v in (body.get("versions") or {}).items())):
            await _reply(send, 400, json.dumps({"error": "Expected thread key and state done, skipped or open"}), "application/json")
            return
        operation = lambda: threads.set_state(root, body["key"], body["state"], device=body.get("device"), versions=body.get("versions"), keys=body.get("keys"))
    elif scope["path"] == "/rem/sender":
        from ...rem.files import EMAIL
        # 忽略 this sender from Today, or undo it: one address, never a pattern that could stop a whole domain.
        if (not isinstance(body.get("address"), str) or len(body["address"]) > 254
                or not EMAIL.fullmatch(body["address"]) or not isinstance(body.get("ignored"), bool)):
            await _reply(send, 400, json.dumps({"error": "Expected one mail address and ignored true or false"}), "application/json")
            return
        operation = lambda: {"ignored": threads.ignore_sender(root, body["address"], ignored=body["ignored"])}
    elif scope["path"] == "/rem/language":
        from ...rem.config import request_language
        operation = lambda: request_language(root, body.get("language"))
    elif scope["path"] == "/rem/translation-request":
        operation = lambda: translate.request(root, body.get("page"), body.get("language"))
    elif body.get("action") == "prepare" and isinstance(body.get("provider"), str) and isinstance(body.get("thread"), str):
        operation = lambda: drafts.prepare_now(root, body["provider"], body["thread"])
    elif (body.get("action") in ("open", "discard", "send", "redraft") and isinstance(body.get("id"), str)
          and isinstance(body.get("body"), (str, type(None))) and isinstance(body.get("channel"), (str, type(None)))):
        operation = lambda: (drafts.send(root, body["id"], body.get("body")) if body["action"] == "send"
                             else drafts.redraft(root, body["id"], body.get("channel") or "mail") if body["action"] == "redraft"
                             else {"open": drafts.open_provider, "discard": drafts.discard}[body["action"]](root, body["id"]))
    else:
        await _reply(send, 400, json.dumps({"error": "Unknown draft action"}), "application/json")
        return
    # Provider/authentication errors must reach the card instead of leaving an empty tab.
    from ...rem.tasks import UnknownItem
    try:
        result = await asyncio.to_thread(operation)
    # A thread mark the notebook will never take is a 400: the reader gives up on those and waits out a 409 (busy).
    except (UnknownItem, threads.UnknownThread) as error:
        await _reply(send, 400, json.dumps({"error": str(error)}), "application/json")
        return
    except (RemError, ValueError) as error:
        await _reply(send, 409, json.dumps({"error": str(error)}), "application/json")
        return
    from ...rem.reader import owner_changed
    # The owner's own change shows now, not at the reader's next rebuild interval.
    # A task status or result read changes nothing, and neither does a conversation.
    if not (scope["path"] == "/rem/task" and body.get("action", "status") in ("status", "result")
            or scope["path"] == "/rem/talk"):
        await asyncio.to_thread(owner_changed, root)
    await _reply(send, 200, json.dumps(result or {"state": "saved"}), "application/json")


def _talk(root, body):
    """和 Codex 聊这件事: the operation one /rem/talk body asks for, or None when it is malformed."""
    from ...rem import conversations
    action, text = body.get("action"), lambda name: isinstance(body.get(name), str) and body[name]
    if action == "begin" and body.get("agent", "codex") in ("codex", "claude") and (text("key") or text("session")):
        return lambda: conversations.begin(root, body.get("agent", "codex"), key=body.get("key"), session=body.get("session"))
    if action == "say" and text("id") and text("text"):
        return lambda: conversations.say(root, body["id"], body["text"])
    if action == "read" and text("id"):
        return lambda: conversations.read(root, body["id"])
    return None


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


def approval_tick(root, create_agent, storage, result_ttl, extra_tick=None):
    """Attach durable REM outbox delivery to the Host's existing minute clock."""
    async def tick(at):
        from ...rem.approvals import release
        from ...rem.tasks import host_dispatch

        def dispatch(item):
            return host_dispatch(root, item)

        if root is not None and root.is_dir():
            await asyncio.to_thread(release, root, at=at, dispatch=dispatch)
        if extra_tick is not None:
            await extra_tick(at)

    return tick

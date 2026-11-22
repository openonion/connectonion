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
(run, status, stop, undo, result), and on this computer opens Terminal on its tmux session (watch) or
its finished session in Codex or Claude Code (resume) (#3138); POST /rem/talk is a conversation with the
agent about a row or an archived session (begin, say, read); POST /rem/review
records the owner's verdict on a review in 问题与关联 (reviews.decide); POST /rem/sender
ignores one mail sender from Today and the night's drafts, or undoes it (threads.ignore_sender);
POST /rem/direct-send sets one person's send policy, the owner's own Direct send line (direct_send.set_tier);
POST /rem/translate-all starts, follows or stops translating every page (translate.every_page).
POST /rem/investigate runs `co rem investigate PAGE --enrich` (or its quick and rewrite levels) for the
Investigate button, follows it step by step, and undoes it or accepts or discards a rewrite (page_runs).

Only loopback clients, and only a Host header naming loopback (a rebound DNS
name gets nothing), are answered. A translation runs in a worker thread; the
page polls the same POST until it is ready or failed.
"""

import asyncio
import hmac
import json
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


def _cookie(header: str) -> str:
    """This reader's cookie from the raw Cookie header. SimpleCookie drops every cookie when any other
    cookie on 127.0.0.1 (any port, any app) holds a space or a JSON value, which made every open tab
    answer 401 ("This page's session has ended") whenever such a cookie existed."""
    for part in header.split(";"):
        name, _, value = part.strip().partition("=")
        if name == COOKIE:
            return value.strip().strip('"')
    return ""


SESSION_ENDED = {
    "en": ("REM · session ended", "This page lost its session with REM.",
           "Open REM again on this computer; this tab picks up where it was.", "Try again"),
    "zh": ("REM · 会话已结束", "这个页面和 REM 的会话断开了。",
           "请在这台电脑上重新打开 REM；这个标签页会接着刚才的位置。", "重新打开"),
}


def _session_ended(headers: dict) -> str:
    """The 401 page: styled, in the reader's language (Accept-Language), with one button that tries again."""
    language = "zh" if headers.get("accept-language", "").lower().startswith("zh") else "en"
    title, lead, what, again = SESSION_ENDED[language]
    return (f'<!doctype html><html lang="{language}"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width, initial-scale=1">'
            f'<title>{title}</title><style>'
            ':root{color-scheme:light dark;--ink:#121512;--paper:#fff;--grey:#5f6360}'
            '@media (prefers-color-scheme:dark){:root{--ink:#eef0ed;--paper:#121512;--grey:#a3a7a4}}'
            'body{margin:0;min-height:100vh;display:grid;place-items:center;background:var(--paper);color:var(--ink);'
            'font:15px/1.7 -apple-system,BlinkMacSystemFont,"PingFang SC","Segoe UI",sans-serif}'
            'main{max-width:420px;padding:24px}h1{margin:0 0 8px;font-size:20px;font-weight:600}'
            'p{margin:0 0 20px;color:var(--grey)}button{min-height:44px;padding:0 20px;border:0;border-radius:999px;'
            'background:var(--ink);color:var(--paper);font:inherit;font-weight:600;cursor:pointer}</style></head>'
            f'<body><main><h1>{lead}</h1><p>{what}</p>'
            f'<button type="button" onclick="location.reload()">{again}</button></main></body></html>')


def _graph_3d_url() -> str:
    from ...rem.reader import GRAPH_3D_URL
    return GRAPH_3D_URL


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
        # Kept 30 days, so a browser restart or an upgrade's Host restart finds the tab still signed in.
        cookie = f"{COOKIE}={token}; HttpOnly; SameSite=Strict; Path=/rem; Max-Age=2592000"
        await _reply(send, 303, "", headers=[[b"location", b"/rem"], [b"set-cookie", cookie.encode()]])
        return
    if not _same(_cookie(headers.get("cookie", "")), token):
        # D-60: no command here either; the page speaks the browser's language and offers one button.
        await _reply(send, 401, _session_ended(headers), "text/html")
        return
    if scope["method"] == "GET" and scope["path"] in ("/rem", "/rem/data.json"):
        from ...rem.reader import cached_page
        # The saved page at once; a stale one is rebuilt by a detached process
        # and the open page reloads when /rem/version names a newer render.
        name = "live.html" if scope["path"] == "/rem" else "data.json"
        page, _ = await asyncio.to_thread(cached_page, root, name)
        await _reply(send, 200, page, "text/html" if name == "live.html" else "application/json")
    elif scope["method"] == "GET" and scope["path"] == _graph_3d_url():
        # The 3D graph's engine (#3309), pinned and vendored: only the live reader asks for it, the first time
        # the knowledge graph opens in 3D. Signed in like every other reader path.
        from ...rem.reader import GRAPH_3D
        await _reply(send, 200, await asyncio.to_thread(GRAPH_3D.read_text, encoding="utf-8"), "text/javascript")
    elif scope["method"] == "GET" and scope["path"] == "/rem/version":
        from ...rem.reader import latest
        await _reply(send, 200, json.dumps(await asyncio.to_thread(latest, root)), "application/json")
    elif scope["method"] == "GET" and scope["path"] == "/rem/task-file":
        await _task_file(scope, send, root)
    elif scope["method"] == "GET" and scope["path"] == "/rem/source":
        await _source(scope, send, root)
    elif scope["method"] == "POST" and scope["path"] == "/rem/translate":
        await _translate(scope, receive, send, root, headers)
    elif scope["method"] == "GET" and scope["path"] == "/rem/thread":
        from ...rem.threads import listing
        await _reply(send, 200, json.dumps(await asyncio.to_thread(listing, root)), "application/json")
    elif scope["method"] == "POST" and scope["path"] in ("/rem/keys/add", "/rem/keys/reveal", "/rem/keys/import", "/rem/keys/env"):
        await _keys(scope, receive, send, root, headers)
    elif scope["method"] == "POST" and scope["path"] in ("/rem/draft", "/rem/thread", "/rem/translation-request", "/rem/translate-all", "/rem/language", "/rem/approve", "/rem/task", "/rem/talk", "/rem/review", "/rem/sender", "/rem/person", "/rem/investigate", "/rem/direct-send"):
        await _action(scope, receive, send, root, headers)
    else:
        await _reply(send, 404, "not found")


async def _source(scope, send, root):
    """One cited source's retained excerpt, for a card the snapshot had no room for (#3165).

    The snapshot's excerpts share one budget across the notebook, mail first, so a project's files, sessions and
    commits rarely fit. Only what REM itself retained is read (the same readers as the snapshot), by a source id
    of a known kind; never a path the request names."""
    from ...rem.reader_model import SOURCE, cited_context
    value = parse_qs(scope.get('query_string', b'').decode('utf-8')).get('id', [''])[0]
    match = SOURCE.search(f"- [1] {value}") if value and len(value) <= 512 and "\n" not in value else None
    if not match or match[2] != value:
        await _reply(send, 404, 'not found')
        return
    found = await asyncio.to_thread(cited_context, root, [{'text': f"- [1] {value}"}], budget=200_000, private=True)
    context = found.get(value)
    if not context:
        await _reply(send, 404, 'not found')
        return
    await _reply(send, 200, json.dumps(context, ensure_ascii=False), 'application/json')


async def _task_file(scope, send, root):
    from ...rem import tasks
    from ...rem.files import RemError
    query = parse_qs(scope.get('query_string', b'').decode('utf-8'))
    try:
        path = tasks.task_file(root, query.get('id', [''])[0], query.get('path', [''])[0])
        content = await asyncio.to_thread(path.read_bytes)
    except (RemError, FileNotFoundError, PermissionError):
        await _reply(send, 404, 'not found')
        return
    # HTML/SVG and other active content are downloads, never scripts on the owner's Host origin.
    import mimetypes
    kind = mimetypes.guess_type(path.name)[0] or 'application/octet-stream'
    safe = kind.startswith('text/') and kind != 'text/html'
    kind = 'text/plain; charset=utf-8' if safe else 'application/octet-stream'
    await send({'type': 'http.response.start', 'status': 200,
                'headers': [[b'content-type', kind.encode()], *SECURITY_HEADERS,
                            [b'content-security-policy', b"sandbox; default-src 'none'"],
                            *([] if safe else [[b'content-disposition', b'attachment']])]})
    await send({'type': 'http.response.body', 'body': content})


def _moment_or_none(value) -> bool:
    """A put-off's `until` is absent or one ISO moment (threads.put_off_over reads it)."""
    from datetime import datetime
    if value is None:
        return True
    try:
        return isinstance(value, str) and len(value) <= 40 and bool(datetime.fromisoformat(value.replace("Z", "+00:00")))
    except ValueError:
        return False


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
        elif action == "status" and isinstance(body.get("key"), str):
            operation = lambda: tasks.status(root, tasks.identity(body["key"]))
        elif action == "clear_failed":
            operation = lambda: tasks.clear_failed(root)
        elif not isinstance(body.get("id"), str) or action not in ("status", "stop", "undo", "result", "watch", "resume", "retry", "prepare_reply"):
            await _reply(send, 400, json.dumps({"error": "Expected task id and action status, stop, undo, result, watch or resume"}), "application/json")
            return
        else:
            operation = lambda: getattr(tasks, action)(root, body['id'])
    elif scope["path"] == "/rem/investigate":
        # The Investigate button (#3105): {"page", "action": run|status|undo|accept|discard, "mode": full|quick|rewrite}.
        from ...rem import page_runs
        action, mode = body.get("action", "status"), body.get("mode", "full")
        if (not isinstance(body.get("page"), str) or action not in ("run", "status", "undo", "accept", "discard")
                or mode not in page_runs.MODES):
            await _reply(send, 400, json.dumps({"error": "Expected a page, action run, status, undo, accept or "
                                                         "discard, and level full, quick or rewrite"}), "application/json")
            return
        operation = (lambda: page_runs.start(root, body["page"], mode)) if action == "run" else (
            lambda: getattr(page_runs, action)(root, body["page"]))
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
                or body.get("state") not in ("done", "skipped", "ignored", "open")
                or not isinstance(body.get("device"), (str, type(None)))
                or not isinstance(body.get("keys"), (list, type(None)))
                or any(not isinstance(key, str) for key in body.get("keys") or [])
                or not isinstance(body.get("versions"), (dict, type(None)))
                or any(not isinstance(k, str) or not isinstance(v, str) for k, v in (body.get("versions") or {}).items())
                or not _moment_or_none(body.get("until"))):
            await _reply(send, 400, json.dumps({"error": "Expected thread key and state done, skipped, ignored or open"}), "application/json")
            return
        operation = lambda: threads.set_state(root, body["key"], body["state"], device=body.get("device"), versions=body.get("versions"), keys=body.get("keys"), until=body.get("until"))
    elif scope["path"] == "/rem/sender":
        from ...rem.files import EMAIL
        # 忽略 this sender from Today, or undo it: one address, never a pattern that could stop a whole domain.
        if (not isinstance(body.get("address"), str) or len(body["address"]) > 254
                or not EMAIL.fullmatch(body["address"]) or not isinstance(body.get("ignored"), bool)):
            await _reply(send, 400, json.dumps({"error": "Expected one mail address and ignored true or false"}), "application/json")
            return
        operation = lambda: {"ignored": threads.ignore_sender(root, body["address"], ignored=body["ignored"])}
    elif scope["path"] == "/rem/person":
        from ...rem.files import EMAIL
        # 不是人 / 是人 for one address, or null to let the rules decide again; never a domain.
        if (not isinstance(body.get("address"), str) or len(body["address"]) > 254
                or not EMAIL.fullmatch(body["address"]) or body.get("person") not in (True, False, None)):
            await _reply(send, 400, json.dumps({"error": "Expected one mail address and person true, false or null"}), "application/json")
            return
        operation = lambda: {"marks": threads.mark_person(root, body["address"], person=body["person"])}
    elif scope["path"] == "/rem/direct-send":
        # 以后直接发给他 / 以后先给我看 (#3121): one person's send policy, the owner's own line on their page.
        from ...rem import direct_send
        if (not isinstance(body, dict) or body.get("tier") not in direct_send.TIERS or not isinstance(body.get("page"), str)
                or not body["page"].startswith("people/") or ".." in body["page"] or not isinstance(body.get("reason", ""), str)):
            await _reply(send, 400, json.dumps({"error": "Expected a person's page and tier partner, close, none or never"}), "application/json")
            return
        operation = lambda: direct_send.set_tier(root, body["page"], body["tier"], body.get("reason", ""))
    elif scope["path"] == "/rem/language":
        from ...rem.config import request_language
        operation = lambda: request_language(root, body.get("language"))
    elif scope["path"] == "/rem/translate-all":
        # «全部翻译成中文»: start, follow or stop the job `co rem translate` runs (translate.every_page).
        if body.get("action", "status") not in ("start", "status", "stop") or not isinstance(body.get("language", ""), str):
            await _reply(send, 400, json.dumps({"error": "Expected action start, status or stop"}), "application/json")
            return
        operation = lambda: translate.every_page(root, body.get("action", "status"), body.get("language", ""))
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
    # A page run's status changes nothing until it has ended; then the page it changed shows now.
    if not (scope["path"] == "/rem/task" and body.get("action", "status") in ("status", "result", "watch", "resume")
            or scope["path"] == "/rem/investigate" and (body.get("action", "status") == "run"
                                                        or body.get("action", "status") == "status"
                                                        and (result or {}).get("result") == "running")
            or scope["path"] in ("/rem/talk", "/rem/translate-all")):
        await asyncio.to_thread(owner_changed, root)
    await _reply(send, 200, json.dumps(result or {"state": "saved"}), "application/json")


async def _keys(scope, receive, send, root, headers):
    """Keys (#3137). Like every /rem route, only this computer reaches it (``_local``) with the page's cookie, so a
    relayed or remote reader never can. A secret travels only in the reveal's reply and the add's body; neither is
    logged, and the reply is never cached."""
    from ...rem import keys
    from ...rem.files import RemError
    if headers.get("content-type", "").split(";")[0].strip() != "application/json":
        await _reply(send, 415, "application/json required")
        return
    try:
        body = json.loads(await read_body(receive, 4_000_000 if scope["path"] == "/rem/keys/import" else 8192) or b"{}")
    except (ValueError, UnicodeDecodeError):
        await _reply(send, 400, json.dumps({"error": "Invalid JSON"}), "application/json")
        return
    text = lambda name: body.get(name) if isinstance(body, dict) and isinstance(body.get(name), str) else ""  # noqa: E731
    action = scope["path"].rsplit("/", 1)[1]
    operations = {"add": lambda: {"page": keys.add(root, text("service"), text("account"), text("secret"),
                                                   purpose=text("purpose"), link=text("link"))},
                  "reveal": lambda: {"secret": keys.reveal(root, text("page"))},
                  "import": _key_import(keys, root, text("source"), text("csv")),
                  # co's own credentials: names and where the file is, never a value (#3305).
                  "env": lambda: keys.env_names()}
    try:
        result = await asyncio.to_thread(operations[action])
    except RemError as error:
        # The reason (no_gui, denied, timeout, ...) is what the reader turns into what to do (#3305). Not "code":
        # the reader's hostPost already uses that name for the HTTP status.
        reason = {"reason": error.code} if getattr(error, "code", "") else {}
        await _reply(send, 409, json.dumps({"error": str(error), **reason}), "application/json")
        return
    if action not in ("reveal", "env"):
        from ...rem.reader import owner_changed
        await asyncio.to_thread(owner_changed, root)
    await _reply(send, 200, json.dumps(result), "application/json")  # SECURITY_HEADERS carry no-store


def _key_import(keys, root, source: str, csv_text: str):
    """The import one /rem/keys/import body asks for: a browser, the macOS login keychain, or a CSV export."""
    if source == "keychain":
        return lambda: keys.import_keychain(root)
    if source:
        return lambda: keys.import_browser(root, source)
    return lambda: keys.import_csv(root, csv_text)


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

"""A fake of Notion's 2025-09-03 REST API for the read-only co notion tests.

It keeps pages, blocks, databases and data sources in memory and answers the
reads co notion makes: users/me, search, pages (and their paginated property
items), block children, databases, data sources and their queries, with
Notion's 10,000-result cap. Faults are injected per request: a 429, a 5xx, a
timeout. Every request is recorded in `sent` as (method, path, body); any
request it does not know fails the test.
"""

import itertools
import json
import re
from copy import deepcopy

import httpx

WORKSPACE = {"object": "user", "id": "bot-1", "type": "bot", "name": "co agent",
             "bot": {"owner": {"type": "workspace", "workspace": True}, "workspace_name": "Acme",
                     "workspace_id": "ws-acme"}}


def rich(text):
    return [{"type": "text", "plain_text": text, "text": {"content": text}}]


def uid(n):
    return f"{n:08x}-0000-4000-8000-{n:012x}"


def para(text, **extra):
    return {"type": "paragraph", "paragraph": {"rich_text": rich(text)}, **extra}


class FakeNotion:
    def __init__(self):
        self.pages, self.blocks, self.databases, self.sources = {}, {}, {}, {}
        self.sent, self.requests, self.faults = [], [], []
        self.ids = itertools.count(1000)
        self.workspace = deepcopy(WORKSPACE)
        # Notion stops one query at 10,000 results (has_more false, request_status incomplete).
        self.query_cap = 10_000
        # The guide warns the incomplete mark can come before the last page: True puts it on every page
        # of a capped query, cursors still valid up to the cap; False only on the last one.
        self.cap_marks_every_page = False
        # Tokens Notion accepts; None accepts any. Anything else gets 401 unauthorized, as a revoked
        # key does.
        self.accepted = None

    # -- building the workspace ------------------------------------------------

    def add_page(self, id, title, *, parent=None, properties=None, blocks=(), edited=None, url=None, created=None):
        props = properties or {"title": {"id": "title", "type": "title", "title": rich(title)}}
        page = {"object": "page", "id": id, "url": url or f"https://www.notion.so/{title.replace(' ', '-')}-{id.replace('-', '')}",
                "created_time": created or "2026-09-01T00:00:00.000Z",
                "last_edited_time": edited or "2026-10-01T09:30:00.000Z",
                "created_by": {"object": "user", "id": "user-ann"}, "in_trash": False,
                "parent": parent or {"type": "workspace", "workspace": True}, "properties": props}
        self.pages[id] = page
        self.set_blocks(id, list(blocks))
        return page

    def set_blocks(self, parent_id, blocks):
        stored = []
        for block in blocks:
            block = deepcopy(block)
            block.setdefault("object", "block")
            block.setdefault("id", uid(next(self.ids)))
            children = block.pop("children", None)
            block["has_children"] = bool(children)
            stored.append(block)
            if children:
                self.set_blocks(block["id"], children)
        self.blocks[parent_id] = stored

    def add_database(self, db_id, title, sources, *, parent_page=None):
        """`sources` is [(ds_id, name, properties)]."""
        self.databases[db_id] = {"object": "database", "id": db_id, "title": rich(title), "in_trash": False,
                                 "url": f"https://www.notion.so/{db_id.replace('-', '')}",
                                 "parent": {"type": "page_id", "page_id": parent_page} if parent_page
                                 else {"type": "workspace", "workspace": True},
                                 "data_sources": [{"id": ds, "name": name} for ds, name, _ in sources]}
        for ds, name, properties in sources:
            self.sources[ds] = {"object": "data_source", "id": ds, "title": rich(name), "properties": properties,
                                "parent": {"type": "database_id", "database_id": db_id},
                                "database_parent": self.databases[db_id]["parent"]}

    def add_row(self, ds_id, id, values, *, blocks=(), edited=None, created=None):
        properties = deepcopy(values)
        title = next(plain(p["title"]) for p in properties.values() if p.get("type") == "title")
        return self.add_page(id, title, parent={"type": "data_source_id", "data_source_id": ds_id,
                                                "database_id": self.sources[ds_id]["parent"]["database_id"]},
                             properties=properties, blocks=blocks, edited=edited, created=created)

    def fail(self, method, path_pattern, response, times=1):
        """The next `times` matching requests get `response` (an httpx.Response, or an exception instance)."""
        self.faults.append([method, re.compile(path_pattern), response, times])

    # -- the transport ----------------------------------------------------------
    def transport(self):
        return httpx.MockTransport(self.handle)

    def client(self):
        return httpx.Client(transport=self.transport())

    def handle(self, request):
        path = request.url.path.removeprefix("/v1/")
        body = json.loads(request.content) if request.content else {}
        self.requests.append(request)
        self.sent.append((request.method, path, body))
        token = request.headers.get("authorization", "").removeprefix("Bearer ")
        if self.accepted is not None and request.url.host == "api.notion.com" and token not in self.accepted:
            return httpx.Response(401, json={"object": "error", "status": 401, "code": "unauthorized",
                                             "message": "API token is invalid."})
        for fault in self.faults:
            method, pattern, response, times = fault
            if times and method == request.method and pattern.fullmatch(path):
                fault[3] -= 1
                if isinstance(response, Exception):
                    raise response
                return response
        try:
            return httpx.Response(200, json=self.answer(request.method, path, body, dict(request.url.params)))
        except LookupError:
            return httpx.Response(404, json={"object": "error", "status": 404, "code": "object_not_found",
                                             "message": f"Could not find object with ID: {path}."})
        except ValueError as error:
            return httpx.Response(400, json={"object": "error", "status": 400, "code": "validation_error",
                                             "message": str(error)})

    def _page_list(self, items, params, body):
        size = int(params.get("page_size") or body.get("page_size") or 100)
        start = int(params.get("start_cursor") or body.get("start_cursor") or 0)
        chunk = items[start:start + size]
        more = start + size < len(items)
        return {"object": "list", "results": chunk, "has_more": more, "next_cursor": str(start + size) if more else None}

    def answer(self, method, path, body, params):
        parts = path.split("/")
        if (method, path) == ("GET", "users/me"):
            return self.workspace
        if (method, path) == ("POST", "search"):
            wanted = (body.get("filter") or {}).get("value")
            query = (body.get("query") or "").casefold()
            found = []
            if wanted in (None, "page"):
                found += [p for p in self.pages.values() if query in title_of(p).casefold() and not p["in_trash"]]
            if wanted in (None, "data_source"):
                found += [s for s in self.sources.values()
                          if query in plain(self.databases[s["parent"]["database_id"]]["title"]).casefold()]
            if wanted == "database":
                raise ValueError("filter.value should be page or data_source")
            found.sort(key=lambda o: o.get("last_edited_time", ""), reverse=True)
            return self._page_list(found, params, body)
        if parts[0] == "pages" and len(parts) == 2:
            page = self.pages.get(parts[1])
            if page is None:
                raise LookupError
            if method == "GET":
                return page
        if parts[0] == "pages" and len(parts) == 4 and parts[2] == "properties":
            page = self.pages[parts[1]]
            prop = next(p for p in page["properties"].values() if p.get("id") == parts[3])
            items = [{"object": "property_item", "type": prop["type"],
                      prop["type"]: item} for item in prop.get("_all", prop.get(prop["type"]) or [])]
            return {**self._page_list(items, params, body), "property_item": {"type": prop["type"]}}
        if parts[0] == "blocks" and len(parts) == 2 and method == "GET":
            for blocks in self.blocks.values():
                for block in blocks:
                    if block["id"] == parts[1]:
                        return block
            raise LookupError
        if parts[0] == "blocks" and len(parts) == 3 and parts[2] == "children":
            if parts[1] not in self.blocks:
                raise LookupError
            if method == "GET":
                return self._page_list(self.blocks[parts[1]], params, body)
        if parts[0] == "databases" and method == "GET":
            found = self.databases.get(parts[1])
            if found is None:
                raise LookupError
            return found
        if parts[0] == "data_sources" and len(parts) == 2 and method == "GET":
            found = self.sources.get(parts[1])
            if found is None:
                raise LookupError
            return found
        if parts[0] == "data_sources" and len(parts) == 3 and parts[2] == "query":
            if parts[1] not in self.sources:
                raise LookupError
            rows = [p for p in self.pages.values() if (p["parent"].get("data_source_id") == parts[1])
                    and not p["in_trash"] and _matches(p, body.get("filter"))]
            for sort in reversed(body.get("sorts") or []):
                key = (lambda p, t=sort["timestamp"]: p[t]) if sort.get("timestamp") else \
                    (lambda p, n=sort["property"]: str(_flat(p["properties"].get(n))))
                rows.sort(key=key, reverse=sort["direction"] == "descending")
            listing = self._page_list(rows[:self.query_cap], params, body)
            if len(rows) > self.query_cap and (self.cap_marks_every_page or not listing["has_more"]):
                # The documented contract: no cursor past the cap, and the response says so.
                listing["request_status"] = {"type": "incomplete", "incomplete_reason": "query_result_limit_reached"}
            return listing
        raise AssertionError(f"unexpected request: {method} {path}")


def plain(rich_text):
    return "".join(part.get("plain_text") or part["text"]["content"] for part in rich_text or [])


def title_of(page):
    return next((plain(p["title"]) for p in page["properties"].values() if p.get("type") == "title"), "")


def _flat(prop):
    if not prop:
        return ""
    value = prop.get(prop["type"])
    if prop["type"] in ("title", "rich_text"):
        return plain(value)
    if isinstance(value, dict):
        return value.get("name") or value.get("start") or ""
    if isinstance(value, list):
        return ",".join(v.get("name", "") for v in value)
    return value


def _matches(page, condition):
    if not condition:
        return True
    if "and" in condition:
        return all(_matches(page, c) for c in condition["and"])
    if "timestamp" in condition:
        stamp = condition["timestamp"]
        (op, value), = condition[stamp].items()
        return {"after": page[stamp] > value, "on_or_after": page[stamp] >= value,
                "before": page[stamp] < value, "on_or_before": page[stamp] <= value,
                "equals": page[stamp][:10] == value}[op]
    prop = page["properties"].get(condition["property"])
    kind = next(k for k in condition if k != "property")
    (op, value), = condition[kind].items()
    actual = _flat(prop)
    if op == "equals":
        return actual == value
    if op == "does_not_equal":
        return actual != value
    if op == "contains":
        return value in (actual.split(",") if kind == "multi_select" else actual)
    if op == "does_not_contain":
        return value not in actual.split(",")
    if op == "is_empty":
        return actual in ("", None, [])
    if op == "is_not_empty":
        return actual not in ("", None, [])
    if op in ("greater_than", "after"):
        return actual is not None and actual > value
    if op in ("less_than", "before"):
        return actual is not None and actual < value
    raise AssertionError(op)

# Custom HTTP routes

Publish deterministic HTTP resources from the same process as your agent. No
LLM round trip is involved.

```python
from connectonion import Agent, HTTPResponse, HTTPRouter, host

http = HTTPRouter()


@http.public.get("/feeds/{category}.ics")
def calendar_feed(category: str):
    return HTTPResponse(
        build_ics(category),
        media_type="text/calendar; charset=utf-8",
        headers={"cache-control": "public, max-age=300"},
    )


@http.contacts.post("/preferences")
def save_preferences(request):
    return {"saved": request.json(), "for": request.identity}


@http.admin.post("/refresh")
def refresh(request):
    return {"started": True, "by": request.identity}


host(Agent("sydney-events"), http=http)
```

The resulting paths say who can call them:

| Python group | URL prefix | Audience |
|---|---|---|
| `http.public` | `/public` | Anyone; no signature |
| `http.contacts` | `/contacts` | Contacts, whitelisted callers, and admins |
| `http.admin` | `/admin` | Admins, including the agent owner |

The group owns both the prefix and the authorization rule. Connectonion stores
the audience on the route and checks that metadata before the handler runs; it
does not infer permission by splitting the incoming URL.

## Methods and parameters

The first release supports `GET` and `POST`. A path parameter is passed to a
handler by name:

```python
@http.public.get("/events/{event_id}")
def event(event_id: str):
    return {"id": event_id}
```

Declare `request` only when you need request details:

```python
@http.public.post("/subscribe")
def subscribe(request):
    email = request.json()["email"]
    source = request.query.get("source", [None])[0]
    return {"email": email, "source": source}
```

`HTTPRequest` provides:

- `method`, `path`, `headers`
- `query`: a mapping from each name to a list of values
- `path_params`
- `body`, `text`, and `json()`
- `identity`: the verified caller address on protected routes, otherwise `None`

Handlers may be synchronous or asynchronous.

## Responses

Return a `dict` or `list` for JSON, `str` for text, `bytes` for binary data, or
`None` for `204 No Content`. Use `HTTPResponse` when status, headers, or media
type matters:

```python
return HTTPResponse(
    body="BEGIN:VCALENDAR\n...",
    status=200,
    media_type="text/calendar; charset=utf-8",
    headers={"content-disposition": 'inline; filename="events.ics"'},
)
```

CORS headers are included on publisher responses and `OPTIONS` preflight
requests. Header values containing newlines are rejected.

## Calling protected routes

Protected requests use normal HTTP bodies plus `X-Co-*` signature headers. The
signature binds the method, path, canonical query, exact body digest,
timestamp, one-use request ID, and recipient agent address.

```python
import json
import httpx
from pathlib import Path

from connectonion import address
from connectonion.network.host.auth import sign_http_request

body = json.dumps({"topics": ["ai"]}, separators=(",", ":")).encode()
headers = sign_http_request(
    address.load(Path(".co")),
    "POST",
    "/contacts/preferences",
    body=body,
    recipient_address="0xAgentAddress",
)

response = httpx.post(
    "https://agent.example/contacts/preferences",
    content=body,
    headers={**headers, "content-type": "application/json"},
)
```

Pass the exact bytes sent on the wire to `sign_http_request`; changing the body
or query after signing is refused. A signature is one-use and cannot be replayed,
including when the ASGI app runs in multiple OS workers. The host keeps only a
short-lived digest in the project's `.co/replay.sqlite3`; raw signatures and
request bodies are not stored there. Each digest remains until the signed
timestamp is outside the accepted freshness window.

Never put an admin private key in browser JavaScript. An H5 admin application
needs a trusted backend or a future short-lived capability flow. Calendar apps
normally cannot add signature headers, so ordinary `.ics` subscriptions should
be public URLs.

## Route ownership

Publisher routes cannot replace framework endpoints. Duplicate route shapes,
current built-in paths, `/admin/trust/*`, `/superadmin/*`, and the permanent
framework namespace `/_co/*` fail during registration.

This is intentional: `/input`, `/ws`, `/health`, `/info`, sessions, and trust
management are SDK, deployment, and security contracts. Presentation routes
can gain explicit replacement options later without making silent shadowing an
extension mechanism.

## ASGI deployment

The same router works with `create_app`:

```python
from connectonion import create_app

app = create_app(create_agent, http=http)
```

`host()` and `create_app()` share the same raw-ASGI dispatcher, so local,
managed, and external uvicorn deployments behave the same way.

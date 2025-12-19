# HTTP Layer: Why Raw ASGI Instead of Starlette/FastAPI

*December 2025*

When implementing `host()`, we needed to choose how to handle HTTP and WebSocket requests. This document explains why we chose raw ASGI over established frameworks like Starlette or FastAPI.

---

## The Problem

The `host()` function needs to expose an agent over HTTP/WebSocket:

```
Client                                    Agent
   │                                        │
   │── POST /input ────────────────────────▶│
   │── GET /tasks/{id} ────────────────────▶│
   │── GET /health ────────────────────────▶│
   │── WS /ws ─────────────────────────────▶│
   │                                        │
```

Requirements:
1. **Simple for users** - Just `host(agent)`, no config
2. **Flexible for future** - Streaming, custom protocols, P2P
3. **Minimal dependencies** - Only uvicorn needed
4. **Transparent** - Easy to understand what happens

---

## Part I: What Others Do

### Option A: Build on Starlette

Most Python frameworks build on Starlette (FastAPI's foundation):

```python
from starlette.applications import Starlette
from starlette.routing import Route
from starlette.responses import JSONResponse

async def post_input(request):
    data = await request.json()
    result = agent.input(data["prompt"])
    return JSONResponse(result)

app = Starlette(routes=[
    Route("/input", post_input, methods=["POST"]),
    Route("/tasks/{task_id}", get_task),
    # ...
])
```

**Pros:**
- Clean routing syntax
- Request/Response objects
- Built-in test client (httpx)
- Middleware support (CORS, GZip)
- Industry standard

**Cons:**
- Additional dependency
- Framework lock-in
- Less control over protocol details

### Option B: Own Implementation (Sanic, BlackSheep)

Some frameworks implement their own HTTP layer:

| Framework | Approach | Why |
|-----------|----------|-----|
| **Sanic** | Own server + ASGI | Predates Starlette (2016), needed control |
| **BlackSheep** | Cython-optimized ASGI | Performance, ASP.NET-style patterns |
| **Litestar** | Custom (Starlette-inspired) | Different design philosophy |

### Option C: Rust Runtime (Robyn)

Robyn bypasses Python ASGI entirely - HTTP is handled in Rust:

```python
# Robyn: Python handlers, Rust HTTP server
@app.post("/input")
async def input(request):
    return agent.input(request.json()["prompt"])
```

**Pros:** Maximum performance (15-20% faster)
**Cons:** Not standard ASGI, different deployment model

---

## Part II: Our Analysis

### Performance Reality

From TechEmpower benchmarks:
```
Performance ranking:
1. Uvicorn (raw server)
2. Starlette (~same as uvicorn)
3. FastAPI (Starlette + Pydantic)
4. ...everything else
```

**Key insight:** Starlette adds essentially zero overhead.

### What Raw ASGI Gives Us

```python
async def app(scope, receive, send):
    # scope = method, path, headers, query_string
    # receive = get body chunks
    # send = send response chunks
```

Full control for:
- **Streaming responses** - Send chunks as agent thinks
- **Protocol hijacking** - Custom binary protocols
- **Server-Sent Events** - Real-time without WebSocket
- **P2P relay** - Custom agent-to-agent protocol
- **Early response** - Send headers before body ready

### What Starlette Would Save

Our raw ASGI code (~70 lines):
```python
async def handle_http(scope, receive, send, ...):
    method, path = scope["method"], scope["path"]
    if method == "POST" and path == "/input":
        body = await read_body(receive)
        data = json.loads(body)
        # ...
        await send_json(send, result)
```

With Starlette (~30 lines):
```python
async def post_input(request):
    data = await request.json()
    # ...
    return JSONResponse(result)
```

**Savings:** ~40 lines, cleaner syntax.

---

## Part III: Decision

**Use Raw ASGI**

### Reasons

1. **Full Control for Agent Protocols**
   - Future: streaming agent responses as they generate
   - Future: P2P relay connections
   - Future: agent-to-agent communication
   - Future: Server-Sent Events

2. **Zero Dependencies**
   - Only uvicorn (already needed)
   - Simpler dependency tree
   - No version conflicts

3. **Precedent**
   - Sanic chose own implementation
   - BlackSheep chose own implementation
   - Both prioritized control over convenience

4. **Transparency**
   - Code shows exactly what happens
   - Educational value for agent framework
   - Easy to debug

5. **Performance Equivalent**
   - Starlette adds ~zero overhead
   - No benefit to switching

### Trade-offs Accepted

We give up:
- Clean `Route("/path", handler)` syntax
- Built-in test client
- ~~Middleware helpers (CORS, GZip)~~ (we implemented CORS manually)
- ~40 lines of code

We gain:
- Full protocol control
- No framework lock-in
- Ability to implement custom protocols
- Clear understanding of what happens

### CORS Implementation (Added Dec 2025)

We implemented CORS manually in `asgi.py` with ~15 lines:

```python
CORS_HEADERS = [
    [b"access-control-allow-origin", b"*"],
    [b"access-control-allow-methods", b"GET, POST, OPTIONS"],
    [b"access-control-allow-headers", b"authorization, content-type"],
]

# Handle OPTIONS preflight
if method == "OPTIONS":
    headers = CORS_HEADERS + [[b"content-length", b"0"]]
    await send({"type": "http.response.start", "status": 204, "headers": headers})
    await send({"type": "http.response.body", "body": b""})
    return
```

This enables cross-origin requests from frontend (o.openonion.ai) to deployed agents (*.agents.openonion.ai).

---

## Part IV: Current Implementation

```
host.py (~360 lines)
├── Types           # Task dataclass
├── Storage         # JSONL persistence
├── Handlers        # Pure functions (input, task, tasks, health, info)
├── ASGI App        # create_app, handle_http, handle_websocket
├── Entry Point     # host()
└── Helpers         # read_body, send_json, extract_and_authenticate
```

Key functions:

```python
async def read_body(receive) -> bytes:
    """Read complete request body."""
    body = b""
    while True:
        m = await receive()
        body += m.get("body", b"")
        if not m.get("more_body"):
            break
    return body

async def send_json(send, data: dict, status: int = 200):
    """Send JSON response."""
    body = json.dumps(data).encode()
    await send({"type": "http.response.start", "status": status,
               "headers": [[b"content-type", b"application/json"]]})
    await send({"type": "http.response.body", "body": body})
```

---

## Part V: When We Might Reconsider

| Need | Consider |
|------|----------|
| Auto OpenAPI docs | Litestar |
| Complex middleware | Starlette |
| Maximum performance | Rust (Robyn/Granian) |
| Production-grade CORS | Starlette middleware |

But for agent hosting with custom protocols: **Raw ASGI is correct**.

---

## Summary

We chose raw ASGI because:

1. **Control** - Future streaming, P2P, custom protocols
2. **Simplicity** - One less dependency
3. **Transparency** - Clear what happens
4. **Precedent** - Sanic and BlackSheep did the same

The ~70 lines of HTTP/WS handling is a fair trade for full protocol control and zero framework dependencies.

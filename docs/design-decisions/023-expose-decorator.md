# @expose: Direct Function Calls on Hosted Agents

*March 2026*

Hosted agents expose one interface: `INPUT → LLM → tools → OUTPUT`. Every request goes through the LLM. This document proposes `@expose` — a decorator that makes agent functions directly callable over HTTP and WebSocket, bypassing the LLM.

---

## The Problem

A Liar's Dice game room agent needs:

```
GET  game state    → deterministic, no LLM needed
POST join game     → validation only, no LLM needed
POST submit bid    → rules check, no LLM needed
GET  spectate      → stream events, no LLM needed
```

But today, the only way to call an agent function is through `INPUT`:

```
Client → INPUT "what's the game state?" → LLM reasons → calls get_state() → OUTPUT
```

This is:
- **Slow** — LLM round-trip for a simple data fetch
- **Expensive** — tokens burned for deterministic operations
- **Unpredictable** — LLM might not call the right tool
- **Wrong abstraction** — not everything needs AI reasoning

---

## The Proposal

```python
from connectonion import Agent, host, expose

game = LiarDiceGame()

@expose(public=True)
def get_state() -> dict:
    """Current game state."""
    return game.public_state()

@expose
def make_bid(player_id: str, quantity: int, face: int) -> dict:
    """Submit a bid. Authenticated players only."""
    return game.process_bid(player_id, quantity, face)

def analyze_bluffs(agent) -> str:
    """Internal tool — LLM uses this to reason about strategy."""
    return analyze(agent.current_session['messages'])

agent = Agent("liar-dice", tools=[get_state, make_bid, analyze_bluffs])
host(agent)
```

Three functions, three access levels:
- `get_state` — exposed, public (anyone can call directly)
- `make_bid` — exposed, private (requires trust/auth)
- `analyze_bluffs` — NOT exposed (LLM-only, needs agent context)

---

## Three Layers, One Agent

```
Layer 3: INPUT     Client → LLM → tool → LLM → OUTPUT
                   Smart, expensive. Full reasoning.
                   All tools available to LLM.

Layer 2: CALL      Client → function → result
                   Fast, cheap. Direct invocation.
                   Only @expose functions.

Layer 1: INFO      Client → {name, tools, exposed, trust}
                   Discovery. What can I call?
```

The same function can serve both layers. `get_state` is a tool the LLM can use (Layer 3) AND a direct endpoint clients can call (Layer 2). The decorator just opens the second path.

---

## Consumer Experience

### Direct call (scripts, servers, other agents)

```python
room = connect("0xGameRoom")

# Layer 3: AI reasoning (existing)
advice = room.input("What's the best strategy right now?")

# Layer 2: direct call (NEW)
state = room.call("get_state")
room.call("make_bid", player_id="0xMe", quantity=3, face=5)

# Layer 1: discovery (existing, enhanced)
info = room.info()  # includes exposed functions with schemas
```

### As remote tools for another agent (the big idea)

```python
room = connect("0xGameRoom")

player = Agent(
    "poker-player",
    tools=[room.tools],        # exposed functions become remote tools
    model="co/gemini-2.5-pro"
)
player.input("It's your turn. Check the game state and make a bid.")
# → LLM sees get_state, make_bid as available tools
# → Calls get_state via CALL (no LLM on game room side)
# → Reasons about strategy
# → Calls make_bid via CALL
```

The game room's `@expose` functions travel across the network as tools for other agents. The provider writes Python with full power. The consumer's LLM reasons about them like local tools.

---

## Protocol

### WebSocket: CALL message type

```json
// Client → Server
{ "type": "CALL", "function": "get_state", "args": {} }

// Server → Client (success)
{ "type": "CALL_RESULT", "function": "get_state", "result": {"players": [...]} }

// Server → Client (error)
{ "type": "CALL_ERROR", "function": "get_state", "error": "game not started" }
```

No session, no LLM, no streaming. Function in, result out.

### HTTP: POST /call/{name}

```
POST /call/get_state
Body: {}
→ 200 { "result": {"players": [...]} }

POST /call/make_bid
Body: { "player_id": "0xMe", "quantity": 3, "face": 5 }
→ 200 { "result": {"accepted": true} }

POST /call/analyze_bluffs
→ 404 { "error": "not exposed" }
```

### Discovery: GET /info (enhanced)

```json
{
  "name": "liar-dice",
  "tools": ["get_state", "make_bid", "analyze_bluffs"],
  "exposed": [
    {
      "name": "get_state",
      "public": true,
      "description": "Current game state.",
      "parameters": {}
    },
    {
      "name": "make_bid",
      "public": false,
      "description": "Submit a bid. Authenticated players only.",
      "parameters": {
        "type": "object",
        "properties": {
          "player_id": { "type": "string" },
          "quantity": { "type": "integer" },
          "face": { "type": "integer" }
        },
        "required": ["player_id", "quantity", "face"]
      }
    }
  ]
}
```

---

## Auth Model

```
POST /call/get_state
  │
  ├─ @expose(public=True)?
  │   └─ YES → skip auth, execute
  │
  └─ NO → extract_and_authenticate(request, trust)
      ├─ allowed → execute
      └─ denied → 403
```

- `public=True` — no auth, anyone can call (spectators, anonymous clients)
- `public=False` (default) — uses agent's existing trust system (Ed25519 signature check)

Reuses `extract_and_authenticate()`. No new auth code.

---

## The Decorator

```python
def expose(fn=None, *, public=False):
    """Mark function as directly callable via HTTP/WS.

    @expose              → requires auth (agent's trust level)
    @expose(public=True) → no auth needed
    """
    def wrap(f):
        f._exposed = True
        f._exposed_public = public
        return f
    if fn is not None:
        return wrap(fn)
    return wrap
```

5 lines. Sets two attributes. `host()` discovers functions with `_exposed = True`.

---

## Integration with Existing Architecture

### What already exists and can be reused

| Component | What it does | Reuse for @expose |
|---|---|---|
| `tool_factory` | Converts functions → OpenAI schemas via type hints | Generate parameter schemas for exposed functions |
| `route_handlers` dict | All routes are functions in a dict | Add exposed functions to the dict |
| `handle_http()` | if/elif routing by path | Add `/call/{name}` pattern |
| `handle_websocket()` | msg_type switch | Add `CALL` message type |
| `extract_and_authenticate()` | Ed25519 signature verification | Auth for non-public exposed functions |
| `info_handler()` | Returns agent metadata | Add `exposed` array |
| `_needs_agent` flag | Tool factory detects `agent` parameter | Some exposed functions may need agent access |

### What needs to change (4 files, ~150 lines)

**1. `server.py` — discover exposed functions at startup**

In `_extract_agent_metadata()`, scan tools for `_exposed` attribute:

```python
exposed = []
for tool in sample.tools:
    if getattr(tool, '_exposed', False):
        exposed.append({
            "name": tool.name,
            "public": getattr(tool, '_exposed_public', False),
            "schema": tool.to_function_schema(),
            "func": tool.run,
        })
metadata["exposed"] = exposed
```

**2. `server.py` — add exposed functions to route handlers**

In `_create_route_handlers()`:

```python
# Add exposed functions
for item in agent_metadata.get("exposed", []):
    route_handlers[f"call_{item['name']}"] = item
```

**3. `asgi/http.py` — add /call/{name} route**

In `handle_http()`:

```python
elif method == "POST" and path.startswith("/call/"):
    func_name = path[6:]  # strip "/call/"
    exposed = route_handlers.get(f"call_{func_name}")
    if not exposed:
        await send_json(send, {"error": "not exposed"}, status=404)
        return

    # Auth check (skip for public)
    if not exposed["public"]:
        _, identity, sig_valid, err = route_handlers["auth"](data, trust)
        if err:
            await send_json(send, {"error": err}, status=403)
            return

    # Execute
    result = exposed["func"](**args)
    await send_json(send, {"result": result})
```

**4. `asgi/websocket.py` — add CALL message type**

After CONNECT/INPUT handling:

```python
if msg_type == "CALL":
    func_name = data.get("function")
    args = data.get("args", {})
    exposed = route_handlers.get(f"call_{func_name}")
    if not exposed:
        await send({"type": "websocket.send",
                   "text": json.dumps({"type": "CALL_ERROR", "function": func_name,
                                       "error": "not exposed"})})
        continue

    # Auth check for non-public (conn_authenticated from CONNECT)
    if not exposed["public"] and not conn_authenticated:
        await send({"type": "websocket.send",
                   "text": json.dumps({"type": "CALL_ERROR", "function": func_name,
                                       "error": "authenticate first"})})
        continue

    result = exposed["func"](**args)
    await send({"type": "websocket.send",
               "text": json.dumps({"type": "CALL_RESULT", "function": func_name,
                                   "result": result})})
    continue
```

**5. `routes.py` — enhance info_handler**

Add `exposed` to response:

```python
result["exposed"] = [
    {"name": e["name"], "public": e["public"],
     "description": e["schema"].get("description", ""),
     "parameters": e["schema"].get("parameters", {})}
    for e in agent_metadata.get("exposed", [])
]
```

---

## What We're NOT Doing (YAGNI)

| Feature | Why not now |
|---|---|
| Streaming @expose (generators) | Can use existing io.send() for push events |
| @expose on agent methods | Functions are the primitive, keep it simple |
| Per-function trust levels | public/private is enough. Full trust config can come later |
| GET /call/{name} for reads | POST-only keeps it simple. Add GET later if needed |
| Rate limiting per function | Agent-level trust handles this |
| TypeScript @expose equivalent | Python first. TS can expose via config |

---

## Usage Examples

### Game Room

```python
from connectonion import Agent, host, expose

game = LiarDiceGame()

@expose(public=True)
def get_state() -> dict:
    """Public game state for spectators."""
    return game.public_state()

@expose(public=True)
def get_rules() -> dict:
    """Game rules."""
    return {"name": "Liar's Dice", "players": "2-6", ...}

@expose
def join(player_address: str) -> dict:
    """Join the game. Requires auth."""
    return game.add_player(player_address)

@expose
def bid(player_address: str, quantity: int, face: int) -> dict:
    """Place a bid. Requires auth."""
    return game.process_bid(player_address, quantity, face)

@expose
def challenge(player_address: str) -> dict:
    """Challenge current bid. Requires auth."""
    return game.process_challenge(player_address)

agent = Agent("liar-dice", tools=[get_state, get_rules, join, bid, challenge])
host(agent)
```

### Data Service

```python
@expose(public=True)
def get_price(symbol: str) -> dict:
    """Get current stock price."""
    return fetch_price(symbol)

@expose
def get_portfolio(user_id: str) -> dict:
    """Get user's portfolio. Private."""
    return fetch_portfolio(user_id)

agent = Agent("stock-agent", tools=[get_price, get_portfolio, analyze_market])
host(agent)
```

### Agent-to-Agent

```python
# Provider: translation agent
@expose(public=True)
def translate(text: str, target: str) -> str:
    """Translate text to target language."""
    return do_translate(text, target)

agent = Agent("translator", tools=[translate])
host(agent)

# Consumer: another agent uses translator's exposed function
translator = connect("0xTranslator")
player = Agent("assistant", tools=[translator.tools])
player.input("Translate 'hello' to Spanish")
# → LLM calls translate via CALL (fast, no LLM on translator side)
```

---

## Summary

`@expose` adds Layer 2 (direct function calls) to agents that already have Layer 3 (LLM reasoning). The decorator is 5 lines. The implementation touches 4 files with ~150 lines. Everything else — schema generation, auth, routing — is reused from existing infrastructure.

The key insight: **exposed functions become remote tools for other agents**. A game room's `@expose` functions are the player agent's toolkit. The provider writes Python with full power. The consumer sees a clean RPC interface. The consumer's LLM can reason about them like local tools.

Simple things simple (direct function call). Complicated things possible (agent-to-agent tool sharing).

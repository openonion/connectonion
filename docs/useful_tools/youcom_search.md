# You.com Search Tools

Three agent tools — `youcom_search`, `youcom_contents`, `youcom_research` — give ConnectOnion agents current web search, URL content extraction, and cited research synthesis through the You.com API. All three are opt-in: without a `YDC_API_KEY` each returns an `auth_required` error dict and nothing leaves the machine.

## Quick Start

```python
from connectonion import Agent, youcom_search, youcom_contents, youcom_research

agent = Agent("researcher", tools=[youcom_search, youcom_contents, youcom_research])

result = agent.input("What are the latest developments in AI?")
```

The functions are plain functions, like `send_telegram` and `web_fetch`'s neighbours in `useful_tools/`. There is no class to instantiate and no state carried between calls — `YDC_API_KEY` is read at call time, so a key exported later in the session is picked up without re-creating anything.

## Environment Variables

### `YDC_API_KEY` (required)

```bash
export YDC_API_KEY="your-api-key-here"
```

Create a key at [you.com/platform/api-keys](https://you.com/platform/api-keys) and put it in `~/.co/keys.env` as `YDC_API_KEY`. All three tools require it; there is no unauthenticated path — a missing key returns `auth_required` rather than silently retrying against a different endpoint.

## Tools

### `youcom_search(query, count=10, freshness=None)`

Current web search.

- `query` (str): Search query
- `count` (int): Number of results, clamped to 1-20 (default: 10)
- `freshness` (str): Time filter — `'day'`, `'week'`, `'month'` or `'year'` (optional)

Returns You.com search results (titles, snippets, URLs), or an `{error, message}` dict.

### `youcom_contents(urls)`

Extract the text content of specific URLs. Accepts one URL or a list of up to 10 (longer lists are capped). Returns extracted content per URL, or an `{error, message}` dict.

### `youcom_research(query)`

One-shot cited synthesis of a research question. Returns a synthesized answer with citations, or an `{error, message}` dict.

## Error Handling

Every failure comes back as a dict with an `error` key — nothing raises past the tool boundary:

- `auth_required` — `YDC_API_KEY` missing or rejected. Same shape from all three tools.
- `payment_required` — You.com returned HTTP 402 (x402). An x402-aware client settles that outside this tool; setting `YDC_API_KEY` skips it.
- `search_failed` / `contents_failed` / `research_failed` — non-2xx You.com response or invalid body.
- `network_error` — transport failure, reported by exception class name only, so the key-bearing URL never reaches the agent.

## Usage Examples

### Research Agent

```python
from connectonion import Agent, youcom_research, youcom_search

agent = Agent(
    "researcher",
    system_prompt="You are a research assistant with web search. Always cite your sources.",
    tools=[youcom_search, youcom_research],
)
agent.input("What are the latest trends in sustainable technology?")
```

### Content Analyst

```python
from connectonion import Agent, youcom_contents

agent = Agent(
    "analyst",
    system_prompt="You analyze web content and provide insights.",
    tools=[youcom_contents],
)
agent.input("Analyze the content at https://docs.example.com")
```

## Security Considerations

- The API key is read from the environment at call time and never logged or echoed in error messages
- Network errors are reported by exception class name, not the exception string (which can contain the request URL)
- Web content returned by the tools is untrusted external data — treat it as evidence, not instructions
- No unauthenticated fallback exists: without a key the tools return `auth_required` and make no network request

## Troubleshooting

### `auth_required`

Set `YDC_API_KEY` (see above). If the key is set but rejected, check it at [you.com/platform/api-keys](https://you.com/platform/api-keys).

### `payment_required`

The call needs payment or a valid key. Setting `YDC_API_KEY` skips the x402 challenge for these endpoints.

### `network_error`

Check that `https://api.you.com` is reachable from the host.

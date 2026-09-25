# web_search and web_fetch

Search the web and read a page, the two tools skills written for Claude Code
or Codex assume every agent has. `co ai` carries both by default, and they are
also commands: [`co search` and `co fetch`](../cli/search.md).

```python
from connectonion import Agent, web_fetch, web_search

agent = Agent("researcher", tools=[web_search, web_fetch])
agent.input("What changed in the json module in Python 3.14? Cite the page.")
```

## web_search(query, engine="auto", count=10)

Returns numbered results: title, URL, snippet.

| engine | Results | Needs | Cost |
|---|---|---|---|
| `co` | Google, through ConnectOnion | `co auth` | per query, from your ConnectOnion credits |
| `serper` | Google, through serper.dev | `SERPER_API_KEY` | your Serper plan (free tier: 2,500 queries) |
| `brave` | Brave Search | `BRAVE_API_KEY` | your Brave plan (free tier monthly) |
| `ddg` | DuckDuckGo | nothing | free |
| `auto` (default) | first that answers: your own key, then `co`, then `ddg` | | |

When your credits run out, `auto` keeps working: it answers from DuckDuckGo
and adds a note saying why and how to get Google results back. An explicit
`engine="co"` returns the failure and names `--engine ddg` instead, so a
choice you made is never silently changed.

## web_fetch(url, prompt="", max_chars=20000)

Returns the page as Markdown: headings, lists, code blocks and absolute links,
without navigation, scripts or forms. With `prompt`, a small model
(`co/gemini-3.8-flash`) reads the page and returns only its answer. That's
cheaper for your main model when you need one fact from a long page.

What it refuses, and why:

- **Private addresses.** Any host resolving to loopback, a private range or
  link-local (e.g. the cloud metadata address `169.254.169.254`) is refused,
  on every redirect hop. The agent follows URLs it read on the web, and a
  page must not be able to point it at your intranet. Use `curl` through
  `bash` for local pages. That's a command you approve.
- **Redirects to another site.** Reported, not followed, so the agent sees
  where it is being sent. Redirects within a site (`example.com` →
  `www.example.com/new`) are followed.
- **Binary files and anything over 5 MB.** Download those with `curl`.

A page that renders with JavaScript comes back nearly empty. The result says
so and points at `co browser`.

Pages are cached for 15 minutes per process.

Results and pages are third-party text. Both tool descriptions tell the model
to treat instructions found in them as data.

## The older WebFetch class

[`WebFetch`](web_fetch.md) returns raw HTML and has LLM helpers for company
pages. It is unchanged; `web_fetch` is the one to give an agent that reads.

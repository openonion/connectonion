# co mcp

> Experimental. Built on Codex's app-server protocol, which Codex itself marks experimental.

Call the MCP servers and account connectors you already have in Codex
(Gmail, Google Calendar, GitHub, Vercel, your own servers) from the terminal,
with no second login and no model turn. Codex holds every credential; co
starts `codex app-server`, opens a throwaway session that never reaches your
Codex history, and asks it to run one tool.

```bash
co mcp ls                                   # servers, tool counts, auth state
co mcp tools codex_apps                     # one line per tool; read-only ones are marked
co mcp call codex_apps gmail.search_emails '{"query": "newer_than:7d"}'
```

`codex_apps` is the server behind the connectors you enabled in Codex or
ChatGPT. A server you added with `codex mcp add` appears under its own name.

## Reading and acting

Each tool says whether it only reads (`readOnlyHint`). A read-only tool runs
at once and prints its own data as JSON, unchanged. Any other tool — send an
email, create an issue, delete messages — prints what it would do and runs
only with `--yes`:

```bash
co mcp call codex_apps gmail.send_email '{"to": ["bo@example.com"], "subject": "Deck", "body": "Attached."}'
co mcp call codex_apps gmail.send_email '{"to": ["bo@example.com"], "subject": "Deck", "body": "Attached."}' --yes
```

## What it needs

- `codex` on PATH, logged in (`codex login`). Connectors are enabled in Codex
  or ChatGPT; co does not add or log in to any.
- Nothing from Claude Code. Its claude.ai connectors (Gmail, Drive, Calendar)
  are reachable only through a Claude turn (`claude -p --allowedTools
  mcp__claude_ai_Gmail__search_threads …`), which costs a model call; co mcp
  does not call them.

## Measured

On one Mac, 2026-10-11 (codex-cli 0.162.1): `codex_apps` listed 537 tools,
`gmail.get_profile` answered in 3.2 s and `gmail.search_emails` in 1.3 s, with
message and thread ids in the result. The same Gmail search through
`claude -p` on Haiku 4.5 took 12.2 s and $0.044.

## Errors

| You see | Do |
|---|---|
| `Codex is not installed` | `npm install -g @openai/codex && codex login` |
| `Codex has no MCP server named X` | `co mcp ls` |
| `X has no tool named Y` | `co mcp tools X` |
| a server shows `notLoggedIn` | `codex mcp login <server>` |

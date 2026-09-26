# ConnectOnion Auth (co auth)

One-time setup for managed models — no provider keys needed.

## Quick Start

```bash
# Authenticate with OpenOnion (required first)
co auth

# Optional: Connect Gmail, Drive, Calendar and YouTube
co auth google
```

What `co auth` does:
- Authenticates your agent and saves a secure token
- Token is saved to `~/.co/keys.env` as `OPENONION_API_KEY`
- If your project has a `.env`, it's updated too
- `~/.co/keys.env` gains `IS_EMAIL_ACTIVE=true`

`co auth login` is the same as bare `co auth`.

Check or undo it without signing in:

```bash
co auth status    # identity, token present or missing, Google/Microsoft/Feishu/Lark connections
co auth logout    # asks, then removes OPENONION_API_KEY; the keypair stays
```

- `co auth status` only reads. It never creates a keypair, never writes
  `keys.env` and makes no network call. On a fresh machine it says
  "Not signed in" and names `co auth login`. Balance and deployments need a
  signed request, so they stay with `co status`.
- `co auth logout` never deletes `~/.co/keys/`: the keypair *is* the account,
  so the next `co auth login` returns you to the same address and balance.
- Any other word (`co auth foo`) exits 2 and lists the valid ones. It used to
  fall through to sign-in.

What `co auth google` does:
- Requests the supported Gmail, Drive, Calendar and YouTube permissions by default
- Opens browser for OAuth authorization
- Saves credentials only locally in `~/.co/keys.env` and an existing project `.env`
- Accepts `--scopes youtube.readonly` (or a comma-separated subset) for restricted consent
- Running again will switch to a different Google account
- See [Google Integration](../integrations/google.md) for details

## Use Managed Models (co/ prefix)

```python
from connectonion import llm_do

response = llm_do("Hello", model="co/gpt-4o")
```

Works across providers:
- `co/gpt-4o`, `co/gpt-4o-mini`
- `co/claude-sonnet-4-5`, `co/claude-haiku-4-5`
- `co/llama` (default, free), `co/gemma` (free), `co/gemini-3.8-flash`, `co/gemini-3.7-flash` (rollback), `co/gemini-3.6-flash`, `co/gemini-3.5-flash`, `co/gemini-2.5-pro`, `co/gemini-2.5-flash`

## Troubleshooting

- Missing token? Run `co auth` again
- Network issue? Try again or check your connection
- Global vs project: `co auth` prefers local `.co` if keys exist, otherwise uses `~/.co`

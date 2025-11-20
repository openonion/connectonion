# ConnectOnion Auth (co auth)

One-time setup for managed models — no provider keys needed.

## Quick Start

```bash
# Authenticate with OpenOnion (required first)
co auth

# Optional: Connect your Google account for Gmail & Calendar
co auth google
```

What `co auth` does:
- Authenticates your agent and saves a secure token
- Token is saved to `~/.co/keys.env` as `OPENONION_API_KEY`
- If your project has a `.env`, it's updated too
- `.co/config.toml` gains `agent.email` and `email_active = true`

What `co auth google` does:
- Connects your Google account for Gmail Send and Calendar Read
- Opens browser for OAuth authorization
- Saves credentials to `.env` for your agents to use
- See [Google OAuth Guide](cli-auth-google.md) for details

## Use Managed Models (co/ prefix)

```python
from connectonion import llm_do

response = llm_do("Hello", model="co/gpt-4o")
```

Works across providers:
- `co/gpt-4o`, `co/gpt-4o-mini`
- `co/claude-3-5-sonnet`, `co/claude-3-5-haiku`
- `co/gemini-1.5-pro`, `co/gemini-1.5-flash`

## Troubleshooting

- Missing token? Run `co auth` again
- Network issue? Try again or check your connection
- Global vs project: `co auth` prefers local `.co` if keys exist, otherwise uses `~/.co`


# Deploy Your Agent

Get your agent running in production.

> **Beta**: `co deploy` is in beta. Works well but may change.

---

## Two Options

| Option | Best For |
|--------|----------|
| **`co deploy`** | Quick deployment, managed hosting |
| **Self-host** | Full control, your own infrastructure |

---

## co deploy (Easiest)

Deploy to ConnectOnion Cloud with one command.

```bash
cd my-agent
git init && git add -A && git commit -m "Initial commit"
co auth  # If not already authenticated
co deploy
```

**Output:**
```
Deploying to ConnectOnion Cloud...

  Project: my-agent
  Secrets: 3 keys

Uploading...
Building...

Deployed!
Agent URL: https://my-agent-0x7a9f3b2c.agents.openonion.ai
```

URL format: `{project_name}-{your_address[:10]}.agents.openonion.ai`

Re-deploying the same project updates the same URL (like Heroku).

### Requirements

- Git repository with committed code
- `.co/config.toml` (created by `co create` or `co init`)
- Authenticated (`co auth`)

### How It Works

```
co deploy → Upload source → We build and run → Returns URL
```

You upload source code, we handle the rest.

### Configuration

```toml
# .co/config.toml
[project]
name = "my-agent"
secrets = ".env"

[deploy]
entrypoint = "agent.py"
```

### Secrets

Secrets from `.env` are securely passed to your agent:

```bash
# .env
OPENAI_API_KEY=sk-xxx
DATABASE_URL=postgres://...
```

---

## Self-Host

Deploy to your own VPS or infrastructure using `host()`.

```python
# agent.py
from connectonion import Agent, host

agent = Agent("my-agent", tools=[my_tool])

# Export ASGI app for uvicorn/gunicorn
app = host.app(agent)

if __name__ == "__main__":
    host(agent)
```

Deploy with uvicorn, gunicorn, or any ASGI server:

```bash
# Direct
python agent.py

# Uvicorn
uvicorn agent:app --workers 4

# Gunicorn
gunicorn agent:app -w 4 -k uvicorn.workers.UvicornWorker
```

For full API reference, see [host()](host.md).

---

## When to Use Which

**Use `co deploy`:** Fastest path to production, no infrastructure management.

**Use self-hosting:** Full control, custom domains, compliance requirements.

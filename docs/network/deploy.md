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
co auth  # If not already authenticated
co deploy --skills ship-feature,review-pr
co deploy --skill ship-feature
co deploy --name agent-4-linkedin --skills linkedin
```

This deploys the built-in `co ai` coding agent with the selected skills. `--skill` is a singular alias for `--skills`. No project `agent.py`, `.co/host.yaml`, or git commit is required for this co-ai path.

```bash
co deploy --skills ship-feature --skills review-pr --model co/gemini-3-flash-preview
```

To deploy a traditional project agent instead, run `co deploy` from a ConnectOnion project with `.co/host.yaml` and a committed `host(...)` entrypoint, or pass `--template project`.

**Output:**
```
Deploying to ConnectOnion Cloud...

  Project: my-agent
  Package: 12.3 KB
  Env vars: 3 keys

Uploading...
Building...

Deployed!
Agent URL: https://my-agent-0x7a9f3b2c.agents.openonion.ai

Container logs:
  Agent started on port 8000
  Ready to serve
```

URL format: `{project_name}-{your_address[:10]}.agents.openonion.ai`

Re-deploying the same project name updates the same URL. Use `--name` for separate co-ai deployments such as `agent-4-linkedin` and `agent-4-sales`.

### Requirements

- Authenticated (`co auth`)
- `co deploy --skills ...` resolves skills from project `.co/skills/`, user `~/.co/skills/`, then built-in co-ai skills
- If a selected skill has `requirements.txt`, those Python dependencies are installed during the co-ai image build
- co-ai deploy env collection reads project `.env`, global `~/.co/keys.env`, and allowed API keys from the current process environment
- `--name` must use lowercase letters, numbers, and hyphens because it becomes part of the hosted agent URL
- Project deploys require a git repository, `.co/host.yaml`, and an entrypoint that calls `host()`

### How It Works

```
co deploy
  ├─ Choose mode: project if in a ConnectOnion project, otherwise co-ai
  ├─ Package: project git archive OR generated co-ai package
  ├─ Collect: load env vars from project .env, ~/.co/keys.env, and allowed API key env vars
  ├─ Upload: POST tarball + project_name + env_vars + entrypoint to API
  ├─ Build: backend builds Docker image, installs dependencies
  ├─ Run: starts container with your env vars injected
  ├─ Poll: checks status every 3s until running (or error)
  └─ Done: returns agent URL + container logs
```

For `co deploy --skills ...`, packaging creates a temporary self-contained co-ai app with the current ConnectOnion package source, `requirements.txt`, a generated `.co/deploy/co_ai_entrypoint.py`, and the selected `.co/skills/<name>/` directories. If a selected skill contains `requirements.txt`, the generated root `requirements.txt` references it. It does not read or modify your working tree except for resolving project-level skills if present.

**Step by step:**

1. **Validate locally** — checks that you have an `OPENONION_API_KEY`; project deploys also check git, `.co/host.yaml`, and `host()`
2. **Package source** — creates a generated co-ai package, or runs `git archive` for project deploys
3. **Collect env vars** — reads project `.env`, selected API keys from `~/.co/keys.env`, and selected API keys from the shell environment to inject into the container
4. **Upload** — sends the tarball, project name, entrypoint path, and env vars to the deploy API
5. **Build & run** — the backend builds a Docker image from your source, installs `requirements.txt`, and starts the container
6. **Poll status** — CLI checks deployment status every 3 seconds until the container is running or fails
7. **Show result** — prints the agent URL and fetches the first container logs so you can verify startup

Each deploy creates a new version. The last 5 versions are kept for rollback.

### Configuration

```yaml
# .co/host.yaml
name: my-agent          # Project name (used in URL)
entrypoint: agent.py    # Script to run in container
trust: careful          # Trust level for incoming requests

# Agent info — displayed on the frontend landing page
summary: "What your agent does"
examples:
  - "Example prompt 1"
  - "Example prompt 2"
```

### Environment Variables

Variables from your `.env` file are securely passed to your agent container:

```bash
# .env
OPENONION_API_KEY=eyJ...    # Required for co/ models
OPENAI_API_KEY=sk-xxx       # Third-party API keys
DATABASE_URL=postgres://...
```

---

## After Deployment

### Access Your Agent

Your deployed agent exposes these endpoints:

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/input` | POST | Send prompt, get response |
| `/ws` | WebSocket | Real-time streaming |
| `/info` | GET | Agent metadata (name, tools, trust, examples) |
| `/health` | GET | Health check |
| `/docs` | GET | Interactive API docs |
| `/admin/logs` | GET | Activity logs (requires API key) |

### Frontend (oo-chat)

Users can interact with your agent at:

```
https://chat.openonion.ai/{your_agent_address}
```

The landing page shows:
- Agent name, model, trust level
- Tools and skills your agent has
- `summary` and `examples` from `host.yaml` as suggested prompts
- Chat input for conversation

### Connect from Code

**Python SDK:**
```python
from connectonion import connect

agent = connect("0x7a9f3b2c...")
response = agent.input("Hello!")
print(response.text)
```

**HTTP:**
```bash
curl -X POST https://my-agent-0x7a9f3b2c.agents.openonion.ai/input \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Hello"}'
```

---

## Self-Host

Deploy to your own VPS or infrastructure using `host()`.

```python
# agent.py
from connectonion import Agent
from connectonion.network import host, create_app

agent = Agent("my-agent", tools=[my_tool])

# Export ASGI app for uvicorn/gunicorn
app = create_app(agent)

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

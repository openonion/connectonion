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
co auth  # If not already authenticated
co deploy
```

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

Re-deploying the same project updates the same URL (like Heroku).

### Requirements

- `.co/host.yaml` (created by `co create` or `co init`)
- Authenticated (`co auth`)
- Entrypoint must call `host()` (exports the ASGI app for the container)

### How It Works

```
co deploy
  ├─ Validate: .co/host.yaml? API key? entrypoint has host()?
  ├─ Package: git-tracked files when in a repo, otherwise initialized folder
  ├─ Collect: load env vars from .env
  ├─ Upload: POST tarball + project_name + secrets + entrypoint to API
  ├─ Build: backend builds Docker image, installs dependencies
  ├─ Run: starts container with your env vars injected
  ├─ Poll: checks status every 3s until running (or error)
  └─ Done: returns agent URL + container logs
```

**Step by step:**

1. **Validate locally** — checks that `.co/host.yaml` exists, you have an `OPENONION_API_KEY`, and your entrypoint file calls `host()`
2. **Package source** — in git repos, packages tracked files using their current working-tree contents; outside git, packages the initialized folder. Untracked files in a git repo are not deployed. Local-only files such as `.env`, `.co/keys`, caches, logs, docs, and build output are skipped.
3. **Collect env vars** — reads your `.env` file (API keys, database URLs, etc.) to inject into the container
4. **Upload** — sends the tarball, project name, entrypoint path, and secrets to the deploy API
5. **Build & run** — the backend builds a Docker image from your source, installs `requirements.txt`, and starts the container
6. **Poll status** — CLI checks deployment status every 3 seconds until the container is running or fails
7. **Show result** — prints the agent URL and fetches the first container logs so you can verify startup

Each deploy creates a new version. The last 5 versions are kept for rollback.

`co deploy --template <name>` is a shortcut for deploying any built-in template:
it creates a temporary `<name>-agent` project with the same code path as
`co create --template <name> -y`, deploys from that generated project, then
deletes the temporary folder after a successful deploy. If deploy fails, the
temporary project path is printed and kept for debugging.

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

## co-ai agent (skills + browser)

`co init --template co-ai` scaffolds a hosted coding agent — the same agent as
the `co ai` command, wrapped in `host()`, plus a `Dockerfile` that ships a real
Chrome + Xvfb browser runtime so browser tools work out of the box.

```bash
co init --template co-ai
co deploy
```

No `git init`/`commit` in between — `co deploy` packages the initialized folder
directly when no git repo exists (skipping `.env`, `.co/keys`, caches, and
docs), so the freshly scaffolded project deploys as-is.

For a one-command deploy that does not modify the current folder:

```bash
co deploy --template co-ai
```

That creates a temporary template project, deploys it, and cleans it up after
success. The same flow works for other built-in templates such as `minimal`,
`browser`, `coder`, and `web-research`.

### Skills

The deployed agent loads skills from `.co/skills/` via the normal loader.

- **Project skills** — skills under `.co/skills/` deploy with the project. In a
  git repo they must be tracked by git; outside git they are packaged from the
  initialized folder:
  ```bash
  co skills copy <name>          # lands in .co/skills/<name>/
  co deploy
  ```
- **External skills** — to bundle any skills folder that lives outside the
  project, pass `--skills PATH`
  (repeatable). The folder contents are copied into the container's
  `.co/skills/` (your working tree is untouched); on a name clash, later paths
  win:
  ```bash
  co deploy --skills /Users/changxing/project/OnCourse/platform/social-media-management-skills
  ```

> Your local `~/.claude/skills` are **not** auto-deployed. `co deploy` ships the
> project plus whatever `--skills` you name — not your whole local skill library.

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

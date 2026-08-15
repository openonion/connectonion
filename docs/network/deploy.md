# Deploy Your Agent

Get your agent running in production.

> **Beta**: `co deploy` is in beta. Works well but may change.

---

## Three Options

| Option | Best For | Identity survives a redeploy |
|--------|----------|------------------------------|
| **`co deploy`** | Quick deployment, managed hosting | no — a fresh container each time |
| **`co deploy --to <server>`** | A server you own, that you can ssh into | yes |
| **Self-host** | Full control, your own infrastructure | yours to arrange |

Pick the middle one when you want the agent to keep its address, its logs and any fix
you made by hand — and to answer on `https://<name>.agents.openonion.ai`. See
[co server](../cli/server.md).

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
  Source: /Users/me/my-agent
  Package: 12.3 KB (8 files)
  Env: /Users/me/my-agent/.env (3 keys)

Uploading package to https://oo.openonion.ai...
Deployment: a1b2c3d4
Building container on ConnectOnion Cloud...
  [1/100] status: deploying
  [2/100] status: running

Deployed!
Agent URL: https://my-agent-0x7a9f3b2c.agents.openonion.ai
Dashboard: https://o.openonion.ai/dashboard

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

`co deploy --template <name>` is a shortcut for deploying a template:
it creates `.tmp/connectonion-deploy/<name>-agent` with the same code path as
`co create --template <name> -y`, deploys from that generated project, then
deletes `.tmp/connectonion-deploy/` after a successful deploy. If deploy fails,
that folder is printed and kept for debugging. Template names are validated by
the same `co create` template logic, not by a separate deploy allowlist.

### Configuration

```yaml
# .co/host.yaml
name: my-agent          # Project name (used in URL) — see the rule below
entrypoint: agent.py    # Script to run in container
trust: careful          # Trust level for incoming requests

# Agent info — displayed on the frontend landing page
summary: "What your agent does"
examples:
  - "Example prompt 1"
  - "Example prompt 2"
```

**Naming rule.** `name` becomes a hostname and a Docker image tag, so it must be
1–39 characters of lowercase letters, digits, and hyphens, starting with a
letter or digit. `co create` and `co init` write a conforming name for you — a
project created in a folder called `My_Project` gets `name: my-project`, and the
adjustment is printed — so this only matters if you edit `host.yaml` by hand.
`co deploy` checks it before uploading and suggests the corrected form.

Two projects whose names reduce to the same thing (`My_Agent` and `my-agent`)
share one deployment URL, and deploying one replaces the other. Set `name`
explicitly if you want them kept apart.

### Environment Variables

Variables from your `.env` file are securely passed to your agent container:

```bash
# .env
OPENONION_API_KEY=eyJ...    # Required for co/ models
CONNECTONION_ADMIN_TOKEN=... # Optional: distinct 256-bit random token for admin monitoring
OPENAI_API_KEY=sk-xxx       # Third-party API keys
DATABASE_URL=postgres://...
BROWSER_PROXY=http://user:pass@host:port  # Optional browser proxy
```

`BROWSER_PROXY` is read by browser tools and routes browser egress through a proxy. See [Browser Tools › Proxy](../useful_tools/browser_tools.md#proxy).

---

## The agent you deploy (skills + browser)

`co create` and `co init --template co-ai` scaffold the same agent the `co ai`
command runs, wrapped in `host()`, plus a `Dockerfile` that ships a real
Chrome + Xvfb browser runtime so browser tools work out of the box.

There is one template. `agent.py` is about five lines, and you specialise it
with skills in `.co/skills/` rather than by starting from a different skeleton:

```python
from connectonion import host
from connectonion.cli.co_ai.agent import create_agent

agent = create_agent(role="coding")

host(agent)
```

`role` picks what kind of agent it is. `"coding"` adds software-engineering
doctrine — read before editing, match the surrounding style, `file:line`
references, git. An agent that posts to LinkedIn or answers support tickets
wants none of that, so pass `role=None`. Everything else — how it plans, asks,
reports, and handles actions it cannot take back — is shared, and improves when
the SDK does.

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

That creates `.tmp/connectonion-deploy/co-ai-agent`, deploys it, and cleans it up
after success. Any template supported by `co create --template <name>` uses the
same flow.

`--name` sets the project name (and URL) for a template deploy, so different
skill combinations of the same base template can run side by side:

```bash
co deploy --template co-ai --name linkedin-agent \
  --skills ~/skills/linkedin-login --skills ~/skills/linkedin-post-submit
```

### Skills

The deployed agent loads skills from `.co/skills/` via the normal loader.

- **Project skills** — skills under `.co/skills/` deploy with the project. In a
  git repo they must be tracked by git; outside git they are packaged from the
  initialized folder:
  ```bash
  co skills copy <name>          # lands in .co/skills/<name>/
  co deploy
  ```
- **External skills** — to bundle skills that live outside the project, pass
  `--skills PATH` (repeatable). A path that is itself a skill (contains
  `SKILL.md`) lands at `.co/skills/<dirname>/`; a directory of skills has its
  contents copied into `.co/skills/`. Your working tree is untouched; on a
  name clash, later paths win:
  ```bash
  co deploy --skills /Users/changxing/project/OnCourse/platform/social-media-management-skills
  co deploy --skills ~/skills/linkedin-login --skills ~/skills/linkedin-post-submit
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
| `/admin/logs` | GET | Activity logs (signed admin or dedicated admin token) |

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

## co deploy --to (a server you own)

```bash
co server new prod          # or: co server add prod --ssh you@1.2.3.4
co deploy --to prod
```

```
myagent → prod (co@1.2.3.4)
  converging server …
  syncing code …
  installing dependencies …
  configuring https …
  restarting …

✓ myagent is running on prod
  https://prod-abc.agents.openonion.ai — the certificate lands within a minute
  logs:  co server ssh prod 'journalctl -u myagent -f'
  state: /srv/myagent/.co/  — untouched by deploys
```

### What a deploy does

```
ensure(setup) → sync code → install deps if changed → authenticate live identity → write unit if changed → restart
```

`ensure(setup)` is idempotent and a no-op once the server is converged, which is why a
machine registered by hand needs no separate path: its **first** deploy is the one that
sets it up. A marker at `/srv/<agent>/.co/provision.json` is read in one ssh call to
decide whether to spend seconds or tens of seconds.

### What survives, and what does not

The rsync carries the project tree. Framework-owned state under `.co/` is
protected, while project-authored configuration and skills still travel:

| | |
|---|---|
| `.co/keys/` | **kept** — the agent's address, so its email and every trust relationship hold |
| `.co/logs/`, `.co/evals/` | **kept** — history a dashboard can actually show |
| `.co/skills/` | **synced** — skills are what the agent *is*, not state it accumulated |
| everything else in the project | synced, with `--delete`, so a deleted file goes away |

The project's root `.gitignore` is the boundary for its own generated state too.
An ignored path is neither uploaded nor deleted on the server. For example, an agent
that writes a cache under `work/` should include:

```gitignore
work/
```

The live `/srv/<agent>/work/` then survives every deploy, including files that exist
only on the server. Non-ignored source still follows the laptop and `--delete`, so a
source file removed locally is removed remotely. Keep large or irreplaceable state
outside `/srv/<agent>/` when possible; otherwise list it in `.gitignore` before the
first deploy.

### The agent runs as itself, not as you

Your project `.env` names *you*. `co init` puts `AGENT_ADDRESS`, `AGENT_EMAIL`,
`IS_EMAIL_ACTIVE` and `OPENONION_API_KEY` there on purpose, so the project runs on
your account while you are developing it.

On the server those four are wrong, and not inertly so: `AGENT_EMAIL` overrides the
mailbox the agent derives from its own address, and `OPENONION_API_KEY` decides whose
credits every model call spends. So the deploy **withholds them** and substitutes the
agent's own, authenticated from the key the server holds:

```
myagent → prod (co@1.2.3.4)
  …
  writing secrets … (5 keys)
  account 0xcf1619cb4c… — the agent's own
```

Everything else in `.env` — your Gemini key, your database URL — travels unchanged.

`--own-identity` mints the key on the machine, so this laptop cannot authenticate as
that agent and no account is written. The deploy says so and the agent has no access
to `co/*` models until you run `co auth` in `/srv/<agent>`:

```
  run co auth in /srv/myagent to give it one; co/* models need it
```

That is deliberate. An agent with no account fails visibly on its first model call;
an agent quietly spending its author's credits does not fail at all — and the spend
cannot be separated afterwards, because usage records carry no column naming the
machine that made the call.

### https and the hostname

A server created by `co server new` gets a DNS record of its own, and the deploy
installs Caddy in front of the agent. `AGENT_PUBLIC_DOMAIN` goes into the systemd unit
so the agent announces `https://<hostname>` to the relay rather than an IP and a port
that is closed — without it clients probe an endpoint that can never answer.

A hand-registered machine gets no https: there is no name of ours to get a certificate
for, and inventing one would fail the challenge rather than fail honestly.

One agent per hostname — there is one name and one `:443`.

### Admin

The deploy writes your **public address** into the agent's `.co/admins.txt`, every
time. A deployed agent generates its own keypair, and admin actions are gated on it,
so without this nobody could ever administer it — the only account that could grant
admin is the one nobody can sign as. Same idea as `ssh-copy-id`, one layer up: nothing
secret travels, and revoking is deleting a line.

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

**Use `co deploy`:** Fastest path to production, no infrastructure management. Right
until you need the agent to keep its address across deploys.

**Use `co deploy --to <server>`:** The agent keeps its identity, its logs and any fix
you made by hand, and it answers on its own https hostname. You can `ssh` in. Costs a
server ($30/month for the small one, charged yearly) — or nothing, if you point it at a
machine you already have.

**Use self-hosting:** Full control, custom domains, compliance requirements.

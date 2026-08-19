# 🧅 ConnectOnion

**Keep simple things simple, make complicated things possible.**

A template-first toolkit for FDEs building, debugging, deploying, and operating real AI agents.

<div align="center">

[![Production Ready](https://img.shields.io/badge/Status-Production_Ready-success?style=flat-square)](https://connectonion.com)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg?style=flat-square)](https://opensource.org/licenses/Apache-2.0)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10+-blue?style=flat-square&logo=python)](https://python.org)
[![PyPI Downloads](https://static.pepy.tech/personalized-badge/connectonion?period=total&units=international_system&left_color=black&right_color=green&left_text=downloads)](https://pepy.tech/projects/connectonion)
[![GitHub stars](https://img.shields.io/github/stars/openonion/connectonion?style=flat-square)](https://github.com/openonion/connectonion)
[![Contributors](https://img.shields.io/github/contributors/openonion/connectonion?style=flat-square)](https://github.com/openonion/connectonion/graphs/contributors)
[![Discord](https://img.shields.io/badge/Discord-Join-7289DA?style=flat-square&logo=discord)](https://discord.gg/4xfD9k8AUF)
[![Documentation](https://img.shields.io/badge/Docs-docs.connectonion.com-blue?style=flat-square)](http://docs.connectonion.com)

[📚 Documentation](http://docs.connectonion.com) • [💬 Discord](https://discord.gg/4xfD9k8AUF) • [⭐ Star Us](https://github.com/openonion/connectonion)

</div>

---

You don't assemble a framework stack. You start from a working template and a CLI that covers the whole delivery path:

```bash
pip install connectonion

co create sales-agent       # create from a working template
cd sales-agent
co ai                       # build and debug with COAI
co doctor                   # verify the environment
co deploy                   # deploy the Agent
co status                   # inspect what is running
```

That is the product. The Python runtime underneath is real and documented — but you reach for it when you need it, not before.

## Five minutes, start to running agent

`co create` gives you the same agent that powers `co ai`: files, shell, browser, planning, todos, sub-agents — hosted and reachable. You specialise it with skills in `.co/skills/`, not by rewriting a skeleton.

`co ai` opens an AI coding session that knows this codebase — in your terminal, or as a web chat at [chat.openonion.ai](https://chat.openonion.ai). It edits your project, runs your tests, and asks before doing anything destructive.

`co deploy` ships it. `co status` tells you what is running and which account pays for it. When something is off, `co doctor` names the missing piece instead of leaving you to guess.

No API key setup required to start: the default model runs on managed `co/` keys with starter credits. Bring your own OpenAI/Anthropic/Gemini key whenever you want.

## The toolkit, by job

Short list, not a reference — each command has a full page at [docs.connectonion.com](https://docs.connectonion.com).

### Start and build

| Command | What it does |
|---|---|
| `co create` / `co init` | New project from the working template, or add `.co/` to an existing one |
| `co ai` | AI coding session in your project — terminal or web chat |
| `co copy` | Copy any built-in tool's source into your project to modify |
| `co skills discover` / `copy` / `link` | Find, vendor, and share reusable SKILL.md workflows |

### Test and diagnose

| Command | What it does |
|---|---|
| `co doctor` | Diagnose the installation — names the missing piece |
| `co status` | Credential sources, account, balance, deployments |
| `co browser` | Drive one persistent browser: direct verbs or `co browser do "..."` |

### Deploy and operate

| Command | What it does |
|---|---|
| `co deploy` | Deploy to ConnectOnion Cloud, or `--to <server>` onto a machine you own |
| `co server new` / `add` / `ls` / `check` / `ssh` | Provision (pick a `--region`), register, preflight, and shell into servers |
| `co call` | Run one command on a remote agent and print the result — no LLM |

### Connect real work

| Command | What it does |
|---|---|
| `co email` | The agent's own mailbox — send, read, `share` an address with another account |
| `co gmail` / `co outlook` | Your Gmail and Outlook from the terminal (OAuth via `co auth`) |
| `co gdrive` | List, search, download, upload Google Drive files |

## What you get

- **Templates** — one working agent (`co-ai`), specialised with skills rather than forked into skeletons. It hosts, it deploys, it survives a redeploy with the same identity.
- **Toolkit** — the `co` CLI above, plus ready-to-use tools you import instead of wiring: `bash`, `Shell`, `FileTools`, `BrowserAutomation`, `Gmail`, `Outlook`, `GDrive`, `GoogleCalendar`, `Memory`, `TodoList`.
- **Runtime** — a Python framework where ordinary functions are tools, with lifecycle hooks, plugins, logging, and multi-provider LLM support. It is the enabling layer, not the starting point.
- **Open extension points** — every built-in tool, plugin, and skill is source you can copy into your project and change. Nothing is a black box:

```bash
co copy Gmail    # the Gmail tool's source lands in your project, yours to edit
```

## Ordinary functions become tools

The one Python idea to know: type hints and a docstring are the whole schema.

```python
from connectonion import Agent

def search(query: str) -> str:
    """Search for information."""
    return f"Results for {query}"

agent = Agent(
    name="assistant",
    system_prompt="You are a helpful assistant.",
    tools=[search],
)
print(agent.input("Search for Python tutorials"))
```

Every run is logged to `.co/logs/` automatically. Group related tools in a class and each public method becomes a tool — the instance keeps its state:

```python
class WeatherService:
    def __init__(self, api_key: str):
        self.api_key = api_key

    def current(self, city: str) -> str:
        """Get current weather for a city."""
        ...

agent = Agent("weather", tools=[WeatherService(api_key="...")])
```

A system prompt can be a string, a file path, or a `Path` — `Agent("support", system_prompt="prompts/support.md")` loads the file.

Debug interactively with `@xray` and `agent.auto_debug()` — breakpoints inside tool calls, inspect and edit local state, test "what if" values, continue:

```python
from connectonion import xray

@xray
def search_database(query: str) -> str:
    """Search for information."""
    ...

agent.auto_debug()   # pauses at every @xray tool
```

### Hooks and plugins

Thirteen lifecycle hooks fire through one agent turn — `after_user_input`, `before_llm`, `before_each_tool`, `after_tools`, `on_complete`, and the rest. A plugin is just a list of hook handlers:

```python
from connectonion.useful_plugins import re_act, auto_compact, subagents

agent = Agent("researcher", tools=[search], plugins=[
    re_act,        # reflect + plan after each tool call
    auto_compact,  # compress context near capacity
    subagents,     # spawn sub-agents with their own tools
])
```

These are the same capabilities coding agents like Claude Code keep internal — here they are source you can read, `co copy`, and change.

## Real delivery workflows

**Browser automation.** One persistent browser shared across sessions — logins survive restarts. Deterministic verbs for scripts, natural language when you want the agent to drive:

```bash
co browser go_to https://example.com
co browser take_screenshot /tmp/page.png
co browser do "log in and export this month's report"
```

**Skills.** A skill is a `SKILL.md` file the agent loads on demand, with automatic permission scoping — `/commit` loads the git skill, its commands are approved for that run, then the grant clears. Discovery is three-level: project `.co/skills/` beats user `~/.co/skills/` beats built-in. Claude Code skills in `.claude/skills/` load as-is.

**Deployment and remote operation.** Deploy to the cloud, or onto a machine you own:

```bash
co server new prod --region australia-southeast1   # provision a server you own
co deploy --to prod                                # sync code, restart the unit
co server ssh prod                                 # shell in whenever you want
co call <address> co status                        # operate a remote agent, no LLM
```

On your own server the agent keeps its address, its logs, and your hand-made 2am fixes across redeploys, and answers on its own https hostname.

**Communications.** The agent has its own email address from day one (`co email`). An address can be shared with another account — send rights without handing over a private key (`co email share`). Your own Gmail/Outlook/Drive connect through `co auth google` / `co auth microsoft`; tokens stay on your machine.

## Stable and Preview

**Stable** is what `pip install connectonion` gives you — the 1.6.x line this README describes. Every command shown here is exercised against it.

**Preview** is opt-in and marked as a pre-release on PyPI and GitHub. It carries the next feature train — currently the `co ai` coding-agent work (native Codex and Claude Code delegation with a live Work Room). Install an exact pre-release version to try it:

```bash
pip install connectonion==<exact-preview-version>   # see the releases page
```

Find current pre-release versions on the [GitHub releases page](https://github.com/openonion/connectonion/releases). Preview behavior can change between pre-releases; stable does not inherit it until it has been exercised end to end.

## Architecture and security boundaries

- **Permissions.** A hosted session runs under one of three profiles: **Read only** (every tool call asks a human; reads pass), **Auto** (reversible workspace work runs; external, destructive, or credential-touching operations ask), and **Full access** (approval-free, bounded by an explicit turn budget — `co ai --yolo --yolo-turns 20`). Plan is a workflow state, not a permission tier. The server owns this state; a client cannot talk itself into more authority.
- **Trust.** When agents call each other, trust decisions run before any LLM sees the request: `open` (dev), `careful` (staging — whitelist allows, unknown asks, blocked denies), `strict` (production). Configured in the operator's own `.co/host.yaml`; no environment variable can change it.
- **Identity.** An agent's address derives from a recovery phrase (standard SLIP-0010 derivation). A deployed agent runs under its own account and keys — not a copy of yours.
- **Credentials.** OAuth tokens for Google and Microsoft stay on the CLI machine. The backend does not store them.
- **Approvals.** Dangerous operations — shell commands, file deletion — trigger approval through a plugin you can inspect, replace, or turn off deliberately.

The layer below all of this is plain: `Agent` orchestrates LLM calls and tool execution, hooks fire at each lifecycle point, plugins are lists of hook handlers, and `host(agent)` makes any agent reachable over HTTP and the relay.

## Community and links

- **[Documentation](http://docs.connectonion.com)** — guides, CLI reference, concepts
- **[Examples](examples/)** — working agents to read and copy
- **[Discord](https://discord.gg/4xfD9k8AUF)** — get help, share what you build
- **[GitHub Issues](https://github.com/openonion/connectonion/issues)** — bugs and feature requests

### Contributing

ConnectOnion is open source and community-driven. Fork, branch, add tests, open a PR. See the [Contributing Guide](http://docs.connectonion.com/website-maintenance).

### License

Apache License 2.0 — use it anywhere, even commercially. See [LICENSE](LICENSE).

---

<div align="center">

[⭐ Star this repo](https://github.com/openonion/connectonion) • [💬 Join Discord](https://discord.gg/4xfD9k8AUF) • [📖 Read Docs](https://docs.connectonion.com) • [⬆ Back to top](#-connectonion)

</div>

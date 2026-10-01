<div align="center">

# ConnectOnion

**The agent CLI harness. CLI is all you need.**

One command line, `co`, gives your AI agent the accounts and tools it works with:<br>
Gmail and Outlook, a logged-in browser, your files, chat apps and other agents.

[![PyPI](https://img.shields.io/pypi/v/connectonion?style=flat-square)](https://pypi.org/project/connectonion/)
[![Python](https://img.shields.io/pypi/pyversions/connectonion?style=flat-square)](https://pypi.org/project/connectonion/)
[![Tests](https://img.shields.io/github/actions/workflow/status/openonion/connectonion/tests.yml?branch=main&style=flat-square&label=tests)](https://github.com/openonion/connectonion/actions/workflows/tests.yml?query=branch%3Amain)
[![License](https://img.shields.io/pypi/l/connectonion?style=flat-square)](LICENSE)
[![PyPI Downloads](https://static.pepy.tech/personalized-badge/connectonion?period=total&units=international_system&left_color=black&right_color=green&left_text=downloads)](https://pepy.tech/projects/connectonion)

[Website](https://www.connectonion.com) · [Docs](https://docs.connectonion.com) · [Quick start](docs/quickstart.md) · [Releases](https://github.com/openonion/connectonion/releases) · [Discord](https://discord.gg/4xfD9k8AUF)

</div>

<!-- connections -->
<!-- /connections -->

## Install

ConnectOnion needs Python 3.10 or newer.

```bash
pip install connectonion
```

## Quick start

```bash
co init              # create your identity and ~/.co/keys.env
co env               # show the settings commands will use; values stay hidden
co auth microsoft    # connect Outlook once (co auth google for Gmail)
co outlook           # read your inbox
co commands          # list every command; add --help to any of them
```

`co init` sets up your global configuration and leaves the current directory
alone; run `co init ./` to initialize a project. The
[Quick start guide](docs/quickstart.md) covers Google, the browser, chat apps
and project-specific settings.

## Why a CLI

- **Any agent that can run a shell can use it.** Claude Code, Codex, Cursor or
  an agent you wrote: there is nothing to import, and the transcript shows the
  same commands you would type yourself.
- **Credentials stay on your machine.** Google and Microsoft tokens are saved
  in `~/.co/keys.env`. The backend that refreshes them keeps none of them.
- **Commands name the next step.** A missing login ends with
  `Next: co auth microsoft`; a typo ends with the command you meant. An agent
  can recover without asking you.
- **Writes are explicit.** Each command's help says whether it is read-only or
  what it changes. Calendar, YouTube and Linear writes show a preview until you
  confirm, and in `co ai` a risky tool call waits for your approval.

## See it work

<picture>
  <source media="(prefers-reduced-motion: reduce) and (max-width: 600px)" srcset="https://www.connectonion.com/aha-search-mobile-poster.png">
  <source media="(prefers-reduced-motion: reduce)" srcset="https://www.connectonion.com/aha-search-poster.png">
  <source media="(max-width: 600px)" srcset="https://www.connectonion.com/aha-search-mobile.gif">
  <img alt="co search ConnectOnion printing an answer with its GitHub and website sources" src="https://www.connectonion.com/aha-search.gif">
</picture>

`co search ConnectOnion` answers from the web and cites its sources. The default
engine uses your own search key, then ConnectOnion credits;
`--engine ddg` is free.

## Use it from Claude Code, Codex or Cursor

A coding agent needs nothing but its shell. Ask it to “use `co` to check my
Outlook inbox”; it can read `co commands` and `co outlook --help` before it
acts.

Two optional shortcuts:

```bash
co skills link       # link ConnectOnion's skills into ~/.claude/skills and ~/.codex/skills
co skills discover   # find the skills Claude Code, Codex, Cursor and Kiro already have
```

See [`co skills`](docs/cli/skills.md) and the
[Claude Code plugin](docs/claude-code-plugin.md).

## Build your own agent

The same package is a Python framework. A tool is a plain function; its type
hints and docstring become the schema the model sees.

```python
from connectonion import Agent

def get_weather(city: str) -> str:
    """Return the current weather for a city."""
    return f"Sunny and 22°C in {city}"

agent = Agent("weather", tools=[get_weather])
print(agent.input("What's the weather in Sydney?"))
```

The default model is `co/gemini-3.8-flash` through ConnectOnion's managed keys,
which `co init` (or `co auth`) signs you in to. Pass `model=` to use your own OpenAI,
Anthropic or Gemini key, or a local model as `ollama/<model>`
([models](docs/concepts/models.md)).

To start from a working agent instead, `co create my-agent` scaffolds the same
agent that runs `co ai`, with files, shell, browser and sub-agents
([`co create`](docs/cli/create.md)). From there:

| Topic | Guide |
|---|---|
| Agents, prompts and iteration limits | [Agent](docs/concepts/agent.md) · [Prompts](docs/concepts/prompts.md) · [max_iterations](docs/concepts/max_iterations.md) |
| Tools, built-in tools and `co copy` | [Tools](docs/concepts/tools.md) · [Built-in tools](docs/useful_tools/README.md) · [`co copy`](docs/cli/copy.md) |
| Plugins and lifecycle hooks | [Plugins](docs/concepts/plugins.md) · [Events](docs/concepts/events.md) · [Built-in plugins](docs/useful_plugins/README.md) |
| Approval and skills | [tool_approval](docs/useful_plugins/tool_approval.md) · [Skills plugin](docs/useful_plugins/skills.md) |
| Debugging with `@xray` | [xray](docs/debug/xray.md) · [auto_debug](docs/debug/auto_debug.md) · [Logs](docs/debug/log.md) |
| Hosting, trust and deploy | [host()](docs/network/host.md) · [Trust](docs/features/trust.md) · [Deploy](docs/network/deploy.md) |

The [full documentation](https://docs.connectonion.com) has the rest.

## Stable and preview releases

ConnectOnion ships on two channels. **Stable**, currently 1.8.10, is what
`pip install connectonion` installs. **Preview** builds, currently the
1.9.0aN alphas, carry new features before they are stable; install one by
pinning its exact version. [docs/releases.md](docs/releases.md) explains both
channels, and every version has notes on
[GitHub Releases](https://github.com/openonion/connectonion/releases).

## Community

Ask questions in
[GitHub Discussions](https://github.com/openonion/connectonion/discussions),
report bugs in [Issues](https://github.com/openonion/connectonion/issues), or
talk to the team on the Discord server linked at the top of this page. If
ConnectOnion is useful to you, starring the repository helps others find it.

## Contributing

Contributions are welcome. [CONTRIBUTING.md](CONTRIBUTING.md) covers the
development setup, tests, the repository layout and what we ask of
AI-assisted pull requests. Everyone taking part follows the
[Code of Conduct](CODE_OF_CONDUCT.md).

## Security

Please do not report vulnerabilities in public issues.
[SECURITY.md](SECURITY.md) explains how to report one privately.

## License

[Apache-2.0](LICENSE).

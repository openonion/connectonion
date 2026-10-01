<div align="center">

# ConnectOnion

**The agent CLI harness. CLI is all you need.**

One command line, `co`, gives your AI agent the accounts and tools it works with:
Gmail and Outlook, a logged-in browser, your files, chat apps and other agents.

[![PyPI](https://img.shields.io/pypi/v/connectonion?style=flat-square)](https://pypi.org/project/connectonion/)
[![Python](https://img.shields.io/pypi/pyversions/connectonion?style=flat-square)](https://pypi.org/project/connectonion/)
[![Tests](https://img.shields.io/github/actions/workflow/status/openonion/connectonion/tests.yml?branch=main&style=flat-square&label=tests)](https://github.com/openonion/connectonion/actions/workflows/tests.yml?query=branch%3Amain)
[![License](https://img.shields.io/pypi/l/connectonion?style=flat-square)](LICENSE)
[![PyPI Downloads](https://static.pepy.tech/personalized-badge/connectonion?period=total&units=international_system&left_color=black&right_color=green&left_text=downloads)](https://pepy.tech/projects/connectonion)

[Website](https://www.connectonion.com) · [Docs](https://docs.connectonion.com) · [Quick start](docs/quickstart.md) · [Releases](https://github.com/openonion/connectonion/releases) · [Discord](https://discord.gg/4xfD9k8AUF)

</div>

<!-- connections: generated, do not edit by hand. Refresh with
     curl -s https://www.connectonion.com/connections.md
     and paste the output between these two comments. -->
<p><b>Mail, calendar &amp; notes</b><br>
<a href="docs/cli/gmail.md"><img src="https://www.connectonion.com/logos/gmail.svg" width="40" height="40" alt="Gmail" title="Gmail · co gmail"></a>
<a href="docs/cli/outlook.md"><img src="https://www.connectonion.com/logos/outlook.svg" width="40" height="40" alt="Outlook" title="Outlook · co outlook"></a>
<a href="docs/cli/gcalendar.md"><img src="https://www.connectonion.com/logos/gcal.svg" width="40" height="40" alt="Google Calendar" title="Google Calendar · co gcalendar"></a>
<a href="docs/cli/gcalendar.md"><img src="https://www.connectonion.com/logos/meet.svg" width="40" height="40" alt="Google Meet" title="Google Meet · co gcalendar meet"></a>
<a href="docs/cli/onenote.md"><img src="https://www.connectonion.com/logos/onenote.svg" width="40" height="40" alt="OneNote" title="OneNote · co onenote"></a>
<a href="docs/cli/outlook.md"><img src="https://www.connectonion.com/logos/teams.svg" width="40" height="40" alt="Teams meetings" title="Teams meetings · co outlook calendar"></a></p>

<p><b>Chat apps</b><br>
<a href="docs/cli/whatsapp.md"><img src="https://www.connectonion.com/logos/whatsapp.svg" width="40" height="40" alt="WhatsApp" title="WhatsApp · co whatsapp"></a>
<a href="docs/cli/telegram.md"><img src="https://www.connectonion.com/logos/telegram.svg" width="40" height="40" alt="Telegram" title="Telegram · co telegram"></a>
<a href="docs/cli/discord.md"><img src="https://www.connectonion.com/logos/discord.svg" width="40" height="40" alt="Discord" title="Discord · co discord"></a>
<a href="docs/cli/slack.md"><img src="https://www.connectonion.com/logos/slack.svg" width="40" height="40" alt="Slack" title="Slack · co slack"></a>
<a href="docs/cli/feishu.md"><img src="https://www.connectonion.com/logos/feishu.svg" width="40" height="40" alt="Feishu / Lark" title="Feishu / Lark · co feishu, co lark"></a></p>

<p><b>Browser &amp; files</b><br>
<a href="docs/cli/browser.md"><img src="https://www.connectonion.com/logos/chrome.svg" width="40" height="40" alt="Your Chrome" title="Your Chrome · co browser"></a>
<a href="docs/cli/gdrive.md"><img src="https://www.connectonion.com/logos/gdrive.svg" width="40" height="40" alt="Google Drive" title="Google Drive · co gdrive"></a>
<a href="docs/cli/youtube.md"><img src="https://www.connectonion.com/logos/youtube.svg" width="40" height="40" alt="YouTube" title="YouTube · co youtube"></a>
<a href="docs/cli/synology.md"><img src="https://www.connectonion.com/logos/syno.svg" width="40" height="40" alt="Synology NAS" title="Synology NAS · co syno"></a></p>

<p><b>Issues &amp; feedback</b><br>
<a href="docs/cli/linear.md"><img src="https://www.connectonion.com/logos/linear.svg" width="40" height="40" alt="Linear" title="Linear · co linear"></a>
<a href="docs/cli/canny.md"><img src="https://www.connectonion.com/logos/canny.svg" width="40" height="40" alt="Canny" title="Canny · co canny"></a></p>

<p><b>Coding agents</b><br>
<a href="docs/claude-code-plugin.md"><img src="https://www.connectonion.com/logos/claude.svg" width="40" height="40" alt="Claude Code" title="Claude Code · co claude"></a>
<a href="docs/cli/skills.md"><img src="https://www.connectonion.com/logos/codex.svg" width="40" height="40" alt="Codex" title="Codex · co skills link"></a>
<a href="docs/cli/skills.md"><img src="https://www.connectonion.com/logos/cursor.svg" width="40" height="40" alt="Cursor" title="Cursor · co skills discover"></a>
<a href="docs/cli/skills.md"><img src="https://www.connectonion.com/logos/kiro.svg" width="40" height="40" alt="Kiro" title="Kiro · co skills discover"></a></p>

<p><b>Models</b><br>
<a href="docs/concepts/models.md"><img src="https://www.connectonion.com/logos/openai.svg" width="40" height="40" alt="OpenAI" title="OpenAI · gpt-…"></a>
<a href="docs/concepts/models.md"><img src="https://www.connectonion.com/logos/anthropic.svg" width="40" height="40" alt="Anthropic" title="Anthropic · claude-…"></a>
<a href="docs/concepts/models.md"><img src="https://www.connectonion.com/logos/gemini.svg" width="40" height="40" alt="Gemini" title="Gemini · gemini-…"></a>
<a href="docs/concepts/models.md"><img src="https://www.connectonion.com/logos/mistral.svg" width="40" height="40" alt="Mistral" title="Mistral · mistral/…"></a>
<a href="docs/concepts/models.md"><img src="https://www.connectonion.com/logos/groq.svg" width="40" height="40" alt="Groq" title="Groq · groq/…"></a>
<a href="docs/concepts/models.md"><img src="https://www.connectonion.com/logos/grok.svg" width="40" height="40" alt="Grok" title="Grok · grok/…"></a>
<a href="docs/concepts/models.md"><img src="https://www.connectonion.com/logos/openrouter.svg" width="40" height="40" alt="OpenRouter" title="OpenRouter · openrouter/…"></a>
<a href="docs/concepts/local-models.md"><img src="https://www.connectonion.com/logos/ollama.svg" width="40" height="40" alt="Ollama (local)" title="Ollama (local) · ollama/…"></a></p>

<p><b>Built into co</b><br>
0x address <code>co init</code> · Agent mailbox <code>co email</code> · Memory <code>co wiki</code> · Secrets <code>co env</code> · Credits <code>co transfer</code> · SMS <code>co sms</code> · Remote browser <code>co remote-browser</code> · Web search <code>co search</code> · Your skills <code>co skills</code> · Shared skills <code>co sub</code> · Evals <code>co eval</code> · Managed keys <code>co/… ($5 credit)</code> · Remote agents <code>co call</code> · Your internet <code>co proxy</code> · Your servers <code>co deploy --to</code> · SSH <code>co server ssh</code> · Schedules <code>co schedule</code></p>
<!-- /connections -->

## Install

ConnectOnion needs Python 3.10 or newer.

```bash
pip install connectonion
```

## Quick start

```bash
# your identity and ~/.co/keys.env
co init
# settings in use, values hidden
co env
# connect Outlook once
co auth microsoft
# read your inbox
co outlook
# every command; add --help to any
co commands
```

For Gmail, use `co auth google` and `co gmail`. `co init` sets up your global configuration and leaves the current directory
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

- `co skills link` links ConnectOnion's skills into `~/.claude/skills` and
  `~/.codex/skills`.
- `co skills discover` lists the skills Claude Code, Codex, Cursor and Kiro
  already have.

See [`co skills`](docs/cli/skills.md) and the
[Claude Code plugin](docs/claude-code-plugin.md).

## Build your own agent

The same package is a Python framework. A tool is a plain function; its type
hints and docstring become the schema the model sees.

```python
from connectonion import Agent

def weather(city: str) -> str:
    """Current weather for a city."""
    return f"Sunny, 22°C in {city}"

agent = Agent("bot", tools=[weather])
print(agent.input("Weather in Sydney?"))
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

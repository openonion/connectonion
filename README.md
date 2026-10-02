<div align="center">

<img src="https://www.connectonion.com/favicon.png" width="96" height="96" alt="ConnectOnion logo">

# ConnectOnion

**The agent CLI harness. CLI is all you need.**

One command line, `co`, gives your AI agent the accounts and tools it works with:
Gmail and Outlook, a logged-in browser, your files, chat apps and other agents.
Its `--help` pages are the agent's instructions, and the agent finds them itself:
no MCP server, tool schema or skill file to set up.

[![PyPI](https://img.shields.io/pypi/v/connectonion?style=flat-square)](https://pypi.org/project/connectonion/)
[![Python](https://img.shields.io/pypi/pyversions/connectonion?style=flat-square)](https://pypi.org/project/connectonion/)
[![Tests](https://img.shields.io/github/actions/workflow/status/openonion/connectonion/tests.yml?branch=main&event=push&style=flat-square&label=tests)](https://github.com/openonion/connectonion/actions/workflows/tests.yml?query=branch%3Amain)
[![License](https://img.shields.io/pypi/l/connectonion?style=flat-square)](LICENSE)
[![PyPI Downloads](https://static.pepy.tech/personalized-badge/connectonion?period=total&units=international_system&left_color=black&right_color=green&left_text=downloads)](https://pepy.tech/projects/connectonion)

[Website](https://www.connectonion.com) · [Docs](https://docs.connectonion.com) · [Quick start](docs/quickstart.md) · [Releases](https://github.com/openonion/connectonion/releases) · [Discord](https://discord.gg/4xfD9k8AUF)

</div>

<p align="center">
  <a href="https://www.connectonion.com/#film"><img src="https://www.connectonion.com/promo/highlight.gif?v=2" width="360" alt="Real co 1.8.10 runs: co browser reads the top Hacker News story, co search and co fetch answer with sources, co email sends from the agent's own address, and co ai hands a task to Codex and Claude Code"></a><br>
  <sub>Real output from co 1.8.10. <a href="https://www.connectonion.com/#film">Watch the 43-second film →</a></sub>
</p>

<!-- connections: generated, do not edit by hand. Refresh with
     curl -s https://www.connectonion.com/connections.md
     and paste the output between these two comments. -->
<p><b>Identity &amp; memory</b><br>
<a href="docs/cli/init.md"><img src="https://www.connectonion.com/logos/address.svg?v=2" width="80" height="80" alt="0x address" title="0x address · co init"></a>
<a href="docs/cli/email.md"><img src="https://www.connectonion.com/logos/mailbox.svg?v=2" width="80" height="80" alt="Agent mailbox" title="Agent mailbox · co email"></a>
<a href="docs/cli/rem.md"><img src="https://www.connectonion.com/logos/memory.svg?v=2" width="80" height="80" alt="Memory" title="Memory · co wiki"></a>
<a href="docs/cli/env.md"><img src="https://www.connectonion.com/logos/secrets.svg?v=2" width="80" height="80" alt="Secrets" title="Secrets · co env"></a>
<a href="docs/cli/README.md"><img src="https://www.connectonion.com/logos/credits.svg?v=2" width="80" height="80" alt="Credits" title="Credits · co transfer"></a></p>

<p><b>Mail, calendar &amp; notes</b><br>
<a href="docs/cli/gmail.md"><img src="https://www.connectonion.com/logos/gmail.svg?v=2" width="80" height="80" alt="Gmail" title="Gmail · co gmail"></a>
<a href="docs/cli/outlook.md"><img src="https://www.connectonion.com/logos/outlook.svg?v=2" width="80" height="80" alt="Outlook" title="Outlook · co outlook"></a>
<a href="docs/cli/gcalendar.md"><img src="https://www.connectonion.com/logos/gcal.svg?v=2" width="80" height="80" alt="Google Calendar" title="Google Calendar · co gcalendar"></a>
<a href="docs/cli/gcalendar.md"><img src="https://www.connectonion.com/logos/meet.svg?v=2" width="80" height="80" alt="Google Meet" title="Google Meet · co gcalendar meet"></a>
<a href="docs/cli/onenote.md"><img src="https://www.connectonion.com/logos/onenote.svg?v=2" width="80" height="80" alt="OneNote" title="OneNote · co onenote"></a>
<a href="docs/cli/outlook.md"><img src="https://www.connectonion.com/logos/teams.svg?v=2" width="80" height="80" alt="Teams meetings" title="Teams meetings · co outlook calendar"></a></p>

<p><b>Chat apps</b><br>
<a href="docs/cli/whatsapp.md"><img src="https://www.connectonion.com/logos/whatsapp.svg?v=2" width="80" height="80" alt="WhatsApp" title="WhatsApp · co whatsapp"></a>
<a href="docs/cli/telegram.md"><img src="https://www.connectonion.com/logos/telegram.svg?v=2" width="80" height="80" alt="Telegram" title="Telegram · co telegram"></a>
<a href="docs/cli/discord.md"><img src="https://www.connectonion.com/logos/discord.svg?v=2" width="80" height="80" alt="Discord" title="Discord · co discord"></a>
<a href="docs/cli/slack.md"><img src="https://www.connectonion.com/logos/slack.svg?v=2" width="80" height="80" alt="Slack" title="Slack · co slack"></a>
<a href="docs/cli/feishu.md"><img src="https://www.connectonion.com/logos/feishu.svg?v=2" width="80" height="80" alt="Feishu / Lark" title="Feishu / Lark · co feishu, co lark"></a>
<a href="docs/cli/sms.md"><img src="https://www.connectonion.com/logos/sms.svg?v=2" width="80" height="80" alt="SMS" title="SMS · co sms"></a></p>

<p><b>Browser &amp; files</b><br>
<a href="docs/cli/browser.md"><img src="https://www.connectonion.com/logos/chrome.svg?v=2" width="80" height="80" alt="Your Chrome" title="Your Chrome · co browser"></a>
<a href="docs/cli/browser.md"><img src="https://www.connectonion.com/logos/remote.svg?v=2" width="80" height="80" alt="Remote browser" title="Remote browser · co remote-browser"></a>
<a href="docs/cli/gdrive.md"><img src="https://www.connectonion.com/logos/gdrive.svg?v=2" width="80" height="80" alt="Google Drive" title="Google Drive · co gdrive"></a>
<a href="docs/cli/youtube.md"><img src="https://www.connectonion.com/logos/youtube.svg?v=2" width="80" height="80" alt="YouTube" title="YouTube · co youtube"></a>
<a href="docs/cli/synology.md"><img src="https://www.connectonion.com/logos/syno.svg?v=2" width="80" height="80" alt="Synology NAS" title="Synology NAS · co syno"></a>
<a href="docs/cli/search.md"><img src="https://www.connectonion.com/logos/search.svg?v=2" width="80" height="80" alt="Web search" title="Web search · co search"></a>
<a href="docs/cli/search.md"><img src="https://www.connectonion.com/logos/fetch.svg?v=2" width="80" height="80" alt="Web fetch" title="Web fetch · co fetch"></a></p>

<p><b>Issues &amp; feedback</b><br>
<a href="docs/cli/linear.md"><img src="https://www.connectonion.com/logos/linear.svg?v=2" width="80" height="80" alt="Linear" title="Linear · co linear"></a>
<a href="docs/cli/canny.md"><img src="https://www.connectonion.com/logos/canny.svg?v=2" width="80" height="80" alt="Canny" title="Canny · co canny"></a></p>

<p><b>Coding agents</b><br>
<a href="docs/cli/ai.md"><img src="https://www.connectonion.com/logos/ai.svg?v=2" width="80" height="80" alt="co ai" title="co ai · co ai"></a>
<a href="docs/claude-code-plugin.md"><img src="https://www.connectonion.com/logos/claude.svg?v=2" width="80" height="80" alt="Claude Code" title="Claude Code · co claude"></a>
<a href="docs/cli/skills.md"><img src="https://www.connectonion.com/logos/codex.svg?v=2" width="80" height="80" alt="Codex" title="Codex · co skills link"></a>
<a href="docs/cli/skills.md"><img src="https://www.connectonion.com/logos/skills.svg?v=2" width="80" height="80" alt="Your skills" title="Your skills · co skills"></a>
<a href="docs/cli/sub.md"><img src="https://www.connectonion.com/logos/sub.svg?v=2" width="80" height="80" alt="Shared skills" title="Shared skills · co sub"></a>
<a href="docs/cli/README.md"><img src="https://www.connectonion.com/logos/eval.svg?v=2" width="80" height="80" alt="Evals" title="Evals · co eval"></a>
<a href="docs/cli/audit.md"><img src="https://www.connectonion.com/logos/audit.svg?v=2" width="80" height="80" alt="CLI audit" title="CLI audit · co audit"></a>
<a href="docs/cli/skills.md"><img src="https://www.connectonion.com/logos/cursor.svg?v=2" width="80" height="80" alt="Cursor" title="Cursor · co skills discover"></a>
<a href="docs/cli/skills.md"><img src="https://www.connectonion.com/logos/kiro.svg?v=2" width="80" height="80" alt="Kiro" title="Kiro · co skills discover"></a></p>

<p><b>Models</b><br>
<a href="docs/concepts/models.md"><img src="https://www.connectonion.com/logos/managed.svg?v=2" width="80" height="80" alt="Managed keys" title="Managed keys · co/… ($5 credit)"></a>
<a href="docs/concepts/models.md"><img src="https://www.connectonion.com/logos/openai.svg?v=2" width="80" height="80" alt="OpenAI" title="OpenAI · gpt-…"></a>
<a href="docs/concepts/models.md"><img src="https://www.connectonion.com/logos/anthropic.svg?v=2" width="80" height="80" alt="Anthropic" title="Anthropic · claude-…"></a>
<a href="docs/concepts/models.md"><img src="https://www.connectonion.com/logos/gemini.svg?v=2" width="80" height="80" alt="Gemini" title="Gemini · gemini-…"></a>
<a href="docs/concepts/models.md"><img src="https://www.connectonion.com/logos/mistral.svg?v=2" width="80" height="80" alt="Mistral" title="Mistral · mistral/…"></a>
<a href="docs/concepts/models.md"><img src="https://www.connectonion.com/logos/groq.svg?v=2" width="80" height="80" alt="Groq" title="Groq · groq/…"></a>
<a href="docs/concepts/models.md"><img src="https://www.connectonion.com/logos/grok.svg?v=2" width="80" height="80" alt="Grok" title="Grok · grok/…"></a>
<a href="docs/concepts/models.md"><img src="https://www.connectonion.com/logos/openrouter.svg?v=2" width="80" height="80" alt="OpenRouter" title="OpenRouter · openrouter/…"></a>
<a href="docs/concepts/local-models.md"><img src="https://www.connectonion.com/logos/ollama.svg?v=2" width="80" height="80" alt="Ollama (local)" title="Ollama (local) · ollama/…"></a></p>

<p><b>Agents &amp; servers</b><br>
<a href="docs/cli/call.md"><img src="https://www.connectonion.com/logos/call.svg?v=2" width="80" height="80" alt="Remote agents" title="Remote agents · co call"></a>
<a href="docs/features/trust.md"><img src="https://www.connectonion.com/logos/trust.svg?v=2" width="80" height="80" alt="Trust" title="Trust · co trust"></a>
<a href="docs/cli/proxy.md"><img src="https://www.connectonion.com/logos/proxy.svg?v=2" width="80" height="80" alt="Your internet" title="Your internet · co proxy"></a>
<a href="docs/cli/server.md"><img src="https://www.connectonion.com/logos/server.svg?v=2" width="80" height="80" alt="Your servers" title="Your servers · co deploy --to"></a>
<a href="docs/cli/server.md"><img src="https://www.connectonion.com/logos/ssh.svg?v=2" width="80" height="80" alt="SSH" title="SSH · co server ssh"></a>
<a href="docs/cli/schedule.md"><img src="https://www.connectonion.com/logos/schedule.svg?v=2" width="80" height="80" alt="Schedules" title="Schedules · co schedule"></a></p>

<p><a href="docs/cli/README.md">Every command</a> · <code>co commands</code> lists them all.</p>
<!-- /connections -->

## CLI is all you need

An agent's work lives in many places: your inbox, your calendar, a chat
thread, a web page behind a login, a file on the NAS, an issue tracker, its own
notes, another agent. **ConnectOnion strings all of that context together with
one command line, `co`.** The agent reads a thread with one command, looks
something up with the next, and writes the answer with a third. Every step is
a line in its shell, and the output of one is the input of the next.

### Why a command line, and not MCP or a plugin per tool

- **Every agent already has one.** Claude Code, Codex, Cursor and any agent you
  write can run a shell command. There is no server to start, no client to
  configure and nothing to install into the agent.
- **It costs no context until it is used.** Tool schemas sit in an agent's
  prompt whether it needs them or not. A command line is discovered on demand:
  bare `co` lists the groups, `co gmail --help` explains one, and only the page
  the agent opens enters its context.
- **The help page is the prompt.** Each `--help` says what the command does,
  what it changes (Read-only, Sends, Changes, Deletes…) and gives a real
  example, so there is no separate skill file or schema to keep in step. CI
  fails any page that loses one of those parts ([`co audit`](docs/cli/audit.md)).
- **Every answer names the next step.** A list ends with how to open the first
  item, a missing login ends with `Next: co auth microsoft`, a typo ends with
  the command you meant. The agent recovers without asking you.
- **It composes.** Commands pipe into each other and into scripts, and the
  transcript is the same commands you would type, so you can read exactly what
  the agent did, and run it yourself.

```console
$ co                       # every command group
$ co linear --help         # what it does, what it changes, an example
$ co linear issues -n 3
3 open issues
CON-3  Todo  No priority  -  2026-10-01  Import your data
CON-1  Todo  No priority  -  2026-10-01  Get familiar with Linear
CON-4  Todo  No priority  -  2026-10-01  Set up your teams
Next: co linear issue CON-3
```

### MCP becomes a command too

MCP servers are useful; the protocol is not the problem, the interface is.
**`co mcp`** (coming next, [#2048](https://github.com/openonion/connectonion/issues/2048))
puts any MCP server behind the same command line: `co mcp tools <server>`
lists its tools, `co mcp help <server> <tool>` renders a tool as a help page,
and `co mcp call` runs it. The agent finds MCP tools the way it finds
everything else, through `--help`, and none of them sit in its prompt.

Credentials stay on your machine, in `~/.co/keys.env` or encrypted with
`co env set … --secret`. Writes that matter preview until `--yes`, and in
`co ai` a risky tool call waits for your approval.

## Install and start

```bash
pip install connectonion   # Python 3.10+
co init                    # your identity and ~/.co/keys.env
co auth microsoft          # or: co auth google
co outlook                 # or: co gmail
co commands                # everything else; add --help to any
```

The [Quick start guide](docs/quickstart.md) covers Google, the browser, chat
apps and project settings.

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

<picture>
  <source media="(prefers-reduced-motion: reduce) and (max-width: 600px)" srcset="https://www.connectonion.com/demos/linear-mobile-poster.png?v=2">
  <source media="(prefers-reduced-motion: reduce)" srcset="https://www.connectonion.com/demos/linear-poster.png?v=2">
  <source media="(max-width: 600px)" srcset="https://www.connectonion.com/demos/linear-mobile.gif?v=2">
  <img alt="co linear issues listing three open issues, then co linear create previewing a new issue" src="https://www.connectonion.com/demos/linear.gif?v=2">
</picture>

List your Linear issues, then create one. The create shows a preview and changes nothing until `--yes`.

<picture>
  <source media="(prefers-reduced-motion: reduce) and (max-width: 600px)" srcset="https://www.connectonion.com/demos/slack-mobile-poster.png?v=2">
  <source media="(prefers-reduced-motion: reduce)" srcset="https://www.connectonion.com/demos/slack-poster.png?v=2">
  <source media="(max-width: 600px)" srcset="https://www.connectonion.com/demos/slack-mobile.gif?v=2">
  <img alt="co slack search finding a message, then co slack thread reading its replies" src="https://www.connectonion.com/demos/slack.gif?v=2">
</picture>

Search Slack, then read the whole thread. Each message carries the id that `co slack send --reply-to` takes.

<picture>
  <source media="(prefers-reduced-motion: reduce) and (max-width: 600px)" srcset="https://www.connectonion.com/demos/canny-mobile-poster.png?v=2">
  <source media="(prefers-reduced-motion: reduce)" srcset="https://www.connectonion.com/demos/canny-poster.png?v=2">
  <source media="(max-width: 600px)" srcset="https://www.connectonion.com/demos/canny-mobile.gif?v=2">
  <img alt="co canny posts ranked by votes, then co canny status previewing a move to planned" src="https://www.connectonion.com/demos/canny.gif?v=2">
</picture>

Your most-voted Canny requests, and a status change you preview before voters hear about it.

<picture>
  <source media="(prefers-reduced-motion: reduce) and (max-width: 600px)" srcset="https://www.connectonion.com/demos/audit-mobile-poster.png?v=2">
  <source media="(prefers-reduced-motion: reduce)" srcset="https://www.connectonion.com/demos/audit-poster.png?v=2">
  <source media="(max-width: 600px)" srcset="https://www.connectonion.com/demos/audit-mobile.gif?v=2">
  <img alt="co audit co linear scoring 13 help pages and reporting fit for an agent harness" src="https://www.connectonion.com/demos/audit.gif?v=2">
</picture>

`co audit` scores a CLI's help pages the way an agent reads them. CI runs it on every `co` page, and it works on any other CLI too.

## Use it from Claude Code, Codex or Cursor

Nothing to install into them: ask your coding agent to "use `co` to check my
Outlook inbox" and it reads `co commands` and `co outlook --help` before it
acts. `co skills link` also links ConnectOnion's skills into Claude Code and
Codex ([`co skills`](docs/cli/skills.md)).

ConnectOnion is also a Python framework for building your own agents on the
same harness; see the [documentation](https://docs.connectonion.com).

## Project

**Stable 1.8.10** is what `pip install connectonion` installs; 1.9.0 previews
carry new features first ([release channels](docs/releases.md),
[release notes](https://github.com/openonion/connectonion/releases)).
Questions go to [Discussions](https://github.com/openonion/connectonion/discussions)
or the Discord linked above, bugs to [Issues](https://github.com/openonion/connectonion/issues).
[Contributing](CONTRIBUTING.md) · [Code of Conduct](CODE_OF_CONDUCT.md) ·
[Security](SECURITY.md) (report vulnerabilities privately) ·
[Apache-2.0](LICENSE).

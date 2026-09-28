# Quick Start

Use `co` to inspect your agent's environment, connect the services it needs,
and run them from your terminal or coding agent. No Python project or editor is
required for these commands.

## Install and see the environment

```bash
pip install connectonion
co init                     # global identity and ~/.co/keys.env
co env                      # selected settings and their sources, values hidden
co status                   # identity, account and connected services
```

`co init` defaults to global configuration; it does not create files in the
current directory. For an existing project, explicitly run `co init ./`.
Even inside a project, CLI commands use the global `~/.co/keys.env` unless you
select another file with `--env-file` **before** the command:

```bash
co init ./
co --env-file ./.env env
co --env-file ./.env outlook
```

The selected file replaces the global file rather than inheriting missing
values from it. `co env` hides every value by default; avoid `show --reveal`
and `get` in shared terminals or logs. Use `co env set KEY VALUE` to save a
setting in the selected file. OAuth account records are managed with
`co auth`, not by editing their token fields. See [Environment selection](cli/environment.md)
and [`co env`](cli/env.md).

## Connect Outlook and use it

```bash
co auth microsoft           # one-time consent; credentials stay in the selected file
co outlook                  # recent inbox, numbered with a listing ID
co outlook read 1 --listing <listing-id>
co outlook calendar today
```

Use the listing ID printed by your own inbox; a row number alone is not a
stable message identifier. Reading does not mark mail read unless you pass
`--mark-read`. Sending or replying is a separate, explicit command. To use a
project-specific Microsoft account, run both authorization and Outlook with
the same selector:

```bash
co --env-file ./.env auth microsoft
co --env-file ./.env outlook
```

See [`co outlook`](cli/outlook.md) for contacts, calendar and sends.

## Reach the rest of your environment

| What your agent needs | Connect or inspect | Use it |
| --- | --- | --- |
| Its own mailbox | `co init`, then `co status` | `co email inbox` |
| Gmail, Calendar and Drive | `co auth google` | `co gmail`, `co gcalendar today`, `co gdrive list` |
| A logged-in browser | Log in interactively once | `co browser go_to https://example.com` |
| Chat apps | Follow the service's setup guide | `co whatsapp listen`, `co telegram --help` |
| Skills | `co skills list` | `co skills link`, `co sub --help` |

Each command has its own help: `co <command> --help`. Run `co commands` for
the current complete list, or `co doctor` if something is not working. The
[CLI reference](cli/) links every integration.

Claude Code, Codex and other coding agents can run these same shell commands.
You can tell one, “Use `co` to check my Outlook inbox,” and it can inspect
`co commands` and `co outlook --help` before acting. `co skills link` is an
optional shortcut, not a prerequisite.

## An example across environments

Once the relevant accounts and permissions are configured, you can ask your
coding agent to: “Read the context from my Telegram bot, check the official
documentation, ask a teammate's agent to run an allowed check, then email me a
summary.” The commands behind that request are visible:

1. `co telegram receive` gets a message delivered to **your configured bot**.
   This receive flow is experimental; it cannot read arbitrary private chats.
2. `co search` finds sources and `co fetch` reads a public page. Search is
   available in the **1.8.9 preview**, not the current stable release.
3. `co call` asks a reachable remote agent to run a command on its allowlist.
   Calling someone else's Codex requires that agent to have Codex installed,
   authenticated and allowed to use it through `co ai`.
4. `co email send` sends the final result to an explicit recipient, after you
   authorize that external action.

The [search GIF](https://www.connectonion.com/aha-search.gif) shows a verified,
read-only search and fetch of the ConnectOnion GitHub repository. The four-step
scenario is illustrative; the GIF does not show Telegram, a remote agent or an
email being used.

## Build an agent of your own (optional)

The CLI above works without a project. If you want to build and host your own
Python agent, start with `co create my-agent` and continue with the
[Python Agent guide](concepts/agent.md) and [Tools guide](concepts/tools.md).

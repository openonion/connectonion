# CLI Call

Run one command on a **remote** agent from the shell, print the result. No LLM, no session — like a remote command line.

## Quick Start (60 seconds)

```bash
co call 0x3d40... co status                              # run `co status` on the remote box
co call 0x3d40... co browser go_to https://example.com   # drive its browser
co call --out shot.png 0x3d40... co browser take_screenshot   # save its screenshot
co call 0x3d40... uptime                                 # any whitelisted command
```

`co call` is the **remote twin of `co browser`**: what `co browser take_screenshot`
does on *this* machine, `co call <address> co browser take_screenshot` does on a
*remote* agent — same verbs, one extra `<address>` up front.

## How it works

```
co call <address> <command...>
        │           │
        │           └── runs on the REMOTE agent, verbatim
        └────────────── the agent's 0x address (or an announced alias)
```

The command is sent over the same authenticated WebSocket the Python `connect()`
client uses (direct or via relay), executed on the remote through its
direct-exec path, and the raw output comes straight back. Under the hood this is
`connect(address).call("bash", command="<command...>")`.

## Gated by the remote's whitelist

The remote decides what may run: every `co call` is checked against **that
agent's `.co/host.yaml` `permissions`** whitelist — the same list its own LLM
uses to auto-run a command without asking. `co ...` commands (including
`co browser <verb>`) are whitelisted by default; read-only shell commands too.
Anything not on the list comes back as an error:

```bash
$ co call 0x3d40... rm -rf /
blocked: command not in the permission whitelist. Allow it by adding a rule to .co/host.yaml permissions.
$ echo $?
1
```

To expose more, edit the whitelist **on the remote** (`.co/host.yaml`), e.g. add
`"Bash(git status)"`. See [network/remote-call.md](../network/remote-call.md).

## Driving a remote browser

Browser control goes through `co browser`, which on the remote talks to its
persistent browser **daemon** (a separate process that manages tabs and
lifecycle itself):

```bash
co call 0x3d40... co browser go_to https://news.ycombinator.com
co call 0x3d40... co browser click "text=login"
co call --out home.png 0x3d40... co browser take_screenshot
```

A screenshot returns as base64; `co call` detects an image result and saves it —
to `--out PATH` if given, else `./screenshot.png` — then prints the path.

## Options

Options go **before** the address; everything after the address is the remote
command, verbatim (so it keeps its own flags — `co call 0x.. ls -la` works).

- `--out PATH` — save an image result (screenshot) to `PATH` instead of `./screenshot.png`
- `--timeout SEC` — seconds to wait for the result (default `60`)
- `--relay URL` — relay server (default `wss://oo.openonion.ai`)

## Scripting

Clean stdout, standard exit codes — safe to pipe and branch on:

```bash
status=$(co call 0x3d40... co status)
co call 0x3d40... co browser get_links_from_page | grep github
co call --out /tmp/s.png 0x3d40... co browser take_screenshot && open /tmp/s.png
```

Exit codes: `0` ok · `1` failure (tool error / not whitelisted / connection) · `2` usage.

## Identity

`co call` signs the request with your local identity (`.co` in the project, else
`~/.co`), which the remote needs if it runs at a strict trust level. For open /
careful agents no keys are required — it works out of the box.

## When to use

- **`co call`** — you know the exact command and want the result now (scripting,
  an agent driving another agent, remote-control steps).
- **Python `connect().input(prompt)`** — hand the remote agent an open-ended
  task and let its LLM decide the steps. See [network/connect.md](../network/connect.md).

## See Also

- [network/remote-call.md](../network/remote-call.md) — `remote.call` / EXEC internals and the whitelist
- [browser.md](browser.md) — `co browser` (the local browser this mirrors)
- [network/connect.md](../network/connect.md) — `connect()` and `input()` for LLM-driven tasks

# co host

`co init` already started your Host. `co host` shows it and manages it.

```bash
co host                     # status: running?, model, port, how to stop it
co host --stop              # stop it (and keep it stopped across login)
co host --background        # start it again
co host --serve             # run it in this terminal instead
co host --agent agent.py    # run your own agent.py as the Host
```

## Nothing to write: host.yaml and skills

An agent is a folder: `.co/host.yaml` and `.co/skills/`. There is no code to
write. Which model answers is one line in `host.yaml`:

```yaml
model: codex                  # native Codex, the account you are logged into
model: claude-code            # native Claude Code, the account you are logged into
model: co/gemini-4-hydrogen   # the built-in agent on that model (the default)
```

`co init` fills it with what works on the machine: a logged-in Codex, then
Claude Code, otherwise the managed default with its free credit. To change it,
edit the line and run `co host --background`. The frontend does not change.

## Where it runs

`co init` installs one user service: launchd on macOS, a systemd user unit on
Linux (run `loginctl enable-linger` to keep it running while you are logged
out). It restarts if it stops and comes back after login. The Host it serves
lives in `~/.co/runtime/mac-host` on macOS and `~/.co/runtime/host` on Linux.
`co init --no-host` skips it. A Linux login with no systemd user session (a
container, CI, or SSH without linger) has no background service: `co init`
says the Host was skipped and finishes normally. There, and on other systems,
run `co host --serve`.

In a project folder that has its own `.co/host.yaml`, `co host` and its options
act on that project instead. Your own `agent.py` is the special case: it needs
`--agent`. A service installed before 1.9.6 that runs a bare `co host` in a
project with `agent.py` keeps serving it.

`--agent` runs the file with the Python that co itself runs on. That is the
whole difference from `python agent.py`, and it matters on a machine where co
came from the one-line installer: co then lives in its own environment, and the
system `python` cannot import `connectonion` (#2438).

One host serves everything, from one process and one port:

- **the agent**, over HTTP, WebSocket and the relay, to whoever `trust` admits;
- **REM**, your `~/.co/rem`, to you only (`rem: false` in `.co/host.yaml` turns it off);
- **channels**, the chats in `.co/host.yaml`'s `listen:`;
- **the schedule**, the jobs in `.co/schedule.yaml`.

`co host --serve`, `python agent.py`, `co deploy` and `co ai` go through the same
`host()`, so they serve the same things. See [host()](../network/host.md#what-one-host-serves)
and [host.yaml](../network/host-config.md).

## "Discover" in co

The word names five different things:

| What | Command or place | Docs |
|---|---|---|
| Finding a hosted agent by its address | the relay ANNOUNCE every host sends; `connect("0x…")` | [host.md](../network/host.md), [announce message](../network/protocol/announce-message.md) |
| Your public profile in the directory | `co announce` | [sub.md](sub.md), [setup.md](setup.md) |
| Skills on this machine | `co skills discover` | [skills.md](skills.md) |
| How to reach a host directly | `transports` in `GET /info` | [host.md](../network/host.md#get-info) |
| Every co command | `co commands` | `co commands --help` |

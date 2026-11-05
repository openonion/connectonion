# co host

Serve the agent in this directory.

```bash
co create my-agent && cd my-agent
co host                 # until you stop it
co host --port 8001     # another port for this run
```

`co host` runs `./agent.py` with the Python that co itself runs on. That is the
whole difference from `python agent.py`, and it matters on a machine where co
came from the one-line installer: co then lives in its own environment, and the
system `python` cannot import `connectonion` (#2438).

One host serves everything, from one process and one port:

- **the agent**, over HTTP, WebSocket and the relay, to whoever `trust` admits;
- **REM**, your `~/.co/rem`, to you only (`rem: false` in `.co/host.yaml` turns it off);
- **channels**, the chats in `.co/host.yaml`'s `listen:`;
- **the schedule**, the jobs in `.co/schedule.yaml`.

`python agent.py`, `co deploy` and `co ai` go through the same `host()`, so they
serve the same things.

## One Host per address on this computer

Every project made by `co create`, `co ai`, the background service from
`co init --background` and the `co ai` that `co rem open` starts all use the
key in `~/.co`, so they share one address. Only one of them serves it at a
time. A second one exits at once and names the first:

```text
[host] 0x3ae5aab6… is already served on this computer by 'a' in /Users/you/a (pid 72209, http://localhost:8731). One address, one Host: the relay would pick between them at random.
       Use that one, or stop it first: co host --stop
```

From any folder:

```bash
co host --status   # {"serving": {"pid", "port", "name", "project", "service"}} or {"serving": null}
co host --stop     # stops it; a background service is stopped as a launchd job
co status          # "Host on this computer"
```

`co rem open` reads through that Host instead of starting another. A project
with its own key in `.co/keys/` has its own address and its own Host. See [host()](../network/host.md#what-one-host-serves)
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

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
serve the same things. See [host()](../network/host.md#what-one-host-serves)
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

---
description: co init used to set a machine up and then leave you to start the Host yourself, with a flag that only Macs had and a model chosen by whichever way you started it. Now co init leaves it running, and the model is one line in host.yaml.
tags: [Host, Init, Setup]
---

# One command, and it is running

The owner asked a simple question about the Host: what is `co host` for? The
honest answer took four layers to explain. `co init` set up the identity, the
free credit, the skills and the first REM notebook, and then stopped. To get a
Host that kept running you needed `co init --background`, which existed only on
macOS and always served native Codex. In a project, `co host` ran an `agent.py`
that `co create` had generated, and the model was a default argument inside it.
Three ways to start the same server, each choosing the model differently, and
none of them visible in a config file.

That is too much machinery for "set it up and leave it on".

## What changed

`co init` now ends with the Host running. It installs one user service, launchd
on macOS or a systemd user unit on Linux, that serves the agent, REM, the
schedule and the chat channels. It survives closing the terminal and comes back
after login. `co init --no-host` skips it; `--background` still works and now
means what it always should have.

A bare `co host` no longer starts anything. It tells you whether the Host is
running, which model answers, which port it uses, and how to stop it.
`co host --serve` runs it in the terminal instead, and your own `agent.py` is
the special case that needs `co host --agent agent.py`.

The model is one line in `.co/host.yaml`:

```yaml
model: codex           # or claude-code, or co/gemini-4-hydrogen
```

`codex` and `claude-code` hand every turn to the native CLI you are already
logged into, with no outer model; any other value is the built-in agent on
that model. `co init` picks what works on the machine: a logged-in Codex, then
Claude Code, otherwise the managed default with its free credit. Claude Code as
the Host's agent is new here; Codex already had it.

## What we kept

A Mac upgraded from an earlier preview keeps its one service and its native
Codex: the profile gets `model: codex` written in, and the old `--native-codex`
spelling still works. A service that runs a bare `co host` in a project with an
`agent.py`, with no terminal attached, keeps serving that file. Tests never
install a real service: a policy in `tests/conftest.py` makes sure of it, the
same way they never start a real tmux server.

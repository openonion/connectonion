---
title: "Global unless you name a project"
date: "2026-09-02"
description: "Credential setup should not turn the current directory into a project."
---

Setting up ConnectOnion credentials should not turn whichever directory happens
to be open into an agent project. Plain `co init` now sets up `~/.co/keys.env`
and the machine identity. Project initialization requires `co init ./` or
another explicit directory.

The previous command combined two operations: global authentication and project
scaffolding. That made sense when every installation started with a new agent,
but the CLI also works without a project—for email, browsers, and remote agents.
Running setup in an unrelated checkout should leave that checkout alone.

## An argument chooses the destination

An alternative was to infer scope from the current directory or from a template
flag. That would leave identical commands writing different files depending on
where they ran. We chose an explicit path instead:

```bash
co init                          # global credentials
co init ./                       # project configuration here
co init ./ --template co-ai       # project configuration plus template
```

The migration cost is deliberate: scripts that scaffold a project must add
`./`. Template, description, and overwrite options without a path fail with a
concrete example before writing anything. `co create` remains the way to make a
new project directory.

## Global storage is not an environment snapshot

By the time the CLI runs, package startup may have loaded a project's `.env`
into the process. Copying detected keys into global configuration would silently
promote a project credential to a machine-wide default. Global init therefore
persists a provider key only when explicitly supplied with `--key`; it preserves
other global keys and writes managed credentials through the existing global
authentication path.

Project initialization keeps its existing global-identity and credential
inheritance rules. It does not create an independent project keypair. Runtime
precedence is unchanged: explicit process variables, then project `.env`, then
global `keys.env`.

The regression checks exercise no-path setup inside and outside projects,
relative and absolute project paths, spaces in paths, offline setup, explicit
provider keys, and rejection before writes. The installed-wheel acceptance test
also checks that the actual `co init` executable leaves the working directory
empty while creating global state.

# DD-051: Isolate local ACP state with an explicit CLI root

**Status:** Accepted

**Date:** 2026-08-13

**Related:** [DD-011 Global Config and Identity](011-global-config-identity-management.md), [DD-029 Persistent ACP Session Ownership](029-acp-persistent-session-ownership.md), [Issue #945](https://github.com/openonion/connectonion/issues/945)

## Context

Local `co ai --acp` stores durable session snapshots and every Agent's logs and
eval records under `~/.co`. That default is useful for one operator, but it is
not a safe acceptance-test boundary when another Agent may be active on the
same machine. Concurrent runs can contend for a session lease or write mutable
evidence into the operator's ordinary state directory.

The final acceptance test must run the real `co ai` command. A unit-test-only
monkeypatch would prove a different entry point, while changing `HOME` would
also redirect unrelated configuration and credential discovery.

## Decision

Add an explicit ACP-only option:

```bash
co ai --acp --state-dir PATH
```

The CLI prepares `PATH` as a private state root and passes the same resolved
directory to both owners of mutable state:

- the ACP lifecycle adapter, for leases and durable snapshots;
- the Agent factory, for Logger and eval output.

The normal default remains `~/.co`. Using `--state-dir` without `--acp` is an
exit-2 usage error. Web-server and network Host storage are unchanged because
they also carry identity, relay, and authenticated-principal semantics that
need a separate decision.

## Keep configuration separate from state

`Agent.co_dir` is configuration as well as a filesystem path: the coding Agent
uses it for its name and skill discovery. Redirecting that value would silently
rename the Agent and make its configured skills disappear.

The Agent therefore accepts a separate Logger state directory. An isolated ACP
Agent keeps its normal global `co_dir` for name and configuration while Logger
and eval output use `PATH`. Provider credentials keep their existing
environment and global-config lookup; no key, token, skill, or identity file is
copied into the state directory.

## Security boundary

The selected root reuses the durable-session store's existing validation:

- create controlled directories with private permissions;
- enforce mode `0700` on POSIX;
- reject a symlink as the selected root;
- fail before opening the ACP protocol when the directory is unavailable.

The flag isolates ConnectOnion's mutable process state. It does not sandbox the
workspace, provider CLIs, environment, or effects authorized by an ACP session
mode.

## Alternatives considered

- **Override `HOME`:** rejected because it changes unrelated tools, shell
  conventions, identity, and credential lookup.
- **Copy `~/.co`:** rejected because it duplicates private credentials and
  creates a second identity copy.
- **Monkeypatch `GLOBAL_CO_DIR`:** retained for narrow unit tests, but rejected
  as final acceptance evidence because it does not run the public CLI contract.
- **Add an environment variable:** rejected for this slice because invisible
  process state is harder to audit than an explicit launch argument.
- **Change every mode at once:** rejected because web and network modes have
  additional storage ownership and authentication boundaries.

## Consequences

Real Claude Code and Codex ACP acceptance can run beside other local Agents
without sharing session, log, or eval files. Callers must deliberately manage
and remove their test directory. Existing users see no behavior change unless
they provide the new flag.

Revisit the ACP-only boundary when web Host mode gains a separately designed
runtime-state root that preserves its global identity and per-principal network
storage guarantees.

# A Host that survives closing the terminal

Candidate implementation for #2684; not yet released. The first slice adds a
macOS user service to an existing project with an `agent.py`:

```bash
co host --background
co host --status
co host --stop
co host --background
co host --uninstall
```

Foreground `co host` keeps its existing behavior. `--background` uses the same
co Python environment and project, installs one launchd GUI-user service and
starts it. It restarts after process exit and loads after user login. A Mac
that is asleep, offline or logged out is not an always-available server.

The plist contains executable/configuration paths, not tokens. Existing co
configuration is loaded at process startup. Logs are local owner-only files
under `~/.co/host-services/`. An edited service definition is preserved rather
than overwritten. Use the same project directory to inspect or stop its service.

Status distinguishes a configured plist from a currently observed process.
Native startup additionally requires that process to own the responding local
Host listener. Readiness discovers the actual port, including a project
`AGENT_PORT` override; it does not equate a shared identity with this process.
It does not establish device pairing, Codex readiness or successful REM work.
Stop disables the service across login; start enables it. Uninstall removes only
the service definition, preserving project code, identity, memory and logs.
Only one service action can be selected per invocation. `--port` applies only
when starting the background service. Other platforms can use foreground hosting.

## Standard Mac preparation

```bash
co init --background
```

The candidate initializes a dedicated profile at `~/.co/runtime/mac-host` through
the standard project initializer, prepares REM directories/configuration without
mapping or investigating sources, then starts a native Codex Host user service.
New profiles are strict-trust, unlisted and have no chat-channel listeners.
Existing user configuration is kept. New REM configuration selects Codex; it
does not silently fall back to a different runner.
New profiles use port 8000 if free, otherwise an operating-system-assigned port;
an existing Host is not stopped. The actual saved profile port is reused later.

`co host --native-codex` runs that native profile in the foreground. It reuses the
existing Codex plugin and Host session/permission boundaries, with no outer
ConnectOnion model call. Session continuation comes from owned Host storage;
remote text cannot choose a native thread ID, cwd or model. File/image inputs
are not yet accepted by this native profile; audio is transcribed separately.

`AGENT_CONFIG_PATH`, selected env-file and nonsecret Codex paths survive service
restart. Native `CODEX_CMD` must name one executable rather than a command with arguments
or credentials; configure provider options in its own configuration. A saved
baseline allows normal interpreter upgrades and reruns without repeating port
options, while preserving actual plist edits.

Provider executable validation happens only when starting a native profile.
Status, stop and uninstall remain usable with invalid Codex settings. Generic
`agent.py` services load their provider settings through the normal selected
configuration; shell-only Codex overrides are not copied into their plist.

The result reports service/process, REM preparation, Codex login preflight and
missing Watch connector separately. Login preflight does not prove remaining
quota or a completed model call. No mailbox/body scan, microphone, ASR upload
or REM investigation starts during setup. The real Watch connector, matching
native bridge and final published setup URL remain required before claiming
complete device onboarding. Do not use a fake QR in their place.

Scoped test observations and remaining gates are recorded in
[candidate acceptance](../acceptance/device-bootstrap/2026-10-26.md).

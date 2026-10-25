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
It does not establish device pairing, Codex readiness or successful REM work.
Stop disables the service across login; start enables it. Uninstall removes only
the service definition, preserving project code, identity, memory and logs.
Only one service action can be selected per invocation. `--port` applies only
when starting the background service. Other platforms can use foreground hosting.

The standard initialization mode, native Codex Host adapter, source-scoped REM
setup and versioned device setup URL remain subsequent slices in this PR. Do
not substitute `co ai --harness codex` without a prompt as a persistent Host:
the existing command is explicitly one-shot. Do not run the broad `co rem init`
source scan merely to create empty local storage.

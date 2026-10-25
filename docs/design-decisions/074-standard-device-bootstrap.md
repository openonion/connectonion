# Standard device bootstrap and persistent Mac Host

Status: implementation in progress, not released. Tracks #2684.

The user gives Mac Codex one official setup URL. Initialization reuses identity,
configures the installed agent integration, prepares a local Host and REM, and
verifies real status. Closing the terminal must not disconnect the Mac.

## Implementation sequence and boundaries

1. Add a macOS user-service lifecycle to the existing `co host` command: install
   and start, inspect status, stop, uninstall. Preserve foreground project hosts
   and user files. Do not require root or embed credentials in launchd plists.
2. Integrate this lifecycle with a standard explicit global initialization mode,
   using a managed runtime project and repairing only known-owned files. REM
   setup prepares storage/configuration, not mailbox archives/investigation.
3. Add a native Codex Host execution boundary and typed device requests. Current
   `co ai --harness codex` is one-shot only; pretending it already hosts would
   leave a process that exits. Do not route an owner-requested Codex-only workflow
   through an unmentioned managed LLM just to delegate.
4. Publish the versioned setup URL only with a tested release. A real Watch
   connector plus matching native bridge is required for device-ready. A running
   process, saved launchd plist, QR display and paired authorization are separate
   facts. Stop honestly when an installed release lacks the connector.

macOS is first. A service uses launchd's GUI user domain, a per-project label,
RunAtLoad and restart policy. Existing identity, memory and recordings survive
stop/uninstall. Other platforms retain foreground hosting until supported.
This is not an unauthenticated remote shell, automatic microphone access or
permission to send saved content to cloud AI.

## Required acceptance

Fresh setup and rerun; no duplicate service; preserve edited config; actual
process liveness after start and terminal exit; crash/login recovery; explicit
stop/restart/uninstall; port conflict and invalid agent errors; Codex absent or
signed out; no model/mail/network on readiness checks; authenticated typed
request and result; missing Watch dependency reported rather than fake success.
Use temporary projects and synthetic payloads. Do not replace user global co
or register a production service until its reviewed runtime is available.

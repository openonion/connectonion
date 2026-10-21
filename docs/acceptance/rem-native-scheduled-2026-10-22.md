# Native Scheduled integration probe — 2026-10-22

## What was checked

Official Scheduled documentation was read. It describes creating and managing
local tasks in the desktop application, with the computer and application running.
This is distinct from Codex CLI and its App Server protocol.

- Installed CLI: 0.163.0. Generated its App Server JSON schema with experimental
  methods included. Enumerated all 172 `ClientRequest` method enum values;
  none manages schedule, automation or cron.
- `co mcp ls` exposed 566 connector tools, and `co mcp tools codex_apps` had no
  local Scheduled creation/update tool. Hosted Page, Site and security-scanning
  schedules were not substituted for local REM scheduling.
- `co mcp tools codex_app --json` returned an empty list. The desktop-only
  `automation_update` capability was not callable from this session.
- The installed desktop application process was running. The session has no
  enabled native desktop UI automation surface, so the Scheduled form itself
  could not be operated or inspected.

## Legacy-definition smoke test

Created one temporary, private `automation.toml` under a unique
`rem-native-smoke-*` ID in the local Codex automations directory. It was first
PAUSED. A read-only query for that exact ID found no native registration.

Changed only this temporary definition to ACTIVE with an absolute UTC DTSTART
and `RRULE:FREQ=MINUTELY;INTERVAL=1;COUNT=1`. The only requested action was to run
a tiny script writing `fired.txt` in a fresh temporary directory. The prompt
explicitly excluded connected services and unrelated files. The file round-trip
parsed as valid TOML. This is an experimental legacy-file probe, not a supported
native creation API or proof of native registration.

Native registration, native run records and the isolated marker were observed
separately. No existing automation definition, REM config or launchd job was
modified. Final timing, outcome and cleanup are recorded below.

## Interpretation boundary

No public App Server method or callable local native tool was available here.
A failure of this legacy-file probe cannot establish that Scheduled itself is
broken, unavailable to the account, or unable to run REM when created through
the proper desktop UI. Without verified registration and execution, switching
REM's default or disabling its working trigger would be unsupported.

Official source: https://learn.chatgpt.com/docs/automations?surface=app

## Final result

```json
{
  "seconds_since_activation": 190,
  "target_utc": "2026-10-21T15:41:38.926637+00:00",
  "native_registration": [],
  "native_runs": [],
  "marker_exists": false,
  "cleanup": {
    "definition_removed": true,
    "temporary_workspace_removed": true,
    "existing_schedules_modified": false
  }
}
```

The one-shot was scheduled 90 seconds after activation. No registration, native
run or marker was observed through this bounded window. The temporary definition
and workspace were removed. No live REM schedule was replaced.

**Native integration is not verified.** The legacy-file route did not demonstrate
registration or execution on this running installation. A supported desktop
creation entry point or an exposed native Scheduled tool is still needed to
validate actual REM execution and result placement. Native desktop UI, restart,
sleep/wake and remote project behavior remain uninspected.

## Independent review

An independent AI reviewer, in a technology-founder/marketing/UI role, reviewed
the complete trial record. It found no blocker in the report's interpretation:
missing callable methods and the failed legacy-file probe are kept distinct
from native Scheduled availability. It confirmed that cleanup, unchanged REM
trigger, required next evidence and uninspected native UI are stated. This was
a report review, not a human review or a rendered native-desktop inspection.

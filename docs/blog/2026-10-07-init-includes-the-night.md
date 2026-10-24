# Init includes the night

The public a42 init already installs nightly upkeep after its first run when
the user approves the source and schedule summary. A real installed-wheel run
confirmed that its root-specific launchd job was installed. We stopped that
temporary job after the test. The estimate-only and --no-start paths leave it
off, and the CLI regression confirms init does not repeat the foreground sync.

The overview still described init as building a map and writing only your own
page. That was an old first-run workflow. The active overview and --help now
say init investigates the mapped pages and offers nightly upkeep, with --yes
for the displayed noninteractive approval and --no-start for leaving it off.
Start remains useful for enabling upkeep later.

This wording is deliberately about the offer, not guaranteed installation:
without approval, the schedule stays off. Model authentication failure can
still prevent memory writing even after metadata mapping succeeds. That
separate first-run failure remains tracked in #2302.


## Follow-up: a running server was not a ready timer

The 24 October control changed the diagnosis. The existing App Server accepted
requests and the task was ACTIVE, yet its native clock did not advance. Opening
`codex://automations` in the same normal app was followed by a real run, a marker,
automatic archiving and an independently confirmed pause. The overdue REM task
also began. Desktop code places the scheduler behind a capability published by
the primary renderer; a live server process does not establish that readiness.

The initialization candidate now opens that Scheduled entry point even when
Codex is already running. A cold-launch control then showed that an early URL could still be too soon.
The candidate now confirms native adoption before delivering Scheduled again,
while the previous clock is still preserved. That retry executed after a normal
app restart without a manual UI action; the real production pass also completed
with successful command exits and an archived wrapper. This removes a manual
setup step while keeping one timer. The controls used local-file registration;
account-managed creation and exact requested-minute execution still need
separate evidence. This follow-up is under review, not a new published preview.

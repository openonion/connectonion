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

# The reader that stayed on yesterday’s release

On a Mac running the REM preview, the command line reported rc33 while the open reader still showed rc29. SQLite’s integrity check passed, and reopening the reader brought back the same page. The upgrade status supplied the other clue. It showed nightly upgrades enabled, but there was no launchd job to run them.

The index turned out to be healthy for the release that wrote it. Its schema was version 2, and the installed reader expected version 3. A rebuild under the notebook’s maintenance lock took about 64 seconds. When it finished, the reader built a fresh page and the open tab caught up on its original URL.

We considered rebuilding the index whenever the reader opened. The minute-long repair made the cost of that approach concrete, especially with a healthy index. The builder now checks compatibility first and rechecks under the maintenance lock before rebuilding. If preparation fails, the saved page is still available. The nightly updater waits for preparation before asking the owned Host to switch. An unfinished turn or pending approval keeps the old Host alive until it can switch safely.

The first regular open of an eligible installed reader also reconciles the missing daily job. The job uses the configured stable or preview channel on PyPI, and an explicit opt-out stays in force. The two symptoms on that Mac exposed two checkpoints worth reporting separately: whether the nightly job can run and whether the release it installed can serve the notebook.

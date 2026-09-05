# The Browser That Status Could Not See

The Linux acceptance browser opened our test page, typed into its input, and
clicked the button. Then `co browser status` told us no browser was installed.
Following its advice would have downloaded the browser again. Nothing about the
successful page operations suggested that another download could help.

The installation probe asked Patchright for Chromium's executable path. That
was sensible: guessing a cache directory would break when the driver's version
or platform layout changed. But the probe used Patchright's synchronous API,
and status now ran inside the daemon's asyncio event loop. The driver refused
that combination. Our diagnostic caught the exception and translated it into
“none installed.” We had turned a failed measurement into a claim about the
machine.

The older tests supplied either a path or no path. Both cases passed because
neither cared where the probe ran. A new test made the probe reject an active
event loop, reproducing the false missing-browser message. Moving the fallback
probe to a worker thread made that test pass without changing which browser
launches or how paid sessions are selected.

On the same Linux acceptance machine, the repaired status printed the installed
Chromium executable while the real page still passed navigation, reading,
typing, script execution, clicking, and screenshot checks. The focused status,
probe-cache, and async-daemon suite passed 23 tests. Those are diagnostic and
free-browser results, not evidence that the paid panel flow has passed.

Next time a diagnostic catches an exception to remain usable, its tests need
to cover the context in which the measurement runs—not just the values we
hope it will return.

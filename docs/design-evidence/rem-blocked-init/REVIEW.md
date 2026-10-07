# Blocked init: Home must say the pass failed

Before: the released a42 template describes two failed investigations as
“Ready when there is something new.” After: Home names the failed count,
classifies refused model access and timeouts, and provides a 44px action to
open the maintenance record. The source map is preserved.

The four PNGs use invented notebook data and the same two failed logs.
Phone: 390 × 900; desktop: 1440 × 900. Both fit without horizontal overflow.
Keyboard Enter opens maintenance and focuses its summary. Private screenshots
of the actual a42 run independently show five failed investigations and zero
written pages; those screenshots are retained locally and are not committed.

This change does not repair credentials or stop queued work after an auth
failure. Those parts of #2302 remain open. Failure grouping follows the
existing latest-pass 18-hour window and is not a new per-init accounting API.

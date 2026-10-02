# The week that looked stuck

The owner asked REM to run against real mail. Five weekly Gmail windows
completed, then the terminal stayed on the sixth. The client was still reading
from Google, but there was no new progress line for several minutes. It looked
like init had frozen before it had written anything useful.

That week held 327 messages. Gmail's listing returns at most 200 at a time, so
REM splits a full week into smaller windows until it has every message. The
Gmail adapter fetched detailed headers for those first 200 before REM made the
split. The split then fetched the same headers again. The request had no socket
timeout either, leaving a slow read without a definite end.

The scanner now asks for IDs only when a full window must be split. It fetches
headers for the smaller, final windows, and Gmail requests have a 30-second
timeout with retries. Other Gmail commands still get their complete listing.
On the next private 90-day run, the 327-message week completed in about 81
seconds. Init then saved all 3,202 listed mail bodies and completed its selected
36 pages, each with source references. No private mail or page text is part of
this record.

This fixes the repeated work and the unbounded wait. The owner page still
appeared only after the map and full body archive. That is too long a wait for
the first moment of value on a large mailbox; moving the quick owner pass
earlier remains a separate first-run design problem.

# The Upload Button Was in Another Document

*2026-08-26*

The file input was plainly visible in Chrome. Our async browser could not find
it.

This is an easy failure to misread during an async migration. The locator call
looks familiar, the selector is correct, and the old browser uploads the file.
It is tempting to blame a missing `await`. The actual problem was spatial: the
editor lived in an iframe, so the control belonged to another document.

The synchronous browser had already learned this lesson. It filtered the page's
frames by URL or name, counted matching controls across those frames, and treated
the caller's index as a position in that combined list. A quick async port that
searched only the main page would keep the same method name while quietly
changing which pages it could operate.

## The chooser made the race visible

Direct file inputs are forgiving. Playwright can set files on a hidden input
without opening the operating-system picker. Upload buttons are less forgiving:
the browser emits a file-chooser event only as a consequence of the click. The
listener must exist before the click, the event must be awaited afterward, and
only then can the selected files be set.

That sequence forced the real design into view. Frame selection was not a detail
inside one upload method; it was the routing boundary shared by scripts, direct
inputs, and chooser-trigger controls. We introduced one frame enumeration path
that preserves the old filters and global match order. Each async operation then
awaits its own locator, evaluation, chooser, post-upload wait, and context save.

We also stopped at an important edge. Selector clicking in the supported browser
is humanized. Porting it as a raw locator click would have made the checklist look
more complete while changing observable behavior. That work remains with the
humanized-input boundary.

## Make the browser prove where the file went

Mocks can prove that methods were awaited and error strings stayed stable. They
cannot prove that Chrome delivered a chooser event from a child frame.

The native acceptance page therefore contains a named iframe with two upload
paths. The test runs a local script inside that frame, sets one file input
directly, then clicks a button wired to a second hidden input. It reads both
selected filenames back from the frame's DOM. We run the same scenario once from
the source tree and once from an installed wheel.

The lesson is broader than uploads: async parity is not a count of converted
methods. It is preservation of time and place—when a listener begins waiting,
which document receives an operation, and when success is safe to report.

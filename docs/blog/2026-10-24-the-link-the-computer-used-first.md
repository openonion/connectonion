# The computer used the phone link first

Implementation draft; no package publication is claimed here.

The command printed a private link and opened the browser. Both actions used the same one-time ticket. That looks convenient on a computer, but the code contained the failure the phone user would meet next: opening the printed URL on the phone came after the desktop had already consumed it.

The fix starts before any browser opens. The command creates independent computer and phone tickets, opens only the computer ticket, and prints the unused phone link. In an interactive terminal it also renders that link as a QR code. An explicit `--qr` is phone-only; `--no-browser` still gives scripts one clean URL. A phone can open that URL directly. The older signed challenge remains a compatibility path, rather than the path the phone is expected to follow.

The link now allows up to ten minutes for moving between devices. Extending that small window exposed a different boundary: a signed-in browser must not repeatedly turn a nearly expired session into another full day of access. Handoff records therefore retain the parent token’s absolute expiry as well as its original authority time. A new session can never outlive that parent, and revocation still applies to the original authority. The old manual browser proof also receives a real 24-hour token instead of a long token hidden behind a short cookie.

Eleven real PostgreSQL checks exercise the boundary, including concurrent exchange, waiting on a row lock across expiry, chained transfers and account migration. The lock test was useful: checking the clock before waiting for the row can still accept a ticket after its deadline. The code now takes a fresh clock after obtaining the lock.

The visible experience should be simpler than that machinery. A signed-in mailbox has an Open on phone action with a fresh locally generated QR; an unsigned phone can paste the link it already has. The official OpenOnion mark identifies both ends, while the private key stays where it was. Final browser coverage and rollout evidence accompany the implementation; this draft does not claim a PyPI release.

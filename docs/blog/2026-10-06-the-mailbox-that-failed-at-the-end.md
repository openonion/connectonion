# The mailbox that failed at the end

A lifetime scan can read thousands of mail headers and still fail on its last
provider request. In a public a41 wheel trial, the source inventory counted
15,551 observed rows, but a late Gmail `SSLError` and Outlook `ConnectError`
left the final People map with only the owner. The CLI called the coverage
incomplete; it did not pretend to have found everyone. It also discarded the
useful years it had already read.

The map used one return value for each mailbox's whole history. Any exception
outside the timeout class left that return value unavailable. We changed the
failure boundary to a year: completed years contribute their people to the
map; a broken connection marks the remaining range incomplete. A timeout can
still skip its affected year and continue to later years. The other mailbox
continues either way. The estimate remains explicitly a lower bound.

This preserves partial discovery, not a complete census. The next obligation
is durable checkpoints so a retry starts at the failed range. Until then, a
retry may rescan successful years. We keep that work in
[#2298](https://github.com/openonion/connectonion/issues/2298) and do not call
an incomplete scan “all people.”

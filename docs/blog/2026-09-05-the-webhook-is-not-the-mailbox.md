# The webhook is not the mailbox

A WhatsApp webhook says that Meta attempted delivery. It does not say the local
agent stored the message. Treating those as the same event creates the worst kind
of reliability bug: a successful HTTP response followed by an empty inbox.

The 1.8.5 preview splits the boundary. O API verifies the raw-body signature,
deduplicates the provider event, and holds a normalized delivery under a lease.
The local listener claims it, writes the ordinary seven-field mailbox record, and
only then acknowledges the remote delivery. A disk error produces a negative
acknowledgement and a retry instead of a quiet loss.

Outbound traffic takes the opposite route. The user's WhatsApp access token stays
local and the CLI calls Meta directly. O API needs only the webhook app secret and
verify token, encrypted at rest, because those are what let it authenticate public
pushes. The division is intentionally asymmetric: every credential exists in the
smallest trust boundary that can do its job.

Fixtures cover signatures, ownership, deduplication, leases, retries, and the
24-hour service-window error. A real WABA subscription is still a release gate,
not something a unit test can honestly claim to have proved.

# Row One Needed a Listing

Draft for 1.8.4; publish after release acceptance.

`co gmail sent` showed a message as row one. `co gmail read 1` could then open
row one from an older inbox. The output looked actionable, but its numbers had
never been written to the cache that `read` used.

Updating the cache after every listing fixes that example. It leaves another:
one terminal lists an inbox, another searches mail, and the first terminal
replies to row one. Both commands succeed while choosing a different message
from the one the operator saw.

The new listing token makes the missing context visible. A row number travels
with `--listing TOKEN`; a full provider ID needs no token. The token freezes the
ordered IDs for 15 minutes and belongs to the account Gmail actually reports.
Saved OAuth email metadata alone cannot establish that identity. A subsequent
listing cannot replace the old rows, and a lost or expired listing asks the
caller to list again.

Requiring a token adds typing for numbered references. Using a full ID in the
printed next command keeps the common path short. The extra context matters
most when commands overlap, because success must still refer to the message
that was selected.

# The address that stopped at @gmail

A handoff preview looked clean. The session copy that `send` uploads did not.
Inside an AI reply sat a contact written the way REM's fact pages often write
it: `name@gmail`, no top-level domain. Full addresses for the same person had
already become `[email removed]`. This one walked through.

`mask()` only recognised a complete `user@domain.tld`. The truncated form comes
from REM headers that get cut before the TLD, then quoted back into the
session. It names the person as clearly as the full address does, and it is
exactly the kind of detail a shared handoff page should not keep.

The email matcher now also accepts a short list of known mail hosts written
without a TLD — gmail, outlook, hotmail, yahoo, icloud, and the usual cousins.
A bare `alice@` token is still left alone. `others()` and `mask()` share the
same pattern, so the brief, the session copy and the answers all agree. A unit
test feeds the truncated forms through and checks they disappear while
examples and kept addresses stay.

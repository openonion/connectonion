# Google login belongs on your computer

The YouTube work exposed a mismatch. The CLI already saved a refresh token on
the user's computer, but the backend refreshed a second copy from its database.
Adding a granted-scopes column would have made the second copy more authoritative,
not made the local login more useful.

We chose one durable owner: the computer where consent began. The CLI opens a
loopback callback and creates a temporary public key. After Google exchanges the
code, the broker encrypts the credentials for that key and sends them straight
back to the CLI. Later refresh requests carry the local token. The application's
client secret stays on the broker, but a user's refresh token does not stay there.

This reuses the Microsoft handoff instead of introducing a second Google desktop
application. It also avoids moving or resetting existing credential rows. The
tradeoff is explicit: an older CLI that asks the server to find its login must
upgrade. A server-side fallback would quietly restore the ownership mismatch.

Default consent asks for the four Google services the CLI implements. A caller
can request fewer scopes, and the saved grant records what Google actually
returned. Consent is still the user's decision; requesting a capability cannot
make a denied capability true.

The tests seal and decrypt synthetic credentials and fail if a Google credential
table is touched. That proves the storage boundary, not that a real account or
YouTube upload has been accepted. Live consent remains a separate release gate.
The 1.8.3 package is being prepared, not announced as available here.

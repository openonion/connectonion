# A Phone Is Not an Agent Private Key

The first SMS pairing design had one appealing property: it was easy to
explain. Put the Agent's recovery words into the phone and both ends possess the
same identity. It was also the wrong security boundary. A phone receiving SMS
needs permission to upload ciphertext; it does not need the power to impersonate
the Agent everywhere that identity is accepted.

The replacement starts from two existing identities instead of collapsing them
into one. The Agent already has an Ed25519 key. Android creates its own
non-exportable P-256 key in Android Keystore. The Agent signs a short-lived QR
challenge, so Android can verify who asked to pair without trusting the server.
Android signs the complete challenge, so the server can verify that the claimant
owns the device key it presented.

That still leaves one hard question: how does the person know the right phone
won the race? Both endpoints hash the exact signed challenge together with the
device public key and display six digits. Only after the person compares those
digits does the Agent sign the exact device key. A copied QR can occupy the
pending slot, but it cannot turn that into an active upload credential unless
the person approves the attacker's different code.

The six digits are deliberately not described as strong cryptography. They are
roughly twenty bits and depend on a human actually looking. The strong parts are
the endpoint signatures; the digits are the short, usable bridge between two
screens. The one-time state and short expiry keep that bridge narrow.

This split also makes revocation honest. The phone receives an upload-only
credential bound to one SMS inbox, not a copy of the Agent identity. Losing the
phone means revoking one device. It does not mean rotating the Agent's recovery
words and every capability derived from them.

The general lesson is that “make two devices work together” is not the same as
“give both devices the same key.” Pairing should grant the smallest durable
capability the new device actually needs, and preserve a visible moment where
the owner can see exactly what is being trusted.

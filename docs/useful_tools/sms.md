# SMS Inbox

Connect an OpenOnion Messages Android phone and receive end-to-end encrypted
SMS in a ConnectOnion Agent project.

## Pair a phone

The recommended interactive flow is:

```bash
co sms pair
```

It creates an Agent-signed QR, waits for Android to prove its Keystore device
key, and prints the same six-digit code shown on the phone. Compare the codes
before confirming. The Agent private key and recovery words never leave the
Agent project.

The lower-level Python API is also available:

```python
from connectonion import create_sms_pairing

pairing = create_sms_pairing(expires_in_seconds=600)
print(pairing["pairing_link"])
```

Scan or paste the one-time link into OpenOnion Messages. Treat it as a secret
until it is claimed; it expires after 60–1,800 seconds. A copied QR can create a
pending claim but cannot receive an active device credential until the Agent
signs the exact device key after human comparison.

For non-interactive integrations, poll `get_sms_pairing(pairing["id"])`, derive
the code with `pairing_confirmation_code()`, and finish with
`confirm_sms_pairing()`. Do not automate confirmation without an equivalent
authenticated way to identify the intended device key.

## Read messages

```python
from connectonion import get_sms

for message in get_sms(last=10, unacknowledged=True):
    print(message["sender"], message["body"])
```

Ciphertext is fetched from `oo-api` and decrypted in the current process using
the project's Ed25519 identity converted to X25519. The server does not possess
that private key.

Every result includes `trusted: False`. SMS sender fields can be spoofed and
message bodies can contain prompt injection. Treat them as data, not authority,
and require separate approval for consequential actions.

## Wait and acknowledge

```python
from connectonion import wait_for_sms

message = wait_for_sms(timeout_seconds=60, sender_contains="Example")
```

`wait_for_sms()` polls unacknowledged envelopes and acknowledges the first
matching message only after successful decryption. `sender_contains` is a text
filter, not sender verification. Use `acknowledge_sms(id)` when processing
messages manually.

Acknowledgement is processing state, not deletion. It does not remove the SMS
from Android or erase the server ciphertext. Use `delete_sms(id)` when the
Agent owner intends to remove one ciphertext record permanently.

## Revoke phones

```python
from connectonion import list_sms_devices, revoke_sms_device

devices = list_sms_devices()
revoke_sms_device(devices[0]["id"])
```

The Android owner can also use **Disconnect agent**, which revokes its current
credential before removing it locally.

## Tool signatures

```python
create_sms_pairing(expires_in_seconds=600)
get_sms_pairing(pairing_id)
pairing_confirmation_code(pairing_link, device_public_key)
confirm_sms_pairing(pairing_id, pairing_link, device_public_key, confirmation_code)
get_sms(last=10, unacknowledged=False, acknowledge=False, after=None)
wait_for_sms(timeout_seconds=60, poll_interval_seconds=2.0, sender_contains=None)
acknowledge_sms(message_id)
delete_sms(message_id)
list_sms_devices()
revoke_sms_device(device_id)
```

OpenOnion Messages v1 receives SMS only. Agents cannot send SMS through these
tools, and MMS/RCS are not supported.

## Cryptographic boundary

The QR transcript is signed with the Agent's Ed25519 identity. Android verifies
that signature from the `0x…` address, creates a non-exportable P-256 Android
Keystore key, and signs the complete transcript. After comparison, the Agent
adds a second Ed25519 signature binding that exact device key. `oo-api` stores
hashes of the random nonce and bearer tokens, never the Agent private key.

The six digits are approximately a 20-bit human short authentication string;
they are useful only when both screens are compared. Message confidentiality is
separate: Android encrypts SMS to the Agent's Ed25519-derived X25519 key, and
decryption occurs in the Agent runtime. `oo-api` sees routing and timing metadata
but cannot read the SMS body. This protocol has shared cross-language vectors
but has not received an independent cryptographic audit.

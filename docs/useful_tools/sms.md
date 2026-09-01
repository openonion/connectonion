# SMS Inbox

Connect an OpenOnion Messages Android phone and receive end-to-end encrypted
SMS in a ConnectOnion Agent project.

## Pair a phone

```python
from connectonion import create_sms_pairing

pairing = create_sms_pairing(expires_in_seconds=600)
print(pairing["pairing_link"])
```

Paste the one-time link into OpenOnion Messages. Treat it as a secret until it
is claimed; it expires after 60–1,800 seconds.

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
get_sms(last=10, unacknowledged=False, acknowledge=False, after=None)
wait_for_sms(timeout_seconds=60, poll_interval_seconds=2.0, sender_contains=None)
acknowledge_sms(message_id)
delete_sms(message_id)
list_sms_devices()
revoke_sms_device(device_id)
```

OpenOnion Messages v1 receives SMS only. Agents cannot send SMS through these
tools, and MMS/RCS are not supported.

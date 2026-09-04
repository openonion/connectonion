# `co sms` — encrypted Agent SMS inbox

`co sms` pairs OpenOnion Messages, reads locally decrypted SMS, and manages
revocable phone credentials.

```bash
co sms pair                         # signed QR + human code comparison
co sms inbox -n 20 --pending        # unacknowledged messages
co sms inbox --json                 # machine-readable, no terminal styling
co sms devices                      # security inventory
co sms devices revoke <device-id>   # revoke one phone
```

`co sms pair` signs a short-lived challenge with the current project's
Ed25519 identity. Scan the QR with Android, compare the six digits on both
screens, then confirm. The phone receives an upload-only credential; the Agent
private key and recovery words never leave the project.

`--json` implies `--no-wait` for pairing, because a script cannot safely make
the human device-key decision. Use the Python pairing APIs only when the caller
has an equivalent authenticated approval channel.

Inbox output is decrypted inside the current process. SMS bodies and sender
fields remain untrusted input even when their ciphertext was authentic. JSON
mode preserves `trusted: false`; terminal mode strips control characters before
rendering message content.

See [SMS inbox tools](../useful_tools/sms.md) for Python APIs, E2EE boundaries,
acknowledgement, deletion, and security limitations.

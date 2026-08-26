# Remote Browser lifecycle (1.8 preview)

Remote Browser is an authenticated OIP service for browser sessions owned by a
remote caller. The first 1.8 boundary manages lifecycle only:

```bash
co remote-browser 0xHOST start
co remote-browser 0xHOST sessions
co remote-browser 0xHOST status rb_0123456789abcdef0123456789abcdef
co remote-browser 0xHOST diagnose rb_0123456789abcdef0123456789abcdef
co remote-browser 0xHOST stop rb_0123456789abcdef0123456789abcdef
```

Use `--json` for the complete stable envelope. A successful envelope includes
`schema_version`, `ok`, `command`, `request_id`, `summary`, `result`, `state`,
`tips`, `warnings`, and `next_actions`. Failures add a stable `code`, `message`,
`retryable`, and `retry_after_seconds`; scripts should branch on `ok` and `code`,
not English text.

`start` is idempotent for the same authenticated owner and request ID. Session
IDs are identifiers, not bearer secrets. Status, listing, diagnosis, and Stop
are filtered by the OIP identity that completed CONNECT, so copying another
owner's session ID does not grant access. Stop is idempotent and retains a
tombstone for retry/reconnect evidence.

This preview accepts direct OIP transport and `proxy=direct` only. A Relay path
returns `SECURE_CHANNEL_UNAVAILABLE` until the reviewed OIP secure channel is
available. It never downgrades to plaintext browser control. Other proxy modes
return `REMOTE_SESSION_PROXY_LOCKED`.

Navigation is intentionally unavailable. Validating only the initial URL would
leave redirects, DNS changes, and subresources able to cross the intended
network boundary. `diagnose` therefore reports `navigation_policy: not_enabled`.
Continue to use local `co browser` for page actions while that policy is being
specified and tested in
[#1297](https://github.com/openonion/connectonion/issues/1297).

See [DD-055](../design-decisions/055-owner-bound-remote-browser-lifecycle.md)
for the decision and follow-up gates.

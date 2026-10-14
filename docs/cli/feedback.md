# Feedback

These commands currently require the [development branch installation](experimental-integrations.md#install-the-preview); they are not released on PyPI yet.

Every `co` invocation ends with feedback channels on **stderr**, including failures. Command results remain on stdout. Feedback channels stay visible when Next-step tips are disabled.

- [GitHub issue](https://github.com/openonion/connectonion/issues/new): best for reproducible bugs and integration requests.
- [Discord](https://discord.gg/4xfD9k8AUF): quick conversation and troubleshooting.
- Email: `aaron.xie@mail.openonion.ai`; subject `[ConnectOnion feedback]`.

```sh
co feedback
co feedback report --command 'co gsheets read'
```

These commands print GitHub/mailto links with the ConnectOnion version, Python version, operating system and the command name you supply. They do not open a browser or submit a report. Add expected behavior and the actual error; remove credentials before sharing logs. There is no automatic upload of your environment or command arguments.

## Maintainer mailbox listener

The mailbox owner can run:

```sh
co feedback listen --once
co feedback listen --interval 60
co feedback inbox
```

The listener uses the mailbox owner's ConnectOnion credentials, reads only `aaron.xie@mail.openonion.ai`, and keeps messages addressed to that mailbox whose subject contains `[ConnectOnion feedback]` (case-insensitive). Other ConnectOnion users cannot read this mailbox by running the command.

Matching messages are saved as JSON in `~/.co/feedback` (or the selected global configuration root). Each receipt is written atomically before the cursor advances, deduplicated by mail ID, and stored with private file permissions. It paginates beyond the first 100 messages and resumes from the newest-seen ID. Reads preserve unread state. The selected identity must own the address and the backend must support scoped address filtering; errors stop the collector visibly.

This first listener collects feedback for us to inspect. It does not run instructions from emails, send replies, or create GitHub issues. `co feedback inbox` prints the saved receipts as JSON lines. Keep one listener running per mailbox; no multi-worker orchestration is needed.

A local macOS launch agent may run the collector after login. It operates while that Mac is awake and connected. A server deployment is a separate operational step; changing the public feedback address requires updating the collector's address and report links together.

# Discord CLI (`co discord`)

ConnectOnion 1.8.5 uses a bot you own as a local mailbox. The listener opens an
outbound Discord Gateway connection; no public endpoint or O API credential is
involved.

```bash
co discord check
co discord listen
co discord receive
co discord reply MESSAGE_ID "done"
co discord send CHANNEL_ID "deployment finished"
```

Create an application and bot in the Discord Developer Portal, enable the
Message Content privileged intent, install it with permission to view channels,
read message history, and send messages, then store its token in
`~/.co/keys.env`:

```text
DISCORD_BOT_TOKEN=...
```

The token is read only by the local process. It is never sent to O API, written
to the mailbox, or included in an error. The listener ignores bot and webhook
messages. Direct messages are marked as addressed to the bot; guild messages
are marked `mentioned` only when they mention the bot or reply to its message.
Consumers decide which users, guilds, and channels are authorized.

Gateway sequence and session data stay in memory. Discord replays missed
events when the process resumes a session, and `inbox.jsonl` deduplicates by
Discord's globally unique message snowflake. A full process restart may receive
a duplicate from Discord; it is logged and not queued twice.

Messages are limited to Discord's 2000-character limit. One provider-directed
rate-limit retry is honored. Live completion requires a real bot, DM, guild
mention, forced reconnect/resume, duplicate delivery, and reply capture; the
automated suite uses fixtures and never sends a real message.

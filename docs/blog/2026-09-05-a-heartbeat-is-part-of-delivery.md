# A heartbeat is part of delivery

Receiving a Discord message is not just parsing `MESSAGE_CREATE`. Before that
event can exist, the client must discover the Gateway, identify with the right
intents, answer heartbeats, remember sequence numbers, resume sessions, and
reconnect without turning one outage into a message storm.

The 1.8.5 preview keeps that protocol machinery inside the adapter and exposes
the same seven-field local mailbox used by Feishu and Telegram. Bot, webhook,
and self-authored events are filtered before storage. Direct messages are
addressed by definition; guild messages record whether the bot was mentioned or
replied to, so a consumer can decide when to act.

The token remains in `~/.co/keys.env`. REST replies have an explicit 2,000
character boundary and retry one Discord rate-limit response using the server's
delay. Gateway logs contain error classes and state transitions, never the bot
token or raw payload.

Fixture tests exercise identify, resume, heartbeat-driven sessions, filtering,
normalization, rate limiting, and redaction. Enabling the privileged Message
Content intent and completing a real server run remain external acceptance
gates; the preview label stays until those checks happen.

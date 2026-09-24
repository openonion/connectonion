# Discord CLI (`co discord`)

Turn a Discord bot you own into a directory of files. Every message the bot
can see becomes one line in a log and one file in a queue; anything that can
read a file can answer it. The same verbs as [`co feishu`](feishu.md), against
a different platform.

```bash
co discord check                        # token, listener, connection, unread count
co discord listen                       # hold the Gateway connection; every message → ~/.co/inbox/discord/
co discord receive                      # block for the next message, take it, print one JSON line
echo "on it" | co discord reply 123456789012345678   # a reply to that message, in its channel
co discord send 234567890123456789 "deployment finished"
co discord done 123456789012345678      # took it, decided not to answer
co discord consume -- claude -p         # one command per message, stdout is the reply
co discord ls                           # what is waiting
co discord chats                        # which channels have spoken
co discord log -f                        # everything, as it arrives
```

The listener dials out to Discord's Gateway, so there is no public endpoint to
open, and no OpenOnion credential is involved.

## Setup

1. Create an application at <https://discord.com/developers/applications>, then
   add a bot to it on the **Bot** page.
2. On the same page, under **Privileged Gateway Intents**, turn on **Message
   Content Intent**. Without it Discord closes the connection with code 4014,
   and `co discord listen` stops and says so.
3. Invite the bot to your server (OAuth2 → URL Generator, scope `bot`) with
   permission to View Channels, Read Message History and Send Messages.
4. Put the token in your global credential file:

   ```dotenv
   # ~/.co/keys.env
   DISCORD_BOT_TOKEN=...
   ```

The token is read only by the local process. It is never sent to OpenOnion,
never written into the inbox, and never included in an error. `co status` and
`co keys` show whether it was found and hide its value.

## What a message looks like

```json
{"id":"123456789012345678","chat":"234567890123456789","thread":null,
 "sender":"456789012345678901","sender_name":"Aaron","text":"@OpsBot check the failed deployment",
 "kind":"text","quoted":null,"mentioned":true,"at":"2026-09-05T05:00:00.000000+00:00"}
```

- **`id`** is Discord's message id, unique across the platform.
- **`chat`** is the channel id. A thread is a channel of its own in Discord, so
  a message in a thread has the thread's id as its `chat`, and replying there
  answers in the thread.
- **`mentioned`** is true for a direct message, and in a server when the
  message mentions the bot or replies to one of its messages. Role mentions and
  `@everyone` do not count.
- **`kind`** is `text`, or `image` / `audio` / `video` / `document` for an
  attachment with no text; the text is then `[image]` and so on. The file is
  not downloaded yet.
- Messages from bots (including this one) and webhooks are never written.

## Sending

A reply references the message it answers and pings nobody: not the person
being answered, not a role, not `@everyone`, whatever the text says. Discord
limits a message to 2000 characters; a longer one is refused before anything is
sent. One rate limit (HTTP 429) is waited out and retried; a second is reported.

A reply carries a nonce derived from the message and the text, so a reply that
is retried after a timeout returns the message Discord already posted rather
than posting it twice. `co discord reply --again` is a deliberate second post
and gets a fresh one.

`co discord edit`, `delete` and `react` exist so the verbs match every other
provider, and say plainly that they are not wired up for Discord yet.

## When the connection drops

The listener heartbeats at the interval Discord asks for. If a heartbeat goes
unacknowledged it closes the socket itself rather than waiting on a connection
that has stopped delivering, then reconnects and **resumes** the session, and
Discord replays what was missed. A replayed message the inbox already has is
logged as a duplicate and not queued twice. Session state lives in memory, so a
full restart of the listener identifies afresh: what arrived while nothing was
running is not replayed.

Some closes no reconnect can fix, and those end `listen` with exit 3 and the
thing to do: 4004 (the token was rejected), 4014 (Message Content intent is
off), and the sharding and intent errors 4010–4013.

To have your own agent answer, list the channel in `~/.co/host.yaml` under
`listen:` as `discord` and run `co ai`, exactly as for Feishu.

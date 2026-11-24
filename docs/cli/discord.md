# Discord CLI (`co discord`)

> **Experimental.** `co discord` was tested against fakes, not yet a live bot or a live user account. Edit, delete and react are not implemented and say so.

Turn a Discord bot you own, or (experimental, against Discord's terms) your
own account, into a directory of files. Every message the bot
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

## As your own account (experimental)

> **Warning.** This automates a normal user account (a "self-bot"). Discord's
> terms forbid it ([support article 115002192352](https://support.discord.com/hc/articles/115002192352)),
> and Discord can limit or terminate the account for it. **Link a throwaway
> account first** and run it for a week or two before you link the one you
> care about. This mode has not yet been run against a real Discord account.

```bash
co discord link --yes                 # shows a QR; scan it with the Discord phone app
co discord link --token --yes         # or paste a token (hidden input, or piped on stdin)
co discord check                      # says "acting as your own Discord account @you"
co discord listen                     # DMs and group DMs → ~/.co/inbox/discord/
co discord reply 123456789012345678 "yes, after lunch"
```

`link` prints the warning above and needs `--yes`, or a `y` at the prompt. The
QR is Discord's own "Log in with QR code": the phone shows which account it is
about to log in, you confirm there, and co receives a token for a new session
that only co uses. If Discord asks for a captcha, co says so and links nothing;
use `--token` instead. You can also put `DISCORD_USER_TOKEN=...` in
`~/.co/keys.env`. Use a token that no other client uses: one session shared by
two clients is what gets accounts flagged.

The token is kept in `~/.co/inbox/discord/user-session.json`, readable only by
you (mode 0600). It is full access to the account. Delete the file to unlink.
While it exists, every `co discord` verb acts as that account instead of the
bot, and `check` and `listen` say which one they act as.

What it does and does not do:

- **Receives** direct messages and group DMs. Messages in servers are ignored
  unless the channel id is in `DISCORD_USER_CHANNELS=<id>,<id>` in
  `~/.co/keys.env`. The account's own messages are never queued.
- **Replies and sends** only in DMs and group DMs the account already has (the
  listener learns them) and allowlisted channels. Before each message it shows
  "typing…" and waits a moment that grows with the length.
- **Caps** sends at 3 a minute per channel and 10 a minute in all. A send over
  the cap is refused, not queued.
- **Refuses** to open a new DM, send a friend request, join a server or post in
  any other channel. These are the actions that get accounts terminated.
- **Stops for good** when Discord objects: a 401, an "account disabled" or
  "verify your account" answer, a captcha, or Gateway close 4004. co stops the
  listener, writes the reason to `user-stopped.json` and does not log in again
  by itself. Fix the account in the official app, then run `co discord link
  --yes` again.
- Identifies to the Gateway as the web client (Chrome, invisible). The client
  build it presents is one constant in `connectonion/inbox/discord_user.py`
  and goes out of date as Discord ships new builds.

## What a message looks like

```json
{"id":"123456789012345678","chat":"234567890123456789","thread":null,
 "sender":"456789012345678901","sender_name":"Ellis","text":"@OpsBot check the failed deployment",
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

## Upgrades reach the listener

A running listener keeps the code it started with, so after an upgrade it
restarts itself in place once no send is in flight, and `check` names both
versions while they differ. A listener started before version tracking cannot
do that; replace it with one command:

```bash
co discord listen --restart     # stop the running listener, start a background one on the installed code
```

The details are the same for every provider; see
[WhatsApp: Upgrades reach the listener](whatsapp.md#upgrades-reach-the-listener).

To have your own agent answer, list the channel in `~/.co/host.yaml` under
`listen:` as `discord` and run `co ai`, exactly as for Feishu.

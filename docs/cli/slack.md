# Slack CLI (`co slack`)

> **Experimental.** `co slack` was tested against fakes, not yet a live
> workspace. Edit, delete and react are not implemented and say so. It is in
> 1.8.9 so people can try listen and reply on a workspace of their own; tell us
> what breaks.

Turn a Slack app you own into a directory of files. Every message your bot can
see becomes one line in a log and one file in a queue; anything that can read a
file can answer it. The same verbs as [`co discord`](discord.md), against a
different platform.

```bash
co slack check                          # both tokens, listener, connection, unread count
co slack listen                         # hold the Socket Mode connection; every message → ~/.co/inbox/slack/
co slack receive                        # block for the next message, take it, print one JSON line
echo "on it" | co slack reply C0123456789:1727500000.123456   # a reply, in that message's thread
co slack send C0123456789 "deployment finished"
co slack done C0123456789:1727500000.123456   # took it, decided not to answer
co slack consume -- claude -p           # one command per message, stdout is the reply
co slack ls                             # what is waiting
co slack chats                          # which channels have spoken
co slack log -f                         # everything, as it arrives
```

The listener uses Slack's **Socket Mode**: it dials out to Slack over a
WebSocket, so there is no public URL, no port opened, and no OpenOnion
credential involved.

## Setup

Slack needs two tokens: an **app-level token** (`xapp-…`) that opens the Socket
Mode connection, and a **bot token** (`xoxb-…`) that reads who the bot is and
posts replies.

1. Go to <https://api.slack.com/apps> → **Create New App** → **From scratch**.
   Name it and pick your workspace.
2. **Socket Mode** (left sidebar) → turn on **Enable Socket Mode**. Slack asks
   for an app-level token: name it anything, give it the scope
   `connections:write`, and copy the `xapp-…` token it shows.
3. **OAuth & Permissions** → **Bot Token Scopes** → add:
   - `chat:write` — post replies
   - `im:history` — read direct messages to the bot
   - `app_mentions:read` — read messages that @mention the bot
   - `channels:history` — only if you subscribe to `message.channels` below
4. **Event Subscriptions** → turn on **Enable Events** (no Request URL is
   needed with Socket Mode) → **Subscribe to bot events** → add:
   - `message.im` — direct messages to the bot
   - `app_mention` — messages in a channel that @mention the bot
   - `message.channels` — optional: every message in public channels the bot
     is in, which is what lets a thread the bot is part of keep reaching it
     without an @mention each time
5. **App Home** → under **Show Tabs**, turn on **Messages Tab** and tick
   **Allow users to send Slash commands and messages from the messages tab**.
   Without it nobody can DM the bot.
6. **Install App** (or **OAuth & Permissions**) → **Install to Workspace** →
   **Allow**, then copy the **Bot User OAuth Token** (`xoxb-…`). Any time you
   change scopes later, Slack asks you to reinstall; do it, or the new scope is
   not in the token.
7. Put both tokens in your global credential file:

   ```dotenv
   # ~/.co/keys.env
   SLACK_APP_TOKEN=xapp-...
   SLACK_BOT_TOKEN=xoxb-...
   ```

8. Invite the bot to any channel it should hear: `/invite @YourBot` in that
   channel. `co slack check` then tests both tokens against Slack.

The tokens are read only by the local process. They are never sent to
OpenOnion, never written into the inbox, and never included in an error.
`co status` and `co keys` show whether they were found and hide their values.

## What lands

- **A direct message to the bot**: always, with `mentioned: true`.
- **A channel message that @mentions the bot**: always, with `mentioned: true`.
- **A message in a thread the bot started or has replied in**: when
  `message.channels` is subscribed, with `mentioned: true`, so a conversation
  can continue without an @mention on every turn.
- **Any other channel message** the bot can see (with `message.channels`):
  written with `mentioned: false`, like Discord, so `log` and `chats` still show
  the room; `co ai` and `consume` answer only what is addressed to the bot.
- **Never**: messages from bots (including this one), edits, deletions, joins,
  and other system subtypes.

With `message.channels` and `app_mention` both on, Slack sends an @mention
twice, once as each event. Both have the same id, so the inbox keeps one.

## What a message looks like

```json
{"id":"C0123456789:1727500000.123456","chat":"C0123456789","thread":"1727499000.000100",
 "sender":"U0123456789","sender_name":"","text":"<@U0BOT00000> check the failed deployment",
 "kind":"text","quoted":null,"mentioned":true,"at":"2024-09-28T05:06:40Z"}
```

- **`id`** is `<channel>:<ts>`. Slack's `ts` is unique only within a channel,
  so the channel is part of the id.
- **`chat`** is the channel id: `D…` for a direct message, `C…` for a channel,
  `G…` for a private one.
- **`thread`** is the thread's root `ts` when the message is in a thread, else
  `null`.
- **`sender_name`** is filled only when Slack includes a profile in the event;
  looking names up would need another scope, so it does not.
- **`kind`** is `text`, or `image` / `audio` / `video` / `document` for a file
  shared with no text; the text is then `[image]` and so on. The file is not
  downloaded (that would need `files:read`).

## Sending

`co slack reply <id>` answers **in the thread** of the message: in the thread
it came from, or a new thread under it if it was a top-level message. That is
Slack's own advice (reply to the thread's root, never to a reply). `co slack
send <channel> "text"` posts at the top of the channel; add `--reply-to <id>`
to post in that message's thread instead.

The text goes to Slack as typed: Slack reads its own *mrkdwn* (`*bold*`,
`<https://x|link>`, `<@U123>` to mention someone), not Markdown.

Slack advises keeping a message under 4,000 characters and truncates one over
40,000 rather than refusing it. `co slack` refuses anything over 40,000 before
anything is sent, because a silently cut answer is worse than an error; under
that, a long message shows with Slack's "Show more". One rate limit (HTTP 429)
is waited out, as long as Slack's `Retry-After` says (at most 30 seconds), and
retried; a second is reported.

Slack has no idempotency key for a post (Discord's nonce has no Slack
equivalent). If a reply times out after Slack accepted it, retrying it posts it
a second time; look at the thread first.

`co slack edit`, `delete` and `react` exist so the verbs match every other
provider, and say plainly that they are not wired up for Slack yet.

## When the connection drops

Every event Slack sends is acknowledged by its envelope id **after** it is
written to the inbox. If the write fails (a full disk), Slack is not told, so it
sends the event again; a message the inbox already has is logged as a
duplicate and not queued twice.

Slack refreshes a Socket Mode connection every few hours: it sends a
`disconnect` message, and the listener asks for a new URL and reconnects. A
dropped network does the same, with backoff up to 30 seconds. Nothing is
replayed across a full restart of the listener beyond what Slack itself
retries.

Some failures no reconnect can fix, and those end `listen` with exit 3 and the
thing to do: a token Slack rejects (`invalid_auth`, `token_revoked`), an
`xoxb-` token where the `xapp-` one belongs (`not_allowed_token_type`), and
Socket Mode being switched off in the app settings (`link_disabled`).

## Upgrades reach the listener

A running listener keeps the code it started with, so after an upgrade it
restarts itself in place once no send is in flight, and `check` names both
versions while they differ. A listener started before version tracking cannot
do that; replace it with one command:

```bash
co slack listen --restart     # stop the running listener, start a background one on the installed code
```

The details are the same for every provider; see
[WhatsApp: Upgrades reach the listener](whatsapp.md#upgrades-reach-the-listener).

To have your own agent answer, list the channel in `~/.co/host.yaml` under
`listen:` as `slack` and run `co ai`, exactly as for Feishu.

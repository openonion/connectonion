# A Message Id Is Not Unique

Feishu numbers every message once. Telegram numbers them per chat: the
first message in any conversation is `1`, the second is `2`, and a bot in
two groups will see `message_id: 55` twice before lunch. The mailbox dedupes
on the message id, so the second `55` would have been dropped as a
redelivery of the first, silently, in another group.

That is why a Telegram message in `~/.co/telegram/` is called
`-100123.55`: the chat, a dot, the message. It is unique across the bot,
`reply` can parse it back into the `reply_parameters` Telegram wants, and a
person reading `ls new/` can tell which group it came from without opening
the file. The change is one line in the provider and nothing in the mailbox,
which is what a provider boundary is for.

Telegram also solves a problem the tool then declines to solve. Its
`getUpdates` long poll keeps unacknowledged updates for a day and hands them
back in order, with an `update_id` that increases by one. The obvious move
is to persist that cursor so a restarted listener resumes exactly where it
stopped. The documentation then says that after a week with no updates the
next id is chosen at random. A persisted cursor would be right for a busy
bot and wrong for a quiet one, and a quiet bot is the one whose owner will
not notice. So the offset lives in memory, a restart asks for everything
Telegram still holds, and the mailbox's own dedup drops what it has already
seen. One mechanism, not two that disagree.

The other difference is what "mentioned" means. Feishu's `group_at_msg`
scope means the platform itself delivers only messages that @ the bot.
Telegram's privacy mode does something similar for commands and replies,
but a group where privacy mode is off delivers everything. The provider
therefore checks the entities Telegram attaches to each message: a
`mention` or `bot_command` whose text ends with the bot's own username,
learned from `getMe` at start, or a reply to one of the bot's own messages.
A private chat is always addressed to the bot. The consumer sees the same
`mentioned` boolean it sees from Feishu and does not need to know how it
was computed.

`co telegram send` already existed and stays exactly as it was, because
scripts depend on its output. The new verbs, `listen`, `receive`, `reply`,
`check`, `ls`, `log` and `serve`, sit beside it under the same group and
use the same token from the same `keys.env`. A bot that could only talk can
now also listen, and the person who set it up in July has nothing to redo.

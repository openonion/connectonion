# A Message Id Is Not Unique

The Telegram adapter was finished in early September. It had tests, a blog
post and a pull request, and then it sat there while the package it was written
against was renamed out from under it: `connectonion/listen/` became
`connectonion/inbox/`, the mailbox became an inbox, `serve` became `consume`,
and a message grew from seven fields to ten. By the time anyone came back to
it, the adapter imported a module that no longer existed.

Porting it looked like a find-and-replace. It mostly was. What made it worth a
post is the one decision that survived the move untouched, and the one that
had to be added because the new inbox asks a question the old mailbox never
did.

The decision that survived is the id. Feishu numbers every message once.
Telegram numbers them per chat: the first message in any conversation is `1`,
the second is `2`, and a bot in two groups will see `message_id: 55` twice
before lunch. The inbox dedupes on the id — that is how a redelivered message
is dropped instead of answered twice — so the second `55` would have been
thrown away as a repeat of the first, silently, in a different group. Nobody
would have noticed until someone asked why the bot ignored them.

So a Telegram message is called `-100123.55`: the chat, a dot, the message.
It is unique across the bot, `reply` can split it back into the quote Telegram
wants, and a person reading `ls new/` can tell which group it came from. The
fix is one function in the provider and nothing in the inbox, which is what a
provider boundary is for. There is a test now that delivers message 55 from
two groups and expects two files.

The addition came from `co telegram check`. The inbox on main has learned,
the hard way with WhatsApp, not to call a listener healthy because a process
holds a lock; it wants the listener itself to write down whether its
connection is up. A long poll has no socket to watch, so the adapter records
"connected" the first time `getUpdates` answers and "disconnected" when it
stops answering, and nothing in between.

Writing that down forced a question the old adapter had answered with a
loop: what if Telegram says no? It had retried every failure with backoff,
forever. For a dropped connection that is right. For a revoked token it is a
listener that looks alive and will never receive anything again. And for
HTTP 409 it is worse: 409 means somebody else is reading this bot's updates —
a second `co telegram listen` on another machine, or a webhook someone set
once and forgot. Telegram hands each update to exactly one reader, so two
listeners would each see a random half of every conversation, and both would
look fine.

Those two now end the listener with exit 3 and say what to do, the same code
a missing token gets, because they are the same kind of problem: a person has
to act before a restart helps.

`co telegram send` still takes two arguments and prints what it always
printed, because scripts depend on it. The inbox verbs sit beside it on the
same group, reading the same token from the same `keys.env`. The honest
remaining gap is the one the original post also admitted: none of this has
been run against a live bot yet. The fakes prove the loop, the offset, the
ids and the refusals. They cannot prove that Telegram agrees.

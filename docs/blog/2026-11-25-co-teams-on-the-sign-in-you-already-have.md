# `co teams` on the sign-in you already have

When we widened `co auth microsoft` in 1.8.9 so OneNote could ride on the same
login as Outlook, we also asked for the four Teams scopes an ordinary work or
school user can grant on their own: `Chat.Read`, `ChatMessage.Send`,
`Team.ReadBasic.All` and `Channel.ReadBasic.All`. Then the release shipped with
a one-line apology in the known limits: *chats can be read with the new
consent, but there is no `co teams` yet (#1907).* People already had the token
sitting in `~/.co/keys.env`. There was just nothing in `co` that spoke Teams.

Building `co teams` looked like copying `co onenote`: borrow `Outlook`'s token
refresh and throttling retries without inheriting its mail tools, number the
rows for fifteen minutes per account, strip the HTML out of message bodies, and
stop. The catch was that sharing one sign-in across Outlook, OneNote and Teams
means meeting every account `co auth microsoft` accepts — including the ones
Teams will never let in.

Half of `co auth microsoft` sign-ins are personal `outlook.com` accounts. For
mail and OneNote, that token works. For Graph's Teams endpoints, Microsoft puts
every personal account in one consumer tenant —
`9188040d-6c67-4c5b-b112-36a304b66dad` — or hands back an opaque `Ew…` compact
ticket, and `/me/chats` refuses it. We had already learned the painful half of
this lesson on OneNote (#1910), where calling a 401 "expired" sent an
`outlook.com` user back to `co auth microsoft` in a loop. On Teams, checking
for a missing `Chat.Read` scope first would have laid the exact same trap,
worse: signing in again with the same personal account can never grant a work
Teams chat API. So `Teams` reads `tid` off the token before touching Graph at
all — refusing `9188040d-6c67-4c5b-b112-36a304b66dad` with the real reason
while leaving B2B guests alone when `tid` is the host organisation's.

Two other habits from our chat commands also had to be dropped at the door. On
Slack, Discord, Feishu and WhatsApp, the natural first verb is `listen`, and
channels are where the work is. Under user-delegated Microsoft Graph, neither
is true. `Channel.ReadBasic.All` lists a team's channels, which any colleague
can consent to, while reading a single channel post needs
`ChannelMessage.Read.All` — a tenant-admin permission most users cannot approve
for themselves. And Microsoft's API terms explicitly forbid polling Teams
endpoints more than once per day to watch for new messages, with throttling or
app suspension as the penalty. Pretending `co teams` was a live inbox listener,
or quietly omitting channel bodies, would hide policy walls behind what looked
like missing features. Instead, `co teams channels` says up front where user
consent stops, `co teams send` previews the chat and text until `--yes`, and a
timed-out `POST` warns that the message may already be in the room rather than
inviting a duplicate send.

One login across tools is only a kindness when each tool is honest about the
edges of the badge it borrowed.

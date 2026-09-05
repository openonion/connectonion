# A Reply Is a Send Too

On September 4 we merged the fix for #1198. `co outlook send --at` had been
delivering the email immediately and leaving a second, deferred copy in
Drafts. The cause was the endpoint: `sendMail` creates and sends in one
step, and the deferred-send time we hung on it never reached the copy that
went out. The fix creates a draft, sets the time on the draft, and submits
that exact draft. A contributor validated it on a live mailbox: nothing
before the requested time, exactly one message after it.

Then the review notes said, in effect, "replies are unchanged on purpose."
That was honest scoping, and it was also the next bug. `co outlook reply --at`
went through `POST /me/messages/{id}/reply`, with the same property tucked
into the `message` block. The reply action is `sendMail` with threading
attached. It creates and sends in one step. Nothing about it suggests the
deferred time would fare any better there than it did on `sendMail`.

We went looking for a reason to believe otherwise and did not find one.
Graph's page on creating extended properties lists every request that can
carry one: `POST /me/messages`, `PATCH /me/messages/{id}`, and a dozen
siblings. Neither `sendMail` nor the `reply` action is on the list. The
`reply` page says the `message` parameter takes "any writeable properties to
update in the reply message" and then never names one. The only community
report we found of an extended property surviving a reply came from someone
who set it *after* `createReply`, with a `PATCH`, and sent the draft next.

So the reply path now walks the documented road. `createReply` makes a draft
that already knows its conversation. Attachments go to the draft's
attachments collection, because `PATCH` does not accept them. Then one
`PATCH` puts `PidTagDeferredSendTime` and `PidTagDeferredDeliveryTime` on the
draft, and `send` submits it. Four requests instead of one, and the draft
lands in `co outlook scheduled` beside the scheduled sends, where `cancel`
can reach it.

Two smaller things fell out. Draft creation needs `Mail.ReadWrite`, so the
scheduled branch checks the scope before touching the network: a token that
only carries `Mail.Send` fails with a re-consent hint instead of a Graph 403
after a reply may already have gone. And the docs page still promised that
scheduling "works with just the `Mail.Send` scope." It did, back when the
schedule was not being honoured. It does not now, and the page says so.

What we have not done is watch this one on a real mailbox. The unit tests pin
the four requests, their order, their payloads, and the early scope failure.
They do not prove Exchange holds a reply draft the way it holds a new one.
That is the check we are asking for before this ships, the same check that
earned the `send` fix its merge.

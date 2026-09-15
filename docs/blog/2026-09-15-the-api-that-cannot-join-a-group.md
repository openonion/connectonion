# The API That Cannot Join a Group

The ask was small enough to say in one line: a bot sits in the WhatsApp group
we already have with a customer, and when someone @s it, it answers. We had the
number. Meta has an official API. This looked like an afternoon.

The Cloud API has a `/groups` endpoint, so the first hour went into reading it
properly. It creates groups. It lists the groups it created. It does not join
one — there is no join endpoint, no invite-accept, nothing that takes a group
link. The groups it makes cap at eight participants, and creating them at all
needs an Official Business Account, which is granted on editorial merit through
a solutions provider and is not something you buy. Meta Verified does not
unlock it; that is the Business App, and Groups is Cloud API.

So the supported API cannot do the one thing we wanted, and the gap is not a
missing feature. A group a human made is the human's, and Meta will not let a
business identity walk into it. Read that way it is a reasonable policy, and it
still left us with an unanswerable question.

The other route is the one WhatsApp Web uses: link a companion device. The
phone stays the account, and the laptop — or, here, a process — becomes one of
the four devices it allows alongside itself. A linked device sees every chat
the number is in, groups included, because it is the account. That is the whole
trick, and it is also the whole problem: automating the consumer client is
against the Business Messaging Policy, and Meta bans numbers for it. Which is
why this landed as `pip install 'connectonion[whatsapp]'` and not as something
installed by default, and why the first paragraph of its docs is about buying a
SIM rather than pointing it at your own phone.

The design surprise came later, and it was not about policy. Every other
provider in `~/.co/inbox/` has `listen` in one process and `reply` in another:
Feishu replies are plain REST, so any process with a token can send. WhatsApp
has no REST. Every byte rides the one authenticated socket the listener is
holding, and a second process opening the same session file presents the same
device identity and takes the connection away from the first. Writing
`co whatsapp reply` the obvious way would have produced a command that
silently kills the listener it depends on.

So `reply` does not connect. It writes the text into `outbox/` and waits, the
listener picks it up and sends it, and the id comes back through the same
directory. Thirty seconds of nothing and it says what to start. It is an
inelegant answer to a constraint we did not choose, and it has a side effect
worth keeping: `send` and `reply` need no compiled library at all now, because
the only process that talks to WhatsApp is the one already running.

The lesson is the one we keep relearning about platform APIs. The question is
never "does the API have this endpoint" — it is "what does the platform believe
about who is allowed to be in this room". Groups are the human's, so the
business identity is kept out, so the only door left is to be a device instead
of a business. Everything downstream of that, the extra, the SIM, the
outbox spool, is just the shape that belief leaves in your code.

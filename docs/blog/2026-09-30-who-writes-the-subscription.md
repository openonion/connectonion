# Who writes the subscription

The owner is building an Airbnb pricing page with a partner. Every day
something comes up: a pricing rule changes, the launch moves, a decision waits
on the partner. co rem already files all of it into the project's page. What
the owner wanted was for the partner's own AI to know it too, without anyone
writing messages or copying notes across.

The first design answered the obvious question, "what should we send?", from
the sender's side. The owner's notebook would guess what the partner cares
about, draft a brief, and send it every night. It worked on paper. But the
guess was exactly the weak point. A guess about someone else's interests is
wrong in both directions: it sends what they don't need, and it misses what
they are stuck on.

The second design turned it around. The partner says what they care about in
a subscription prompt, and the sender filters by it. That is more accurate,
and it is also a form. Asking a busy person to describe their interests in a
paragraph is how a feature never gets used.

The turn came from the owner: the partner doesn't need to write anything,
because the partner's notebook already knows. co rem keeps a page for every
project, and each field it cannot fill yet says `Unknown`. Those are questions
waiting for a source. "Launch date: Unknown" on the partner's pricing page is
the subscription prompt, before anyone writes it.

So the sender only needs to say what it has. Each notebook sends a short card
to the contacts its owner picks, listing the topics it is willing to share,
with no content. The receiving notebook keeps the card with that contact. Each
night it matches the card against its own open questions. When one person can
answer three of them, it writes the request itself, asks its owner once, and
sends it. The sender's notebook checks the request against what its owner
allows, asks once, and from then on sends a brief whenever those pages change.
As the partner's questions get answered, the subscription narrows by itself.

The lesson is about where knowledge already lives. We kept designing
interfaces for people to tell the system what it could have read from its own
pages. The design is written down as DD-074, with the transports, the consent
points and the options we turned down.

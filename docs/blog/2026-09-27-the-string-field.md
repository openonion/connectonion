# The string field

Every WhatsApp message we receive gets a `kind`: text, image, audio. The code
that decides it walks the message's protobuf fields and names the message
after the first one it recognises. It had tests, a parametrised list of every
variant, and they all passed.

Then we counted the owner's real inbox. Of 334 messages, 154 had the kind
`messagecontextinfo`. Nobody sends a messagecontextinfo. It is the delivery
metadata WhatsApp attaches to nearly every group message. Those 154 were
ordinary text: "dinner at 7?", "yes", "who's bringing the car?". An agent that
answered only `kind == "text"`, which is what the docs suggest, skipped almost
half of what people said to it.

The walk only looks at fields whose type is another message, because that is
where images and replies live. Plain text is not one of those. `conversation`
is a string field. So the walk stepped over the text, found the metadata next,
and named the message after it. Our test fakes gave `conversation` the message
type, because whoever wrote them assumed it had one. The tests and the code
shared the same wrong belief, so they agreed perfectly.

The same walk explained a bug another session had already filed. The first
time someone posts in a group, WhatsApp sends two events under one id: a
sender-key frame with no text, then the message. We recorded the frame. When
the message arrived we dropped it as a duplicate of something we had already
seen, and the person's first words were lost.

The fix is small. Text is checked by name first. Metadata never names a kind.
A frame of nothing but metadata is not a message and is not recorded. What
made it trustworthy was the last test we added: it builds real neonize
`Message` objects in the exact shapes from the owner's inbox and runs the
check on those. When a fake and the code share a belief, a fake cannot catch
it being wrong.

The lesson: when a test double has to describe the outside world, build at
least one test from the real type.

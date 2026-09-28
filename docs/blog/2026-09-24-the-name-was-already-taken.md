# The name was already taken

The WhatsApp Cloud API adapter was finished three weeks ago. It had a test for
the one failure that mattered, a design note, a doc page, and a green CI run.
It never merged, and when we came back for it, the code it was written against
no longer existed.

It had been written for `connectonion/listen/`. Main had since renamed that
package to `connectonion/inbox/`, rewritten the mailbox as an inbox with ten
fields where there had been seven, and grown a CLI layer where every verb ends
by naming the next one. None of that was hard to follow. The hard part was a
single line in the old PR:

```python
"whatsapp": ("connectonion.listen.whatsapp", "WhatsApp", {}),
```

On main, `whatsapp` was already somebody else's. While the Cloud API branch
waited, `co whatsapp` had shipped as a linked device: a QR code, a phone, a
companion session that can sit in a group a person made. People were using it.
The Cloud API adapter wanted the same name for a different product.

The tempting port was to merge them. Both are "WhatsApp", both put messages in
a directory, and one command group with a `--cloud` switch would have looked
tidy in `co --help`. We wrote down what the two actually share and it came to
the brand. They sign in differently: a QR scan against a Meta app, a WABA and
a token. They are allowed to do different things: groups on one side, one-to-one
only on the other. They follow different rules: message any time on one side,
free text only within 24 hours of the customer's last message on the other.
Even their failures mean different things. The linked device is banned for
automation. The Cloud API is the sanctioned route and refuses a late reply
with error 131047. A single `co whatsapp` would have made every help line, every
exit code and every doc sentence start with "unless you are on the other one."

So the port became a second provider, `co whatsapp-cloud`, with its own
`WHATSAPP_CLOUD_*` variables and its own directory under `~/.co/inbox/`. The
two can run side by side and never read each other's files.

Almost everything else carried over as it was. The behaviour the old PR was
built around came through line for line: O API stores Meta's signed webhook,
the listener claims it under a lease, writes it to disk, and only then ACKs. The
test that pins it is the same test, rewritten against a real `Inbox` in a temp
directory, with a disk that fails on cue. When the write fails, the last call
is a NACK and there is no ACK anywhere in the log.

The port also turned up one thing the original could not have known. Its
listener retried every failure forever, with backoff. That was reasonable while
the O API side (openonion/oo-api#227) was expected to land alongside it. It
still has not merged. A listener polling a route that returns 404 would have
backed off to thirty seconds and stayed there, looking exactly like a quiet
inbox. Now a 401, 403 or 404 from O API stops the listener with exit 3 and names
the missing server change, because no amount of waiting will create a route.

The lesson we took is that the risky part of porting stranded code is the
names, not the lines. A name that was free when the branch was cut can mean
something else by the time it lands, and something other people rely on. The
code moved in an afternoon; deciding that `whatsapp` should stay what it had
become was the actual work.

It is still a preview. Nothing here has talked to Meta or to a deployed O API.
The fakes prove what happens at a failed write and a closed window. They cannot
prove that Meta's app review passes or that the webhook subscription is right.

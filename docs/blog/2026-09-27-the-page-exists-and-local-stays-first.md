# The page exists, and local stays first

A day ago `co wiki open` sent people to `chat.openonion.ai/<address>/wiki`, a page
O Chat did not have. The fix made the local snapshot the default again and put the
live view behind `--live`, with one switch, `LIVE_WIKI_SERVED`, to flip when the
page existed — flipping it would also make the live view the default once more.

The page exists now. O Chat's Wiki view shipped: it reads the notebook from the
owner's Host over a signed request, shows it in a sealed frame, and says "Host
offline" with the next step instead of an empty chat when nothing answers. So the
switch should flip.

But the owner had made a second decision in the meantime, on purpose: opening
locally is the default, and the live view is a feature. A snapshot opens on a
plane, with the Host stopped, on a machine that has never announced itself; the
live view needs all three to be fine. One switch was carrying two questions —
does the page exist, and should people land on it — and answering the first
would have silently overturned the second.

So there are two switches now. `LIVE_WIKI_SERVED` is true, which stops `--live`
warning about a page that is no longer missing. `LIVE_IS_DEFAULT` is false,
which keeps a bare `co wiki open` on the snapshot, and the test that guards the
default now names the decision it protects instead of the page that was missing.

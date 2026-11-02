---
title: The candidate that stops moving
date: 2026-10-26
description: 1.9.3rc24 is the freeze candidate. After it, a change has to be the reason 1.9.3 cannot ship.
---

The 1.9.3 line has had twenty-three release candidates. Each one was honest
about what it had and had not proved. Each one also brought new work, so no
candidate stayed still long enough for its own evidence to cover the release
we would call stable.

rc24 is where that stops. It carries the work merged after rc23. REM keeps
the originals it cited when its evidence is folded into an index. Its
translations copy Sources byte for byte. The owner's company is a company the
owner named, not whichever domain they happen to send mail from. Muse looks for
what a page does not know yet. One rule now keeps diary folders out of every
page and session unless the owner opts in. It also carries a macOS user service
for `co host`, and an inbox filter that tells you when an address is not yours
instead of telling you no mail came.

After rc24, the 1.9.3 line only takes a fix for something that would stop 1.9.3
from shipping. Anything else waits for the next line. If rc24 holds up end to
end, the same code becomes 1.9.3 unchanged. If it does not, the fix becomes
rc25, and the end-to-end check starts again from that candidate.

A freeze is a promise about what will not change. It means the testing done
against rc24 is testing done against 1.9.3, and that is worth more than one
more feature.

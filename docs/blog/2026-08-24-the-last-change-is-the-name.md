---
title: "The last change is the name"
date: 2026-08-24
author: ConnectOnion Team
---

RC10 had survived the run we kept failing to finish. A clean public install
opened real Codex and Claude Code Work Rooms, downloaded through a real browser,
compiled C, C++, and Rust, stopped provider work, narrowed permissions,
restarted the Host, and reconnected without sending the prompt twice. I copied
the candidate into a Stable branch expecting the last check to be ceremonial.

It failed three times.

The first failure said a final `1.7.0` package was still Beta. The second said
the release did not exist on the documentation site, which still called
1.6.12 Stable. Neither failure concerned the code RC10 had exercised. Both
were telling us that changing a version number is a user-visible operation,
not clerical cleanup.

The third failure came from ancestry, not the release script. The 1.6.12 line
contained a bounded set of operational fixes that had never reached the 1.7
branch. Calling RC10 unchanged would therefore have made Stable newer in name
but older in those behaviours. We forward-ported the missing fixes, published
RC11, and repeated the public-artifact checks instead of hiding the difference
inside the Stable commit.

The repeated gate then produced late evidence of its own. A truncated
image-looking tool result could crash formatting, and an unattended Auto run
ignored a configured browser-command grant because no live approval channel
existed. Both were release blockers, so we fixed them on 1.7, forward-ported
them to main/1.8, and published RC12. Stable is promoted from that newer
accepted source, not from the branch we had already prepared around RC11.

That exposed an awkward phrase in our own release plan: “promote RC10
unchanged.” I had been reading unchanged as identical files. But a Stable wheel
cannot be identical to an RC wheel. It must identify itself as `1.7.0`, carry
the Production/Stable classifier, and make an ordinary install resolve to the
new line. Its archive bytes must change even when its product source does not.

The useful invariant is narrower and stronger: promotion changes the promise,
not the behavior. No new retry, adapter event, permission rule, or UI contract
may hide inside the version commit. The package metadata and the public channel
must change together because they are two surfaces of the same promise.

After those failures, the RC12 release check passed the release-contract suite across the
version sources, lock, artifact provenance, workflow, history, and docs
contract. The new wheel and source archive passed `twine check`. More
importantly, the failure changed how we stage the release: the Stable React
reader and final O Chat head are prepared first, the package tag comes only
after that client gate, and the documentation switches only after PyPI serves
the package it names.

RC12 is the candidate that contains the accepted 1.7 behaviour, the complete
applicable 1.6.12 fix set, and the two late blocker fixes. 1.7.0 is the
promise that ordinary users may now depend on the same behavior. The last code
change was no code change at all; the last lesson was that names are part of
the product boundary.

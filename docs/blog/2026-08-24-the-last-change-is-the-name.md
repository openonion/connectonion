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

It failed twice.

The first failure said a final `1.7.0` package was still Beta. The second said
the release did not exist on the documentation site, which still called
1.6.12 Stable. Neither failure concerned the code RC10 had exercised. Both
were telling us that changing a version number is a user-visible operation,
not clerical cleanup.

That exposed an awkward phrase in our own release plan: “promote RC10
unchanged.” I had been reading unchanged as identical files. But a Stable wheel
cannot be identical to an RC wheel. It must identify itself as `1.7.0`, carry
the Production/Stable classifier, and make an ordinary install resolve to the
new line. Its archive bytes must change even when its product source does not.

The useful invariant is narrower and stronger: promotion changes the promise,
not the behavior. No new retry, adapter event, permission rule, or UI contract
may hide inside the version commit. The package metadata and the public channel
must change together because they are two surfaces of the same promise.

After those two failures, the release check passed 59 assertions across the
version sources, lock, artifact provenance, workflow, history, and docs
contract. The new wheel and source archive passed `twine check`. More
importantly, the failure changed how we stage the release: the Stable React
reader and final O Chat head are prepared first, the package tag comes only
after that client gate, and the documentation switches only after PyPI serves
the package it names.

RC10 remains the name of the artifact that earned acceptance. 1.7.0 is the
promise that ordinary users may now depend on the same behavior. The last code
change was no code change at all; the last lesson was that names are part of
the product boundary.

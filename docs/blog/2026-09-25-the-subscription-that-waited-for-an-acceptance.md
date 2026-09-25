---
title: "The subscription that waited for an acceptance"
date: "2026-09-25"
description: "An old skill still taught a handshake that the public skill subscription CLI never used."
---

The subscription skill looked thorough. It resolved an alias, signed a
SUBSCRIBE request, waited for the publisher to accept, downloaded each body,
and made links for several coding agents. Every step had a code block. That
detail made the instructions feel safer than a short command.

Then we compared it with the command users actually install. `co sub sync`
does not send SUBSCRIBE or wait for an accept queue. A public subscription is
a local decision to pull a publisher's skills. The CLI requires a full address
the first time, verifies the publisher's signed profile and revision, and
installs only the bodies the publisher made public. The old skill asked for an
identity that the reader did not need and proposed endpoints and file writes
that would bypass the CLI's checks.

The less visible mismatch was in the success report. A publisher's profile
can name a skill without publishing its body. A subscription can therefore be
recorded while zero skills reach a coding agent. Telling that reader to restart
their tools would imply that something had been installed when it had not.

The replacement skill now begins with the decision a reader can make: first
follow with a full `0x` address, refresh a pinned publisher, refresh everyone,
inspect the local list, or remove one. The command output supplies the counts.
The skill asks for a restart only when installation actually happened, and it
explains why the list's profile count may be larger than the mirrored count.

There is still judgment outside the command. A valid signature says who
published the text; it does not say that the text is safe to follow. The
publisher's identity is pinned by address, while the subscriber remains
responsible for reviewing instructions and authorizing consequential work.

---
title: "127.0.0.1 did not look like an IP address"
date: 2026-08-26
description: "Why Remote Browser needs the browser's idea of an address before it can enforce an egress policy."
author: ConnectOnion Team
tags: [remote-browser, security, chromium, ssrf]
---

# 127.0.0.1 did not look like an IP address

`127.0.0.1` is easy to reject. `2130706433` is the same address, and a browser
will happily turn the second spelling into the first.

That detail changes how Remote Browser navigation must be built. A conventional
URL parser can hand back `2130706433` as if it were an ordinary hostname. If a
security check classifies the text it received while Chromium classifies the
address it understood, the two components are enforcing different policies.

The first navigation implementation slice therefore contains no navigation at
all. It is a pure destination-policy module with a versioned catalogue of the
strange inputs that matter: shortened IPv4 such as `127.1`, single-number IPv4,
octal-like and hexadecimal parts, IPv4 embedded in IPv6, IDNA names, unsafe
ports, and mixed public/private DNS answers.

The policy canonicalizes the authority using the WHATWG IPv4-number rules that
browsers follow. It then classifies the resulting numeric addresses against a
frozen, reviewed copy of the IANA special-purpose ranges. We deliberately do
not call Python's `is_global`: its answers have changed across Python releases,
while ConnectOnion supports Python 3.10 through 3.13 and needs one security
answer on all four.

Two small tests caught disproportionately dangerous mistakes while this layer
was still isolated. Port `0` is falsey in Python, so `parsed_port or 443` quietly
turned a denied explicit port into the default HTTPS port. And several globally
reachable IANA protocol ranges were absent from the first conservative table.
The catalogue now makes both choices visible and reviewable.

This parser still opens no socket and performs no DNS lookup. That separation is
intentional. The next layer will resolve every answer, reject the entire set if
one address is prohibited, and dial only an approved numeric socket without a
second lookup. Later Chromium tests will prove that alternate spellings,
redirects, subresources, WebSockets, and rebinding attempts send zero bytes to
the protected destination.

Security work is easier to trust when each boundary can fail alone. Before the
browser is allowed to move, it first has to agree on what an address means.

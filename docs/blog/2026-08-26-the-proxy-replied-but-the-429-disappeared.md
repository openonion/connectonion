---
title: "The proxy replied, but the 429 disappeared"
date: 2026-08-26
description: "What one vanished overload response taught us about building a fail-closed browser gateway."
author: ConnectOnion Team
tags: [remote-browser, proxy, security, testing]
---

# The proxy replied, but the 429 disappeared

The overload test looked almost insulting in its simplicity. Hold one proxy
connection open, set the limit to one, open a second, and expect `429 Too Many
Requests`. The server wrote the response. The client received nothing.

On macOS, closing a TCP connection while peer bytes remain unread can reset the
connection. Our gateway had correctly refused the second client without parsing
its request, then erased its own refusal while cleaning up. That is not an SSRF
bypass, but it is exactly the sort of platform edge that turns a stable failure
contract into a browser error nobody can diagnose.

The fix is deliberately narrow. An overloaded connection still cannot reach
authentication, DNS, policy, or dialing. After writing the constant response,
the gateway consumes at most one bounded request buffer for 50 milliseconds so
the ordinary client close does not reset away the response. An attacker cannot
buy work by keeping the socket alive; the same header-size and time limits cap
the discard.

That failure arrived while building the gateway below Remote Browser. The
gateway binds one ephemeral IPv4 loopback socket, requires a fresh daemon-scoped
proxy credential, resolves every hostname once, denies a complete DNS set when
one address is prohibited, and hands only canonical numeric endpoints to the
dialer. There is still no Chromium flag and no `open` command. We want proxy
mistakes to fail in isolation before a browser can depend on them.

The useful turn was realizing that “refused” has two observable halves. The
protected side must see no dial, while the browser side must receive one clear,
bounded answer. We had asserted the first and assumed the second because the
server called `write()`. The failing client made us measure both ends of the
same refusal instead.

A security proxy has two jobs: refuse the wrong connection and make that refusal
boringly observable. The missing 429 was small, but it reminded us to test both.

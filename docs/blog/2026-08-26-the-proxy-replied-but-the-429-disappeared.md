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

The same test pass found a more serious shutdown problem. Python 3.14 waits for
accepted connections in `Server.wait_closed()`. Waiting for the server before
cancelling a resolver meant shutdown waited on the very task it was responsible
for stopping. Reversing that order—close admission, cancel owned handlers, then
wait for the listener—made cleanup deterministic across the supported Python
versions.

Other tests attack places where proxies become ambiguous: duplicate
authorization, a `Connection: content-length` token that tries to strip message
framing, a second pipelined authority after a declared request body, a WebSocket
Upgrade, mixed public/private DNS answers, and a hostname smuggled into the
numeric dialer. The important assertion is usually not the returned status. It
is that the dialer saw zero calls.

A security proxy has two jobs: refuse the wrong connection and make that refusal
boringly observable. The missing 429 was small, but it reminded us to test both.

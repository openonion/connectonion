---
title: "The daemon was not the slow part"
date: 2026-08-24
author: ConnectOnion Team
---

Our 1.7 release test kept losing contact with the browser. A state query would
miss its deadline, then closing the tab would miss another one. The obvious
story was that a page command had wedged the single-threaded browser daemon and
left every later request waiting behind it.

The socket trace contradicted that story. A fresh `co browser status`, pointed
at a socket that did not exist, took 40.82 seconds. There was no daemon to be
busy. The client had not reached the socket at all.

Every direct browser command was importing the natural-language Agent, the
Playwright browser implementation, the terminal UI, and provider integrations
before it could send a small local RPC. That work belongs in the long-lived
daemon, or in `co browser do` when a model actually needs the browser tool
schema. It does not belong in every status poll, click, or cleanup command.

The direct command path now loads only its transport client. Help loads the
browser schema when asked, and `do` installs the same tool methods lazily before
building its Agent. The wire protocol and daemon behavior did not change. The
same absent-daemon status check now takes 2.91 seconds.

The lesson was in the boundary, not the timeout. When a client repeatedly talks
to a persistent service, importing the service's entire implementation on every
call defeats the reason the service is persistent. Measure the path before
blaming the queue.

---
description: What an agent served depended on which command started it. Now there is one host, one switchboard in host.yaml, and a co host command that works on a machine set up five minutes ago.
tags: [Host, Design]
---

# One host, whichever door you came in by

We asked a simple question about hosting: if you set up an agent once, does it
serve everything? The answer depended on how you started it.

`co ai` served the agent, your REM pages and your chat channels. `python
agent.py`, the line `co create` prints, served the agent and the channels but
not REM. `co deploy` runs `python agent.py` on the server, so a deployed agent
never served REM either. `.co/host.yaml` had no line for it, so there was
nowhere to ask. Our own deploy guide said the template was "the same agent
`co ai` runs". It was not.

There was a second split under the first. `co ai` started its own listener
for chat channels, and then passed `~/.co` to the host, whose own consumer
read the same `listen:` from the same file. Every channel had two consumers,
with two different ideas of what a conversation's history was. Atomic
renames kept them from answering twice, which is why nobody noticed.

Then the new-machine test found the third. A person whose first contact with
co is a handoff mail gets co from the one-line installer, which keeps it in
its own environment. The next thing `co create` tells them is `python
agent.py`, and the system python has never heard of connectonion.

The fix is one door and one switchboard. `co host` runs `agent.py` with the
Python co runs on, so it works however co was installed. `host()` serves REM
unless `.co/host.yaml` says `rem: false`, answers the channels in `listen:`,
and `co ai` hands its channels to that same host instead of running its own.
`co create` now prints `co host`.

The rule we keep: a feature turns on in configuration, not in the choice of
command. Otherwise the person who set it up once finds out, on the day it
matters, that they came in by the wrong door.

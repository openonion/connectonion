# The page nobody opened

`co wiki open` is the command you run to look at your notebook. On the owner's
Mac it printed this, opened a browser tab, and said it had launched:

```
$ co wiki open --no-launch
Wiki open
Page: https://chat.openonion.ai/0xa633…25df/wiki
```

The tab never showed a notebook. O Chat has a page for an agent and a page for
one of its chat sessions, and nothing else, so `/0xa633…/wiki` was read as a chat
session whose id is "wiki". The route that was meant to serve it is
openonion/oo-chat#246, still open with red checks. And even with that page
deployed, it reads the notebook from the owner's own `co ai` Host over OIP. No
such Host was running. The command sent the reader to a page that did not
exist, to ask an agent that was not there.

A week earlier the same command had opened a self-contained HTML file: the
whole notebook embedded in one page, written to a temporary file, working with
the Wi-Fi off. The plan in #1637 was to replace it with a live view anyone could
reach from another device while the Host was up. The CLI half of that plan
landed first, and it switched the default on the day it landed, pointing at a
front end that had not shipped.

## Why every test was green

There were tests. One of them asserted, character for character, that the
default opened `https://chat.openonion.ai/<address>/wiki`. It was a correct
test of the wrong thing: it proved the CLI printed the string it meant to print.
Nothing asked whether a browser handed that string would show anything. The
release walks for 1.8.8 and 1.8.9 ran `co wiki open --local --no-launch` on an
empty notebook, which exercised the path that still worked and skipped the one
that had changed.

A URL is a promise made on someone else's behalf. The CLI can only keep it if
the page exists and, here, if a process on the user's own machine is answering.
Neither is something a string comparison can see.

## What changed

The default is the snapshot again, rendered fresh on every run so it is never
older than the notebook, and `co wiki open` prints its path and its `file://`
link. The live view is still there, behind `--live`, and the snapshot output
says so in one line.

`--live` now asks before it sends anyone anywhere, and it asks the two
questions a client's connect() depends on. Does the relay hold the Host's
announce socket, and has it heard a heartbeat in the last three minutes? That
is how O Chat reaches a Host behind NAT or on another machine. Failing that,
does one of the endpoints the Host announces answer `/info` as that address?
No model, no login, three seconds for the whole check. If neither answers, it
says the Host is not online, says to start it with `co ai`, and opens the
snapshot.

The first draft only did the second check, and a reviewer caught what that
meant: the owner's Host on a home network, perfectly reachable through the
relay, would have read as offline from a laptop anywhere else. "Online" has to
mean what the page that opens will find, not what this machine can dial.

The route itself lives in one constant next to one flag, `LIVE_WIKI_SERVED`,
set to False with a comment naming oo-chat#246. When that page ships, flipping
the flag makes the live view the default again, still behind the Host check.
A test guards the flag: until it flips, the default must never print a
chat.openonion.ai address, even with a Host online.

And a new test does what no test did before: it runs `co wiki open`, takes the
`file://` link it prints, opens it in headless Chrome, waits for the contents
page, clicks into People, and goes Back, failing on any page or console error.
It skips, saying why, on a machine with no browser.

## The lesson

The bug was not the unfinished route; unfinished work is normal. It was a
default that depended on two things outside the CLI — a deployed page and a
running process — and checked neither. A command a person runs to *see*
something is only tested when something looks at what it produced.

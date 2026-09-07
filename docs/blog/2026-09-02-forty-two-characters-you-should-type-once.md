# Forty-two characters you should type once

The remote browser worked. Every command to drive it looked like this:

```bash
co proxy share to 0x3f9a7c2e1b8d4f6a9c0e2b5d7f1a3c8e6b4d2f0a
co remote-browser 0x3f9a7c2e1b8d4f6a9c0e2b5d7f1a3c8e6b4d2f0a start --proxy shared
co remote-browser 0x3f9a7c2e1b8d4f6a9c0e2b5d7f1a3c8e6b4d2f0a status rb_…
```

The address is forty-two characters. It is the same forty-two characters in
every command, in every session, on every day, because the server you rent
does not move. And yet each command asked for it again, plus the `--proxy`
mode that also never changes, as if the tool had no memory between one line
and the next.

Aaron's review of the flow was one sentence: configure it once, and if it is
not configured, say so.

## Remember it, do not guess it

```bash
co remote-browser config 0x3f9a… --proxy shared   # once
co remote-browser start                            # from now on
co proxy share
```

`config` writes `~/.co/remote-browser.json`. Every command that used to take
an address now reads it from there when none is given. An explicit address on
the command line still wins, so a one-off against a second host needs no
reconfiguration.

The interesting rule is the failure. With nothing remembered and no address
given, the command does not pick a host from the proxy registry, the last
session, or anything else it could plausibly infer. It stops:

```text
No remote browser configured.
Set one with: co remote-browser config <address> --proxy shared
```

A remote browser is someone's machine and someone's bill. A tool that guesses
which one you meant is a tool that will one day start a session on the wrong
one, and the operator will find out from the invoice. "I do not know, here is
how to tell me" is the only honest answer.

## Deciding whether an address is there

The parser used to count positionals: two words meant `<address> <command>`.
Making the address optional would have turned that into a table of every
command and its arity. The address is the only token that can start with
`0x`, so the parser looks at the first word instead of counting the rest. One
check, no table.

## The other default we got wrong

While here: the remote session started headless by default. `co browser` on
your own laptop opens a visible window, and the browser layer already knows
to run headless on a Linux host with no display. The remote command now shares
that default. A visible window is also what an anti-detect browser should
look like when a window is possible; asking for `--headless` remains one
flag.

Measured: seven new CLI tests, all red before the change, all green after;
the config path is redirected to a temporary directory so the suite never
reads a developer's real `~/.co`.

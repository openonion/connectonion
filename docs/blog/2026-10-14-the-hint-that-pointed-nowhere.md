---
description: We brought read-only Asana and Obsidian commands from F13DBREAD team's repo into co. Every Obsidian test passed; the test that failed was the one checking that our hints point at real commands.
tags: [CLI, Obsidian, Asana, Testing]
---

# The hint that pointed nowhere

An Obsidian vault is rarely one thing. Ours mix lecture notes with project
plans, and some people keep a diary in the same folder tree. So when we, team
F13DBREAD, gave `co` a way to read a vault, the first rule was that it reads
only what the person points at. `co obsidian vaults` reads Obsidian's own
registry and opens no notes. `notes`, `read` and `search` refuse to run
without `--folder`, and a symlink inside the vault is skipped rather than
followed. Asana got the same treatment: a token, five read-only commands,
and nothing that writes back.

We built both in our own repo, then moved them across to send upstream. The
Obsidian work had landed in two steps, vault discovery first and notes,
reading and search a day later. We copied the four new files over and ran
the tests. All of the Obsidian tests passed.

Six other tests failed, all in `test_cli_tips_name_real_commands.py`. That
test reads every "Next:" hint the CLI prints and checks that the command it
names exists. Our new code told people to run `co obsidian notes`, and `co`
had no such command. The files were new, but `cli/main.py`, where commands
are registered, was still the version from the first step. It knew only
about `vaults`. Every function worked and the commands were unreachable, and
the only thing in the suite that noticed was a test about what we say to the
user.

Asana had hit something similar a few days earlier. Registering its commands
imported the Asana client as soon as `co` started, and
`test_importing_connectonion_stays_cheap.py` caught every `co --version`
paying for it. The fix was to import the client the first time an Asana
command runs.

Neither failure was in the code we were worried about. They were in the
seams: where a feature is registered, and what starts loading when the CLI
starts. A unit test checks that a function does its job. These tests check
that the rest of the system can reach it and that we tell the truth about
it, and that is what you break when you move code from one repo to another.
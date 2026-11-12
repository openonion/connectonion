---
description: Blocking a requester with co trust only stopped new connections; an open socket kept sending messages. Now every frame re-reads the requester's trust, and co trust can target the lists the Host actually reads.
tags: [Trust, Host, CLI]
---

# Revoked means now

The previous change let a non-admin's Auto runs go ahead, and told them so: "the admin can revoke your access at any time." Then we tried to revoke someone.

We ran `co trust block <address>` while that person still had O Chat open. Their next message went through. So did the one after. The block was saved, and the Host would refuse them the next time they connected, but an authenticated WebSocket stayed authenticated until it dropped. "At any time" really meant "the next time their browser reconnects".

There was a second, quieter problem. For a `co ai` Host, the `co trust block <address>` line the Host printed for the operator usually did nothing at all. The Host reads its trust lists from `~/.co`. The CLI wrote to the `.co` folder of whatever project you ran it in (#2819). The command said it had blocked the address, and the Host never saw it.

## Checking on every frame

Trust used to be checked once, when the socket was admitted. Now the session re-reads the requester's trust before it dispatches every frame from an authenticated connection: a new message, an interjection, an approval or ask answer, a Work Room continuation. If the requester was blocked, removed or moved down a level, the Host sends "Your access to this agent was revoked by its admin.", closes the socket (code 1008 on a direct socket; a relay session is ended), and interrupts that requester's running turns. Other callers on the same Host are not touched.

Revocation takes effect on the requester's next frame. Anything a turn already did stays done, and the docs say so plainly instead of promising more.

## Pointing co trust at the right files

Every `co trust` subcommand (list, level, add, remove, block, unblock) now takes `--co-dir <dir>`, and `--global` (or `-g`) is shorthand for `~/.co`. Each one says which file it read or wrote. The operator notice the Host prints now includes the Host's own trust folder, shell-quoted: `co trust block <address> --co-dir <dir>`. One test copies that printed command and runs it from a different working directory, against a Host, and checks that the block lands.

## How we checked

`test_ws_session_revocation.py` drives a real session: block, remove and downgrade each end the socket on the next frame and stop that requester's turns, over direct sockets and through the relay. `test_trust_cli_targets.py` and `test_cli_and_host_trust_paths.py` cover the CLI targets. On the base branch, 23 of the new tests fail; with the change, they pass.

The lesson is about promises again. A sentence like "you can revoke access at any time" is a claim about the code. We wrote the sentence first and only then went and made it true.

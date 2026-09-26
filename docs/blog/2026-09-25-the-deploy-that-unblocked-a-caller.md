# The deploy that unblocked a caller

An agent on a server started getting spam from one address. The admin blocked
it from the agent's admin page, the spam stopped, and they went back to work.
That afternoon someone pushed a small prompt fix from their laptop with
`co deploy --to prod`. The next morning the spam was back.

Nobody had unblocked anything. The deploy had done it.

`co deploy --to` is an rsync of the project, and we had spent weeks deciding
which files under `.co/` belong to the author and which belong to the running
agent. Identity, logs, session history, the scheduler's state, the admins list
and `contacts.txt` are the server's. They are never deleted, and a local copy
is never sent over them. `whitelist.txt` and `blocklist.txt` ended up on the
other side of that line, with a comment saying they stay deployable because
the docs describe them as files the author writes.

That was true, but it was only half the story. The author writes them, and so
does the running agent. `block()` appends to the blocklist in the agent's own
`.co/`, so when the admin blocked that address, the server's file got one line
longer than the laptop's. The deploy did what an rsync does: it made the
server's file match the laptop's, and the new line was gone.

The audit reproduced it with real rsync. The server's blocklist
`0xold, 0xattacker_blocked_live` came back as `0xold`, and a whitelisted
partner disappeared along with it. The deploy printed a green tick.

The obvious fix was to exclude both files, the way `contacts.txt` is excluded.
But that has a problem of its own. On a first deploy the server has no
blocklist yet, and if we never send the author's, the new agent starts with
nobody blocked, which errs in the permissive direction. A file two parties
write needs a rule for each of them:

- The server's copy wins. The main sync no longer sends either list.
- A second, narrow rsync with `--ignore-existing` sends a local list only when
  the server has none, so the author's first blocklist still lands.
- The deploy says it kept the server's lists. An author who edited a list
  would otherwise think the edit went live.
- `--push-trust-lists` replaces the server's lists on purpose. That is the
  only way to remove an address, and the docs tell you to read the server's
  copy first.

The tests run the real `_sync_code` with rsync pointed at a directory standing
in for the server. They block a caller on the "server", deploy, and check that
the caller is still blocked. We'd learned from `host.yaml` going missing for a
release that checking the rsync argv tells you what we asked rsync to do, not
what landed on the server.

The lesson is about ownership. "Who writes this file?" had one answer when we
drew the line, and the running agent later became a second writer without
anyone moving the line.

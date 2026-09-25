# The laptop remembers too

A deployed agent keeps a record of every turn it has served, in
`.co/session_results.jsonl`. The Home page reads it, and a client that drops
its connection reads its answer back from it. On a busy agent it is weeks of
conversations with real callers.

It turned out that every `co deploy --to` could replace that record with a
copy from the author's laptop. Nobody had done anything unusual. They had run
the agent locally once, to try it, which is what everyone does before a deploy.
Running it locally wrote a laptop `session_results.jsonl`, and the next deploy
sent it up over the server's.

We found this while fixing the same bug for the scheduler's state file, and the
reason it survived so long is worth saying plainly. Deploy protects `.co/` on
the server, and we read "protected" as "left alone". Rsync reads it more
narrowly: a protected file is one `--delete` will not remove. It says nothing
about a file the laptop *has*. That file is sent, and the server's copy is
replaced. So the protection worked perfectly on a fresh checkout, which is
exactly the case our tests used, and failed on every real laptop.

Once you see it that way, the question is no longer "is session history
excluded" but "what else does the running agent write into `.co/` that a laptop
also has?" Walking the host code gave a longer list than we expected. The
replay store of signatures already used: a laptop copy would make every signed
request the server has seen acceptable again. The remote-browser leases, and
the browser runtime that holds its authkey. Files callers uploaded. And
`contacts.txt`, which is where a caller lands after paying or using an invite
code, so a stale laptop copy quietly un-onboards every customer since the last
deploy.

Each of those is now excluded, and each is pinned by a test that runs real
rsync between two directories, with a different file on each side, and checks
which one survived. That shape matters. Asserting the rsync command line would
have passed the whole time; the command was exactly what we wrote. Only looking
at the files afterwards tells you what a deploy did.

One file we deliberately left alone. `whitelist.txt` is written at runtime when
someone is promoted, but it is also documented as a file you write by hand and
deploy. Excluding it would silently stop an author's edits from reaching the
server, which is the same bug pointed the other way. That one needs a decision,
not a filter rule, so it still deploys.

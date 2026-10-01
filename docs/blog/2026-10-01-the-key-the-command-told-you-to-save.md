# The key the command told you to save

`co linear` started as a plan to wrap Linear's MCP server. Its tools cover
issues and comments, but they decide what comes back, and an agent reading a
standup does not need forty fields per issue. Linear's GraphQL API lets the
query name every field it wants, so the commands ask for six: id, title,
state, assignee, priority, updated. Lists print those six and `--json` returns
the same six.

We wrote the help pages before the code, and one rule in them created two
commands nobody had asked for. The rule was that an unknown name exits with
the valid names and the command that lists them. `--label bgu` has to answer
`Valid: Bug, auth` and `Next: co linear labels --team ENG`, and until then no
`labels` command existed. `--assignee` takes an email, so `users` came from
the same rule.

The setup line was settled early too: `co env set LINEAR_API_KEY lin_api_...
--secret`, so the key is not left in plain text. The first version then read
the key the usual way, from the environment that `keys.env` fills. Reading
`co env get` to see how secrets come back out showed the problem. A value
saved with `--secret` goes to an encrypted store, and the environment never
sees it. Someone who followed our own instruction exactly would have been
told, by the next command, that the key was not set. That command would have
named the same instruction again, and they would have gone round in that loop.
The key is now read in the order `co env get` uses: the shell, then the file,
then the encrypted store. A test saves a key through the store and checks
that it reaches the request header.

The other error we could check for real was a bad key. We sent one to Linear,
and its reply (HTTP 401, `authentication error`, a message for users that
ends in a full stop) became the fake that the unit test runs against. The
first output read "operation.. Make a new key", with two full stops in a row.

What has not run is a real workspace. Nobody on this change had a key. The
queries are checked against Linear's published schema and against a fake
that answers by root field, which proves the arguments are well-formed and
says nothing about Linear's ranking, paging or which errors it calls "not
found". An opt-in test creates one issue titled as a test, comments on it and
closes it. It is the step before a stable release.

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
The key is now read through `setting()`, the lookup `co env get` uses: the
shell, then the file, then the encrypted store. A test saves a key through the
store and checks that it reaches the request header.

The other error we could check for real was a bad key. We sent one to Linear,
and its reply (HTTP 401, `authentication error`, a message for users that
ends in a full stop) became the fake that the unit test runs against. The
first output read "operation.. Make a new key", with two full stops in a row.

The first run on a real workspace found the same loop one level down, in the
test itself. With the key exported, the opt-in test passed and created CON-5.
Then the key was moved to where our setup line puts it, the `--secret` store,
and the test skipped: it checked `os.environ` before running. It now asks
`setting()` too. Run again with nothing exported, it created CON-6, commented
on it and closed it in eleven seconds. The guess about how Linear words a
missing issue held: `issue CON-999` printed "No issue CON-999 in this
workspace" and the search tip. The same run printed "1 issues matching", so a
count of one is now singular.

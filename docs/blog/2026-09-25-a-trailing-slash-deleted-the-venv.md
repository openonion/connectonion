# A trailing slash deleted the venv

On 25 September a production agent redeployed with `co deploy` and came back
without its Python environment. The next step of the deploy, `pip install`,
failed, and the agent stayed down until someone rebuilt the environment by
hand.

The server kept its virtualenv outside the project tree, with
`/srv/<agent>/.venv` as a symlink to it. That is a common and sensible layout:
the environment survives a wiped project directory, and several releases can
share one. `co deploy` syncs the project with `rsync --delete`, and it had
always excluded `.venv/` so a local environment would never be copied over the
server's.

The slash is the bug. In rsync's filter rules a trailing slash means "match
directories only". A symlink is not a directory, so the rule did not match
it, and `--delete` removed the link because the local tree had nothing by
that name. On a server whose `.venv` was a real directory, the same rule
worked, which is why it held for so long.

The fix is to drop the slash, so the rule matches `.venv` whatever kind of
file it is. The test that pins it runs real rsync against a directory with a
symlinked `.venv` and checks that the link is still there afterwards — the
only kind of test that could have caught it, because the argument list itself
had looked right all along.

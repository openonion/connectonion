# The help page that moved the notebook

The rename to co rem came with a careful migration. The first `co rem` moves
`~/.co/wiki` to `~/.co/rem`, refuses if both exist, and replaces the daily
schedule so it runs `co rem sync`. It was tested, and it worked.

An hour after it merged, we asked the new command a harmless question:
`co rem projects --help`, to check a command name for the release notes. It
printed the help. Above the help it also said "Moved your notebook from
~/.co/wiki to ~/.co/rem" and "Your daily update now runs co rem sync". This was
the owner's real notebook. Their installed co was still 1.8.9, which has no
`co rem`, so the schedule it had just installed would fail at 17:00. And
1.8.9's `co wiki` would no longer find the notebook where it looked.

Nothing was lost; the folder had only moved. But the rule it broke is one every
co help page is held to: reading help writes no file. An agent reads help pages
to find its way. If reading one can move your data, no help page is safe to
read.

The cause was ordering. The migration ran in the group callback, and Click
calls the group callback before it prints a subcommand's help. By the time the
callback runs, the subcommand's arguments have already been consumed, so the
callback cannot even see the `--help`. The fix looks one step earlier, in the
group's own `invoke`, where the arguments are still visible. When they ask for
help, nothing is carried over. A test now asks three subcommands for help
against an old notebook and checks that it has not moved.

The lesson: a migration is a write, and every entry point is a way in. Test
the path you designed, and also the one a curious reader takes first:
`--help`.

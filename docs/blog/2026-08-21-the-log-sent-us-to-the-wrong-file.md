# The Log Sent Us to the Wrong File

An operator deployed an agent with `co deploy --to`, opened its journal, and
saw a reassuring line: the invite was set in `.env`. They went to
`/srv/<agent>`, looked for that file, and found nothing useful. The agent was
running and invitations worked, yet the one diagnostic meant to explain the
door had sent them to a file the service did not read.

The first instinct was to make the deployment copy its secrets into the
project directory. That would have made the log literally true, but it would
also have undone an important boundary. The project tree belongs to rsync and
`--delete`; the real deployment secrets live in a root-owned file at
`/etc/connectonion/<agent>.env`, outside that tree, with mode `0600`.

The complication was that Host is also used locally. It can describe an
environment variable, but normally it cannot know which file populated the
process environment. Hard-coding the server path in Host would make local
diagnostics wrong in the opposite direction.

The turn was to let the systemd unit state the fact it already knows. Alongside
its `EnvironmentFile`, the unit now supplies a non-secret marker naming that
file. Host uses the marker only in its diagnostic. A deployed agent says
`CO_INVITE_CODE` is in `/etc/connectonion/<agent>.env`; a local agent continues
to name its local `.env`. Missing-code guidance follows the same source.

The secret did not need to move. The diagnostic did. The reusable lesson is
that when one layer loads configuration for another, it should pass provenance
along with values—otherwise a perfectly secure storage design can still become
an operational trap.

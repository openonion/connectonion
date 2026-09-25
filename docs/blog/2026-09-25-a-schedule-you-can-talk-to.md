# A schedule you can talk to

Agents have been able to run work on their own clock for months. Put an entry
in `.co/schedule.yaml` and the hosted agent runs it every fifteen minutes, or
every Monday at nine. What you could not do was ask it anything. There was no
page in the docs, no command, and the only way to find out whether Monday's
report had run was to open the Home page or read a JSON file on the server.

`co schedule` is that missing half. `co schedule` on its own lists each entry
with when it runs next, when it last ran and how that went, including the
reason when a run failed and the session it produced. `co schedule check`
reads the file exactly as the scheduler does and names each entry it would
ignore, before you deploy a typo. `run`, `pause` and `resume` control one entry.

The design choice worth explaining is where those three write. Not
`schedule.yaml`: that file is deployed, so a pause written into it on the
server would be silently undone by the next `co deploy`. They write the
scheduler's own state file, which the running agent reads every minute. The
Home page reads the same file, so the command line and the page cannot
disagree about whether an entry is paused.

Checking that claim turned up the one real bug in this change. Deploy protects
`.co/` from deletion on the server, and we had assumed that covered the state
file. It does not: protection stops rsync deleting a server file, not
overwriting it with a local copy. Anyone who ran the agent on a laptop had a
local `schedule-state.json`, and every deploy sent it up, rewinding the
server's record of what had run. The file is now excluded from deploys, with a
test that runs real rsync to prove it.

Help was written to the standard we set in #1643. Every page says whether it
changes anything, carries an example that parses, and names its way back. Every
refusal exits 1 and names the next command, including the one for a missing
file, which prints an entry you can copy.

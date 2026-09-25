# The first run said the wrong next thing

A tester sat down with 1.8.8b7 as a brand-new user and did what the README
says: `co create my-agent`, `cd my-agent`, `python agent.py`. The agent came
up. The banner printed its address, its URL, and one yellow line:

    Invite: no one can onboard — CO_INVITE_CODE is not set. Add it to .env,
    or run `co init ./` to mint one.

They opened `.env`. `CO_INVITE_CODE` was there, a fresh code that `co create`
had generated a minute earlier. The banner was sending them to fix a line that
was already fixed. When they tried to connect with that code, the agent turned
them away, because in the running process the variable really was unset.

Nothing was broken in the usual sense. Each piece did what its author meant.
`co create` wrote the code into the project's `.env`, the most sensible place
for it. The environment loader reads `~/.co/keys.env` and never the current
directory, and that is deliberate: a `co` command should not quietly switch
accounts because someone typed it inside a folder that happened to hold a
`.env`. Both rules are right. Together they meant the one file holding the
agent's invite code was the one file the agent never read.

The rest of the tester's notes had the same shape. When the port was taken,
the banner printed `http://localhost:8000` first and uvicorn's raw
`[Errno 48]` came after it. Opening that URL gave a 404. `co doctor` finished
with "Run 'co auth' if you need to authenticate" right under its own
"✓ Valid credentials". The `co` on their PATH was three previews old, and
doctor said nothing about it. `co benchmark list` printed "the smallest valid
one", a two-case file that `co benchmark check` then rejected for having fewer
than five cases. The `.env` showed the agent's email twice, with two different
lengths. `co eval run` reported "forbidden again" for a case that had passed
the run before.

None of these is a crash. Every one is a sentence that was true when someone
wrote it, or true in the situation they had in mind, and false for the person
reading it now. "Forbidden again" was meant for a regression, but the list
behind it can only hold outcomes the previous run did not have. The email in
the comment was a guess written before `co auth` ran, and the backend then
assigned a different one. The two-case example had a note under it about
"three more", but the heading still called the file valid, and people believe
headings.

The fixes are small, and they share a rule: a message has to be true at the
moment it is printed. `host()` now reads the project's `.env`, ranked below
anything the process already set and above `~/.co/keys.env`. `co` commands
still ignore the current directory, so the old rule holds where it was meant
to. The port is checked before the banner goes out, and the message names
`port:` in `.co/host.yaml` and `AGENT_PORT`. `/` now answers with where
`/docs` and `/info` live. Doctor only suggests `co auth` when you are not
authenticated, names a `co` on PATH that reports another version, and groups
forty identical skill warnings into one row. The benchmark example has five
cases, and a test copies it into a file and runs `check` on it. The regression
label now says "newly forbidden". The `.env` comment now points at
`AGENT_EMAIL` instead of guessing an address.

Each of these went through review because the reviewer read the message in
the situation the author pictured. The tester read them the way a new user
does, top to bottom, trying each thing they were told. A message is an
instruction, so the useful test is to follow it and see whether it works.

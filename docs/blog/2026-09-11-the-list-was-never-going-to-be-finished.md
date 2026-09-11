# The list was never going to be finished

Yesterday we fixed a policy that refused `head`. An unattended job had been
running seven times a day, and on the sixteenth iteration it reached
`co browser ... get_text | head -40` and stopped. The policy allowed eleven
commands — `pytest`, `ruff`, `cargo`, `make` and seven more — and everything
else fell through to "ask", which with nobody watching is "no".

The fix added the read-only commands: `head`, `tail`, `grep`, `wc`, `ls`,
`sort`, `cut`, `jq`, thirty-odd names. Tests went green. The job ran.

Then the maintainer asked a question that undid it. *If the default were
allow, what would the list be for?*

Nothing. That is the whole answer. The two designs are alternatives, not
layers: either you enumerate what may run, or you enumerate what may not.
We had been asked for the second and had built the first, and the first is
the one that cannot be finished. Every list of safe command names is a list
somebody has to extend for every tool anyone ever installs, and the way you
find out it needs extending is that a job dies at two in the morning.

## What we went looking at

Before changing anything we looked at what the tools on this machine actually
do. Claude Code's settings file has an allow list, an ask list and a deny list,
and all three are empty. Codex's config has no command list at all; it has a
reviewer. Neither of them decides anything by command name.

They constrain by boundary. Can this touch that directory. Does it leave the
sandbox. A name is not a capability — which is obvious once said, and was not
obvious while we were adding `basename` to a set.

## What the list was not buying

The argument for enumerating is that you know what each name does. We had a
careful comment explaining why `sed` and `awk` were deliberately excluded:
they take a *program*, and `awk 'BEGIN{system("rm -rf /")}'` reads like an
inspection and is arbitrary execution. Correct, and worth the paragraph.

`make` was on the allow list. A Makefile recipe is arbitrary execution.
`cargo build` runs `build.rs`. `npm test` runs whatever `package.json` says.
The policy was refusing `awk` and running three things that do the same job
with a config file. It was not holding a line; it was holding an alphabet.

The argument was right and it was pointed at the wrong list. Executing
unreadable input *is* the thing to refuse — just not by asking whether the
command's name is on a roster of thirty.

## Flipping it, and what fell out

The change is small: an ordinary command runs. Everything that was denied
before is still denied, and three rules had to be written down that the list
had been enforcing by omission.

The first was the one that mattered. With the default flipped,
`bash << 'EOF' rm -rf / EOF` was allowed — `bash` is just a command name, and
the heredoc body is not something any rule here can read. So: a command whose
argument is a program asks. That is `bash`, `sh`, `python`, `node`, `ruby`,
`perl`, `awk`, `sed`, and `uv run python -c`, which is `python -c` wearing a
coat. The careful paragraph about `awk` survives, generalised.

The second we found the same way. `co email send --to ... hi` was allowed.
Nothing about that command is dangerous to this machine; it is dangerous to
the relationship with whoever receives it. An unattended agent must not be the
one deciding to be seen, so anything whose subcommand is `send`, `reply`,
`post`, `publish`, `deploy`, `push`, `transfer` or `pay` asks. Local damage and
outward visibility are different axes, and the old list had conflated them by
accident — `co email send` was refused for being unrecognised, not for being
an email.

The third was `tee out.txt` and `find . -delete`, which write and delete
through their arguments rather than through a redirect, so the redirect rule
never saw them. They now get the same workspace check the write tool gets.

Three rules, and the shape of them is the point: they describe categories of
consequence, not names of programs. The set of dangerous *verbs* is small and
changes slowly. The set of safe *commands* is unbounded and changes every time
someone runs `brew install`.

## The test that fired

The job test from yesterday pinned exactly which steps needed an operator
grant, with a docstring promising it would fail loudly if a policy change made
a pipe filter need a grant again. It failed loudly in the other direction:
the two steps that had needed a grant — making a directory, and running the
binary the job had just built — needed nothing.

Needing a standing `Bash(co *)` permission to run `mkdir` was the shape of the
problem, not a boundary anyone would defend. The test now asserts the job needs
no grant at all, which is a better thing to pin.

Two bugs in one file, two days apart, and the second one only visible because
the first fix was wrong in a way that worked.

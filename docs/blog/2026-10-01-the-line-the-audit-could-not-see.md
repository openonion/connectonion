# The line the audit could not see

Yesterday `co audit co` passed 301 of 302 pages on the new look rule, and we
wrote that a gate only judges what it runs. This morning the owner ran 1.9.0a5
on his real machine and showed us how right that was. Every `co` command in
his terminal opened with the same line two or three times:

    [env] /Users/…/.co/keys.env
    [env] /Users/…/.co/keys.env

The audit had never printed it once. Its "terminal" run set `FORCE_COLOR=1`
and captured the output through pipes. Colour was on, but nothing was a
terminal. `environment.py` printed `[env]` only when stderr was a terminal,
so the one line every person saw first was the one line the audit could never
see. It printed more than once because loading runs when the package is
imported and again when a command selects its file.

That was not the only gap. `co whatsapp check` showed a path in two shades of
magenta. `co --version` coloured `1.9` in bold cyan and left `.0a5` plain.
Rich highlights anything that looks like a number, a date or a path, unless
the console is made with `highlight=False`. The rule compared words with the
colour stripped, so a word coloured in pieces looked perfect to it. `co status`
still had a cyan panel titled "📊 Account Status" and ended on a 💡 tip.
Nothing checked for emoji or for a missing Next line, so both passed.

The one failure the audit did find was a real bug in a surprising place.
`co doctor` asks the `co` on PATH for its version. In a terminal that child
answered in colour, `co \x1b[1;36m1.9\x1b[0m.0a5`, which never equals
`1.9.0a5`. So doctor told a person at a terminal that their `co` was a
different install, while a pipe said the same install was fine.

The fixes were small. `[env]` now prints only under `CO_DEBUG_ENV=1`, once.
Doctor asks for the version with `NO_COLOR`. The consoles no longer
auto-highlight, and `co status` ends on a Next line. The harder part was the
rule. The terminal run now gives stdout and stderr each their own
pseudo-terminal, so a program that checks `isatty()` behaves as it would for a
person. The rule then looks for a line repeated at the top, a word whose
letters change colour partway through, an emoji in a panel title, and a status
command with no Next line.

The first draft of the pieces check failed sixteen help pages, and it was
wrong. Typer colours `<name>` inside `.co/skills/<name>/SKILL.md` on purpose,
because that is a metavar. So the check now reads only what a command prints
as its result. Help pages stay with Typer's own rules.

The lesson is the same as yesterday's, one level deeper. Turning colour on is
not the same as being a terminal. If a program can tell the difference, the
audit has to run it where it can't.

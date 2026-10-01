# The folder nothing imported

The first thing anyone sees on github.com/openonion/connectonion is a list of
folders, before the README. Ours had `subagents/` at the top level, next to
`connectonion/`. It looked like a second package, which it was meant to be
once: a prototype of the subagent system, with an `__init__.py`, a loader, a
factory and two definitions, `explore.md` and `plan.md`.

Then the subagent system was built inside the package instead. It is
`connectonion/useful_plugins/subagents.py`, and its built-in definitions live
in `useful_plugins/builtin_agents/`. The root folder stayed behind. Nothing
imports it, the wheel and the sdist leave it out, and no test touches it. Its
only commits since March were search-and-replace sweeps for the default model.
A dead folder with live-looking contents still costs something: an agent or a
contributor reading the tree reasonably assumes it matters, and edits the copy
that nothing runs.

Checking "nothing uses it" meant checking every way it could be used: imports,
packaging, tests, scripts and CI. Each came back empty, and the folder is gone.
The same check removed `output/`, two marketing images nothing referenced, and
a strategy draft that belonged in a private notebook rather than at the root
of a public repository. The three design notes that still describe the old
folder now say so at the top, and point to where subagents actually live.

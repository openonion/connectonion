---
name: rem-init
description: Run REM initialization and check useful, cited findings about people, projects, organizations and installed skills.
---

# Initialize REM

Use the notebook root supplied by the task in every command. Read [CLI.md](CLI.md)
for source CLI syntax and recovery; resolve it beside this Skill. `co rem --help`
and `co rem init --help` are the command contract. Do not recreate the command's
mapping or investigation logic in a long prompt.

Run `co rem --root '<absolute-notebook-root>' init --days 90`. It maps connected
sources, saves their private evidence, then uses the configured runner to write
the owner's page and investigate eligible people, queued projects, related
organizations and installed skills, recent first. It announces the model-work
estimate. The configured weekly investigation budget (35% by default) is a
**target**, not a stopping point. Finish the selected investigation even when
it takes more, unless the configured
weekly safety floor, runner failure, or interruption stops it. Do not pass
`--no-investigate` for a normal first run.

Read the result and `co rem --root '<absolute-notebook-root>' logs`. Check that
the owner's page and selected pages have useful findings and citations, not
only empty frames. Follow the returned `Next:` command and retry failed pages
with `co rem investigate` or `co rem projects write`. Report source gaps and
unfinished pages. Never copy private source bodies into a public document.

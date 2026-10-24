---
title: Initialization should not depend on the first command
date: 2026-10-24
tags: [CLI, Onboarding, Skills]
---

# Initialization should not depend on the first command

The request sounded like a missing feature: could initialization link the skills
too? Plain `co init` already did. Someone who started with `co init ./` or
`co create` received an identity and project files, but missed the same coding
agent integration. An existing private key also sent `co setup` past its own
bootstrap. The implementation remembered that setup had once started rather
than checking whether it had finished.

We considered adding another instruction to the getting-started guide: run
`co skills link` after creating a project. That would leave every caller carrying
knowledge about which initialization command they had used. Calling a separate
installed `co init` from setup was already fragile: PATH could select an older
version, and a module could retain paths from an earlier invocation.

The candidate for [issue #2675](https://github.com/openonion/connectonion/issues/2675)
shares the local preparation across all four entry points. The identity remains
the machine's; a missing local profile is created; installed coding agents get
the bundled skills and generated command index. Every run checks the pieces
again. User skill directories, profile edits and instruction text outside the
generated block survive. Project `--force` does not become permission to replace
someone's own skill library.

Creating a default profile exposed a second problem. A later
`co setup --name ... --bio ...` must actually customize it. Explicit fields now
update those fields while preserving other profile metadata. Full profile
replacement keeps its separate backup behavior. Discovery, copying, manifests
and runtime skill lookup also resolve the current global directory together;
preparing a library in one place is useless if the agent searches another.

Ten filesystem regressions failed against the original implementation, covering
the entry points, selected roots, missing environment file and rerun behavior.
The first shared implementation passed those cases. Wider checks caught a
runtime lookup path still pointing at the default library. Independent review
then caught manual skill listings lost during a profile refresh, healthy
personal links being replaced, and an announcement preview selecting the wrong
root. The corrected candidate merges metadata, keeps healthy personal links,
and carries the selected root through both runtime loaders and publication
previews. Invalid bundled YAML descriptions are now quoted, so a fresh imported
library does not report those shipped skills as broken. This is a local
candidate under review, not a claim that a new package is published or that
every connected service has been tested.

The boundary is local preparation. Importing a person's separate library remains
an explicit setup operation. Account login, browser installation, publication
and recurring work keep their own commands. We would revisit that boundary if
one of those becomes a necessary prerequisite for the first useful local action.
For now, a user should be able to choose the right starting command and receive
the same foundation, then rerun it to repair what is missing.

# No Dialog Is Not Approval

A headless `co ai` run was asked to write one canary outside its project. It
started in Auto, had no browser or other approval channel, and wrote the file
without asking. The same operation in O Chat was correctly classified as an
outside-workspace write and denied. The permission mode had one name but two
boundaries.

The split came from an old shortcut. The deterministic Auto policy only ran
when `agent.io` existed, because its `ask` decisions were designed to open a
dialog. Without IO, the older approval hook simply returned. That kept local
library calls noninteractive, but it also meant that one-shot `co ai` skipped
the path and effect checks that made Auto safe.

Treating every headless call as denied would have fixed the escape by making
Auto unusable. Workspace reads, reversible workspace edits, and focused
verification are the operations Auto is meant to perform unattended. The
correct boundary is the policy decision itself: run the same classifier with
or without a UI, preserve its allow and deny results, and turn only `ask` into
deny when nobody can answer.

Full access remains separate. An operator can explicitly select its bounded
turn grant for trusted unattended work, and protected control files still
cannot be rewritten. A missing dialog is now the absence of consent, not an
implicit grant.

The regression covers both sides of the boundary: headless Auto allows an
inside-workspace edit, rejects outside reads and writes plus unknown tools,
and bounded Full access retains its explicit bypass. Permission policy should
not depend on whether the product happened to render a button.

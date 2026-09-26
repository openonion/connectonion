# A subscription has to remember what it installed

The first `co sub sync` looked complete. It fetched a publisher's profile,
copied each public `SKILL.md` into a local mirror, and linked those directories
into installed coding agents. The trouble appeared on the second sync. If the
publisher withdrew a skill, the mirror still contained its old directory. The
agent could continue following instructions that the publisher no longer
published. A renamed publisher could leave a second bundle beside the first.

There was also a more immediate cost to treating a matching name as proof of
ownership. A subscriber might already have a hand-written skill directory at
`~/.codex/skills/<alias>-<skill>`. The old install path could remove it while
making room for a symlink. Unsubscribing used the same broad name match. The
local notes in that directory had no relationship to the publisher, but the
command could still delete them.

The fix treats a subscription as a relationship with a pinned local alias and
an owned set of installations. A refreshed bundle is built in a temporary
directory from a verified publisher signature, then swapped into place.
Fan-out removes its previous links and marked copies before installing the new
set. A same-name real directory, ordinary file, or link to another target is
left in place and reported as a conflict. A missing public body stays missing;
it cannot survive as an old installed instruction.

The same boundary exposed another gap: a skill can depend on a script or
reference file next to `SKILL.md`. Sending only the Markdown body made the
subscription appear installed while the skill was unusable. Publisher and
relay now carry bounded companion files inside the signed profile. The
subscriber verifies the reconstructed profile before writing any of them.
The relay must deploy that support before the SDK preview is published, since
an older relay would omit bytes the signature covers.

We exercised the withdrawal, rename, collision, staging failure, tampered
file, and publish-to-mirror paths in focused tests. The command now reports
listed, mirrored, and installed counts separately, so someone can see whether
a published name actually reached their agent.

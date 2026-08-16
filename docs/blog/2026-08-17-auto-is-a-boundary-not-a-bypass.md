# Auto Is a Boundary, Not a Bypass

The stable and preview lines had slowly taught two different lessons about
automation. A user could see “Auto” in one place, “Default” in another, and a
legacy session field in a third. The dangerous interpretation was that any one
of those labels meant the browser had been granted permission to do whatever the
agent next proposed.

The merge makes the boundary explicit. A Host owns the durable permission
profile, starts every browser session in Read only, and advertises only the
profiles it is prepared to enforce. The workspace Auto profile is not a
universal approval switch: it permits a small deterministic class of local,
reversible workspace work. It still asks for unclear or broader actions, and it
denies deletion, credentials, external control, and writes outside the approved
workspace.

That distinction mattered during a rolling deployment. An older client can
round-trip a session snapshot, but it cannot choose a newer server-owned
authorization default. The Host strips stale policy markers before merging a
client session and re-applies the durable owner and permission state atomically.
Planning remains a local workflow state; it never changes what a Host will
approve.

We measured the boundary rather than trusting its label. The policy tests cover
allowed reads and reversible edits, approvals for ambiguous work, and denials
for destructive or sensitive actions. The Host route tests cover the
owner-preserving transaction. The full non-real-API suite then ran 7,070 tests;
the separate preview-document contract also passed against the clean published
preview documentation worktree.

This is deliberately not the promised model-reviewed Auto mode. That later
feature needs an explicit reviewer and acceptance evidence. Until then, “Auto”
means a Host-enforced workspace boundary that can be explained, tested, and
revoked — not a nicer name for unrestricted autonomy.

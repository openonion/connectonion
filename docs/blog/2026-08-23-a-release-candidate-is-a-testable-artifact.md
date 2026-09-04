# A Release Candidate Is a Testable Artifact

Beta 10 passed the longest 1.7 browser run we had performed. A fresh public
wheel started a real `co ai` Host, accepted an invocation-scoped invite, drove
O Chat through permission changes, built C and Rust projects, delegated another
C project to native Codex, stopped and restarted the Host, reconnected without
resending the prompt, and left fourteen screenshots for review.

Then the screenshot review found that the Work Room could still lose the thing
that made it a client: its input box. The backend accounting review found a
different boundary where measured cache usage could be preserved by the
provider and then flattened before it reached the final outcome. Beta 10 was
real evidence, but it was evidence for the bytes that existed before those
fixes.

We had three tempting choices. We could keep making Betas even though the
feature train was frozen. We could call the merged fixes stable because their
unit tests passed. Or we could use a release candidate for what it is actually
good at: giving every layer one immutable public version to test together.

RC1 takes the third path. Core, the React reader, and O Chat receive exact
candidate identities. The Work Room keeps attributed user/provider messages
and a provider-targeted composer in every lifecycle state; a blocked composer
stays visible and says why. Managed usage keeps its normalized cache-read,
cache-write, uncached-input, provider/model, pricing-tier, and server-cost
fields. Neither statement counts as accepted merely because the code merged.

The gate now asks the candidate to do more than render reassuring text. A real
installed `co ai` must drive the real `co browser` command through a catalog
search and an actual attachment download. A strict report and fixture-side
request log prove both operations independently of the model's prose. The same
journey builds C, C++, and Rust work, invokes native Codex, switches modes,
stops, restarts, and reconnects. It preserves sanitized logs, workspace checks,
and hash-addressed desktop, tablet, and mobile screenshots.

The UI review is a separate gate because green automation cannot say whether a
new user understands the page. Every frame is checked for a recognizable remote
coding client, visible conversation and input, distinct thinking and active
work, readable tool summaries, honest blocked states, and responsive layout.
An unresolved Critical or High finding makes the evidence bundle ineligible.

This also explains why RC1 can exist while stable blockers remain. The missing
Anthropic live authorization and the private backend repository's stopped
GitHub Actions budget still prevent stable promotion. They do not make an
immutable candidate less useful; they make one necessary. Once those gates are
restored, they can test the same bytes everyone else installed instead of a
moving branch.

The version-only checks pass 38 release and cross-repository assertions, the
React candidate passes 141 tests, and the O Chat gate passes 183 unit tests plus
its browser suite. Those numbers justify creating a candidate, not promoting
one. Stable 1.7 is earned only if the exact RC survives the remaining provider,
backend, platform, upgrade, rollback, provenance, security, and UI window
without another code change.

An RC is therefore not a victory lap between beta and stable. It is a checksum
for a claim the whole system still has to prove.

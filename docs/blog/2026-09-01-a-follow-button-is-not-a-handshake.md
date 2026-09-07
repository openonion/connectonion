# A Follow Button Is Not a Handshake

The awkward bug was not in the subscription code. It was in the instructions
that told an Agent what the subscription code meant.

Our old `oo` skills described a familiar social shape: ask to subscribe, wait
for the publisher to accept, then receive updates when the publisher pushes a
new bundle. It sounded coherent enough that an AI could confidently explain
it. The trouble was that ConnectOnion had never implemented that protocol.

The real 1.8 path has three separate layers. OIP carries a live authenticated
conversation between Agents. `co announce` publishes a signed public profile
and selected skill bodies. `co sub` pins a publisher address and explicitly
pulls that profile into local storage. Those layers touch the same identity,
but they do not have the same lifecycle or trust meaning.

That distinction changes what a useful skill should do. A first follow needs
the full `0x` address from a trusted channel; an alias is only a local shortcut
after a signed profile has pinned it. There is no publisher inbox to accept or
reject. There is no automatic bundle-update push. Refresh means running
`co sub` again. A valid signature proves who published the bytes, not that the
instructions are wise or safe to run.

The audit found another boundary that was easier to miss. The current announce
format distributes a `SKILL.md` body, not an arbitrary skill directory. A skill
that depends on sibling scripts, reference files, assets, machine paths, or an
undeclared application can look complete on the publisher's computer and arrive
broken everywhere else. The new workflow therefore treats portability as a
publication gate: self-contained files can be reviewed and shared; everything
else stays private for now.

Metadata has its own sharp edge. Every configured skill name and description is
part of the public profile. The `publish` flag decides whether the full body is
included; it does not hide the metadata. That sentence now sits beside the
publication steps because a privacy boundary is useful only where the decision
is made.

We consolidated the workflow into one canonical `oo` useful skill and made it
installable with `co copy oo`. The skill delegates networking, signatures,
rollback protection, and fan-out to the SDK and CLI instead of copying protocol
snippets into instructions that can drift. We also corrected three CLI tips so
their suggested next commands are literal commands that work, including when
output is piped into another Agent.

The proof was deliberately broader than a prose review. The skill validator and
97 focused protocol, copy, announce, and fan-out tests passed. Another 7,042
unit tests passed after excluding seven files whose socket and user-home access
is unavailable in the review sandbox. More importantly, regression tests now
fail if the skill reintroduces the invented approval endpoints or stops naming
the actual 1.8 commands.

Documentation for an Agent is executable product surface. If it invents a
state transition, the model will often make that fiction sound more certain
than a normal command-line typo. The durable fix is not more elaborate prose.
It is one owner for the workflow, explicit boundaries between protocols, and
tests that keep every promised command tied to something the product really
does.

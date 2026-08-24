# Arm the deadline before the tool returns

A coding provider can finish perfectly and still leave its user stranded.

The public `1.7.0rc9` acceptance run asked Claude Code to build a bounded C11
stack. Claude returned successfully after 132.8 seconds. The harness compiled
and ran the project independently. Then the parent conversation stopped moving:
no final answer, no approval, and no composer.

RC9 already contained a 90-second deadline for the model call that settles a
native provider result. The small tests passed. The real Work Room did not see
that deadline. The mistake was temporal: provider identity was discovered only
after the hosted tool path returned. Plugins and event observers are allowed to
normalize the in-memory call while that path runs, so a safety property derived
after execution was weaker than the durable fact recorded by execution itself.

We considered putting a larger timeout around the release harness. That would
only make the test stop sooner; it would not restore the user's conversation.
We also considered relying on the original call object and adding more logging.
That would make the same ordering assumption easier to diagnose, not correct.

The parent deadline is now armed from the model decision before provider work
starts. At the next iteration, Core also checks the durable trace for a completed
`codex` or `claude_code` tool result since the latest model call. Either fact is
enough to bound settlement. The trace records the applied timeout so a hosted
acceptance run can prove the safety boundary was active, rather than infer it
from elapsed wall time.

The first installed-wheel smoke refined the boundary again. Claude returned,
the parent quickly called `glob`, then the following model response requested
another tool and stalled before that tool reached a visible execution or
approval state. The LLM calls were fast; timing only those calls could never
close the turn. Post-provider settlement is therefore terminal-only. The parent
may summarize the recorded provider result, but it cannot open a new outer tool
chain. One attempted tool batch is discarded with a final-only reminder; a
second attempt fails explicitly so the Host can publish a terminal outcome and
restore the composer.

The tradeoff is deliberate: every remaining model call in that provider turn is
bounded, including the single grounded recovery attempt. A very slow but healthy
settlement may be abandoned. That is preferable to an indefinitely unusable
Work Room, and the provider result remains recorded for the retry.

Unit coverage now changes the observed ToolCall name after execution and proves
the already-armed deadline still fires. It also proves the durable trace can
re-arm the boundary while an unrelated later tool batch cannot inherit an old
provider deadline. The release claim still depends on the harder evidence: a
new public candidate must repeat the complete browser, compiler, provider,
permission, Stop, reconnect, and responsive Work Room journey.

We would revisit the 90-second value if production measurements show legitimate
settlement calls routinely need longer. We would not revisit the ordering rule:
a deadline that protects the result of a tool must exist before that result can
cross a mutable hosted path.

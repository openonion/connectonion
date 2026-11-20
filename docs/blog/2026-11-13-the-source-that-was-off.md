# The source that was off still stopped the notebook

A fresh REM notebook should be able to tell you what it intends to read before
you connect another service. In the unmerged Granola draft, that question alone
could stop onboarding. Granola was disabled, yet building the consent summary
raised `UnboundLocalError`. A notebook meant only for coding sessions could
fail without its owner ever choosing Granola.

The report in [issue #2882](https://github.com/openonion/connectonion/issues/2882)
was deliberately narrower than a production incident. A reviewer isolated the
exact summary function from [draft #2881](https://github.com/openonion/connectonion/pull/2881)
and supplied its dependencies in memory. No real notebook, source API, model,
or scheduler was needed to reproduce the exception. It was a finding against
an unmerged draft, not evidence of a bug in a released package.

## The useful default exposed the missing path

The draft added Granola to every notebook's source list with `enabled: false`.
That made an optional integration visible without subscribing the owner to it.
The summary already knew how to describe a disabled source: mark it
`unsubscribed` and move on.

Granola's scope display had a different assumption. Its local `selection`
variable was assigned only in the enabled-Granola branch. The earlier disabled
branch skipped that assignment, but the output block still tried to include
`selection`. Turning the integration off avoided the read path and broke the
description path instead. The same summary is used for consent fingerprints
and init authorization, so the missing value reached beyond one display.

The existing Granola tests helped explain how this escaped: they connected or
enabled the source before approving it. The configured path worked. The
ordinary notebook that had never connected Granola was the missing case.

## Empty was only half the answer

Giving every disabled source an empty selection would stop the crash, but it
would lose information for a notebook that had configured Granola and later
turned it off. Its saved scope still matters when explaining what the source
is configured to read. Disabled and never configured are different histories,
even when neither permits a read now.

The fix derives the scope directly from the current Granola source when
building its output entry, using an empty mapping only when no selection is
saved. The existing state decisions stay in their original order. A disabled
source remains `unsubscribed`; an enabled but unconsented source keeps its
configured selection and remains awaiting approval. None of that requires a
Granola key or a request to Granola.

Computing the scope earlier in the loop could also have worked. Keeping the
lookup next to the field it populates avoids a separate local value whose
availability depends on another branch. The change is small because the
read, approval, and scheduling boundaries already existed; they did not need
to move to repair the description.

## The default became the regression test

Before changing the function, seven regression cases were added around the
service boundary. Six failed with the reported exception: the default summary
and fingerprint, two previously configured disabled states, init authorization,
and declined startup. The enabled-but-unconsented case already passed and
provided a behavior to preserve.

After the fix, all seven passed. The focused REM/Granola suite, including
REM init, passed 452 cases on macOS with CPython 3.12.9. The tests used isolated
configuration and synthetic data. The new consent tests reject attempts to
construct a Granola client, require saved credentials, read imported summary
rows, or invoke the model runner; declined startup also leaves the fake
scheduler uninstalled. These are service-level checks, not a real API or full
interactive CLI integration run.

This fix belongs to the Granola draft and makes no package-release claim. The
lesson applies to any optional source: turning a connector off must leave it
possible to describe its state. That description is part of the consent
boundary, and the default-disabled path needs its own test before the feature
is integrated.

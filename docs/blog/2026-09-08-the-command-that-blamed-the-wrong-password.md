# The command that blamed the wrong password

On 27 August, four emails were queued in Outlook for the next morning. An hour
later the wording had to change. `co outlook send --at` had confirmed each one
with a timestamp and a recipient, and nothing else. The way to take them back
was found by opening `useful_tools/outlook.py` and reading what `get_scheduled`
did, then guessing that `cancel` existed. It did. The CLI had simply never said
so.

The same afternoon, `co outlook inbox` said the Microsoft session had expired
and told the user to run `co auth microsoft`. They did, twice, through the
browser consent flow, and got the same error. The token was fine. A direct
request to Graph with the stored token returned 200. What had died was the
OpenOnion key that the refresh broker checks first, and the 401 from our own
backend had been reported as a Microsoft expiry. Later the same key was absent
from the environment altogether, and that surfaced as "Microsoft Mail permission
missing". Three causes, one wrong instruction.

The third complaint was quieter and worse. A threaded reply to an external
founder needed a colleague copied in. `co outlook reply` had no `--cc`, so the
reply went out as a fresh `send` with "RE:" in the subject. On the founder's
side it arrived as a new conversation with no history, the shape of a mass
mail, and it had to be re-sent by hand.

None of these were failures of the Graph integration. Every request that mattered
had worked. They were failures of what the command said afterwards, and the
lesson we kept relearning is that an error message naming the wrong command
costs more than no message at all: the user does the wrong thing confidently
and then trusts the tool less.

So the fix was mostly about the last line of output. A scheduled send now ends
with the cancel path, and the `--at` help says it too. The credential layer
that failed is the one that gets named: `co auth` when the OpenOnion key is
missing or rejected, `co auth microsoft` when Microsoft revoked the grant or the
saved record has no refresh token, and the scope by name when the token predates
it. `reply` gained `--cc` and `--bcc`, set on Graph's reply action so the
message stays in its thread. And because the Microsoft calendar tool had
existed for months with no way to reach it from a terminal, `co outlook
calendar` now mirrors `co gcalendar` leaf for leaf, under `co outlook` because
Outlook is one product with three panes, not four.

Writing the tips was not the hard part. Testing that they work was. We gave a
fresh model only the output of each command and a goal, and asked for one shell
command back. Twenty-five of twenty-six rows passed on the first run. The one
that failed was an invalid `--at` value: the error explained the accepted
formats but named no command, and the model answered with a shell history
substitution that would have done nothing. A human reading that message would
have called it clear. The tip test is worth running precisely because it does
not read like a human.

The regression tests were run against the public 1.8.3 wheel before the fix.
Thirteen of fifteen failed there, which is the evidence that they test the
complaint and not the implementation. The two that passed cover the token
reuse from #1312, which 1.8.3 had already fixed; they stay as guards. No live
mailbox was used for any of this, and that is what the beta is for.

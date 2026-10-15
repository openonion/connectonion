# The model that was not a Flash

*2026-10-15*

"Gemini 4 is out — check the price, can we move the default from 3.8?"

The honest answer took one call to find and was not the one anyone expected.
`ListModels` on our own key returns exactly one Gemini 4 model, `gemini-4-argon`,
and no `gemini-4-flash`. There is no Flash in Gemini 4 yet. So the question
"should the default move up a generation" was really "should the default move
from a Flash price to a Pro price", which is a different question with a
different answer: $0.75 input and $3.75 output per million becomes $2.00 and
$10.00. That is 2.7x on the model that carries nearly all our traffic and that
new accounts spend their free credits on.

Easy enough — make it selectable, leave the default alone. Then the pricing page
mentioned, in a column most readers would skim, that Argon doubles to $4.00 and
$20.00 on December 1. Six weeks away.

Our pricing records already carried an `effective_until` date. They had carried
one for months. Nothing read it. `get_model_pricing` returned the first record
for a model whatever the date, so the field was documentation that looked like
enforcement — the comfortable kind of bug, where the thing you would check is
present and correct and inert. On December 1 nothing would have failed. No alert,
no error, no 422. We would simply have billed half of what Google charged us, on
the most expensive model we offer, for as long as nobody happened to look.

That had already been written up in an issue about the Flash rates changing on
January 1. It had six weeks longer to be found. Argon took the deadline and moved
it, which is the only reason it got fixed now: a stale rate on a model nobody
uses costs nothing, and a stale rate on a model we just advertised costs
whatever people use it for.

So a pricing record can now name its successor, and the lookup returns the window
containing the request date. A record without a successor answers exactly as
before — the fix is narrow on purpose, because re-pricing every model in the
table was not what anyone asked for, and a change that quietly moved the default
model's rate would be a worse bug than the one being fixed.

What we measured, rather than assumed: Argon answers, does tool calls, does
structured output, and takes `reasoning_effort` low, medium and high. At `high`
the response came back with 5 completion tokens and 152 total — the thinking
tokens are outside `completion_tokens` entirely, which would have under-billed
reasoning if the proxy had trusted that field. It derives output from
`total - prompt` instead, and has since a Flash model taught it the same lesson.

One row did fight back. Every Google model in our table has a cached-input rate
at 25% of input, and a test asserts it; Argon's is 5%. The test failed on the
first run, which is exactly what it is for. It would have been one line to widen
the rule to "or whatever the vendor says". Argon is in the published-exceptions
list instead, with its own pinned numbers, so the next model with a strange
cached rate fails the same way rather than sliding through a rule that has
learned to accept anything.

`co/gemini-4-argon` works today. It is not the default, and the row in our table
says to update it on December 1.

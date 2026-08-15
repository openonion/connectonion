# The cache was invisible

*2026-08-15*

The model provider said a request had reused thousands of tokens. Our bill and
our terminal said nothing about it.

That disagreement made every repeated agent turn look more expensive than it
really was. It also made the cache impossible to reason about: a developer
could send the same large prefix twice, see no cached-token count, and conclude
that the provider had missed the cache entirely. In reality, the provider had
reported the hit. We had flattened the response into input and output totals
before the useful detail reached the user.

## A total is not an explanation

`prompt_tokens` includes both newly processed input and cached input. Treating
the whole number as fresh input is therefore wrong twice: it overcharges the
cached portion, and it hides the evidence needed to verify the charge.

The useful accounting identity is small:

```text
new input = prompt tokens - cached tokens
cost = new input × input rate
     + cached input × cached rate
     + output × output rate
```

The fix keeps those quantities intact across the managed proxy, Python usage
object, console output, `/cost`, and the chat status line. A turn can now say
how many tokens were new, how many were cached, how many came back as output,
and what was finally charged. Zero is also reported explicitly; absence no
longer masquerades as a cache miss.

## Cache hits are observations, not promises

Implicit provider caching is opportunistic. Similar prompts sent close
together are good candidates, but an application cannot honestly promise that
every turn will hit. Our tests therefore check the contract we control: when a
provider reports cached tokens, the same number survives every layer and uses
the cached rate. They do not invent a hit when the provider reports none.

We exercised that path with a repeated Gemini prompt large enough to qualify
for implicit caching. The warm response reported cached tokens through the
OpenAI-compatible API, which ruled out the tempting but unnecessary solution
of replacing the whole transport. The bug was local accounting, not missing
provider capability.

The lesson is broader than one model or one price. Usage metadata is part of
the product contract. If an optimization changes what a request costs, users
must be able to see both the optimization and the resulting charge.

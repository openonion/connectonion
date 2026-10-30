---
title: The score asked for a temperature the model would not take
date: 2026-10-30
tags: [Plugins, Eval, OpenAI]
---

# The score asked for a temperature the model would not take

The eval plugin fixed one mistake in October: it stopped sending its scoring
calls to `co/` and started using the agent's own model, because a configured
provider is usually billing, data residency or simply the key that works. That
fix was right, and it carried an assumption along with it. The two scoring calls
still pinned `temperature=0.2` and `temperature=0`, values chosen when we always
knew which model would answer.

Now any model can answer. `o4-mini` is the `OpenAILLM` default, and OpenAI's
reasoning models, like the gpt-5 family, accept only the default temperature.
Every other value gets a 400. So an `o4-mini` agent with `plugins=[eval]` did its
work and then failed the turn.

The order of failures made it worse. `generate_expected` already catches a
refused call, because scoring is not the work (#543). But `evaluate_completion`
asks for the expectation again when none is stored, and that second request had
no `try` around it. The first 400 was logged and dropped; the second one went
out of `agent.input()` after the task had finished.

There were two fixes. The scoring calls no longer pick a temperature, so the
model uses its own default: a reasoning model accepts that, and the other
providers already use that default for any call that does not set one. The
fallback expectation now fails the way the early one does. The run loses the
expectation and is scored without it; it does not lose the turn.

Two tests cover this. One records every scoring call and checks that none
carries `temperature`. The other refuses only the expectation request and checks
that the finished turn still gets an evaluation. Both fail on the old code.
Once a side call follows the user's model, every argument it sends has to be
one that model accepts.

# The user's model, and a cut-off answer

Picture someone who runs `co ai -m ollama/qwen3`. They chose a local model
on purpose. Maybe the code is private, maybe they have no credits, maybe
they just like having everything on their own machine. They type "my secret
plan" and watch Ollama answer.

Before Ollama saw anything, though, their prompt had already gone to our
managed backend. The intent step, the small call that works out what you're
asking so the UI can say "Writing it...", sent it to `co/gemini-3.8-flash`.
If they had eval turned on, the scoring calls went there as well. None of
that cost appeared in `agent.total_cost`.

This wasn't meant to happen, and we had already fixed it once, in #543. A
deployed agent kept failing because its intent call went to an empty `co/`
account, so both plugins were changed to "follow the model the agent was
built with":

```python
model=getattr(agent, "model", None) or DEFAULT_MODEL
```

The trouble is that `Agent` has no `.model`. The model lives on
`agent.llm.model`. So the `getattr` always returned `None`, and the fallback
always won. The tests for that fix passed because the fake agent they used
was a `MagicMock` with `agent.model = "gemini-2.5-pro"` set on it, an
attribute no real agent has ever had. The test only checked the fake.

Now both plugins pass `llm=agent.llm` to `llm_do`, which has a new `llm`
parameter for this. They use the user's provider, key and endpoint, with no
model name to look up and get wrong. The tests that pinned this behaviour
now build a real `Agent`.

## Half an answer

The same audit found a second problem that also looked like success. Every
provider reports why a response ended. `finish_reason: "length"` or
`stop_reason: "max_tokens"` means the model hit its output limit and stopped
mid-sentence. None of our providers checked for it. A migration plan that
stopped at "and then we" came back as the final answer, and the turn was
recorded as `natural`.

A tool call was worse. When a model writing a large file runs out of tokens,
the JSON arguments stop in the middle of a string. `json.loads` raised
`JSONDecodeError` straight out of `agent.input()`. The server had already
charged for 8,192 output tokens, and the exception discarded the only object
that knew about them.

Each provider now raises `TruncatedResponseError`, which carries the usage
and any partial text. The check runs before the tool-call JSON is parsed, so
the cost always has somewhere to go. The agent loop adds that cost to
`total_cost`, records the call in the trace as `truncated`, and tells the
model its reply was cut off. It asks the model to answer more briefly or
split the work, for example by writing a long file in several calls. If the
model hits the limit twice more in the same turn, the turn fails loudly with
its cost recorded.

## The calls nobody counted

Fixing the intent step brought up a wider issue from #730. Every `llm_do`
made during a run went uncounted. That includes auto-compact, re_act,
web_fetch and the browser's element finder. `structured_complete` discarded
its usage on every provider. `total_cost` is also the Control Center's budget
cap, so a run could go over its budget while reporting that it hadn't.

Now each provider keeps `last_structured_usage`. While `agent.input()` runs,
the agent is held in a context variable, and `llm_do` uses it to add each
side call to that agent's `total_cost` and trace. The worker thread that runs
tools gets a copy of that context, so a tool's `llm_do` is counted too.

## What we took from it

Both bugs came down to a check that didn't match reality. The intent tests
checked an attribute that real agents don't have. The providers treated any
response they received as a complete one. When a test needs a stand-in for
the real object, it should use the real object, or it can end up testing
only the stand-in.

# The model you chose, and the one we called

Picture someone who runs `co ai -m ollama/qwen3`. They chose a local model on
purpose. Maybe the code is under NDA, maybe they have no credits, or maybe they
just want their prompts to stay on their own machine. They type "my secret
plan" and watch Ollama answer.

Before Ollama saw anything, though, that prompt had already gone to our
servers. `co ai` runs a small intent step first. It is a quick call that
reads what you asked so the UI can say "Writing it..." while the real work
starts. That call went to `co/gemini-3.8-flash`, our managed model, whatever
the user had picked. With eval turned on, the scoring calls went there as
well. A user on their own OpenAI key got the same treatment. Their words
reached a backend they had chosen not to use, and paid for with credits that
`agent.total_cost` never counted.

## We had fixed this already

The embarrassing part is that this was a known bug with a fix already merged.
Earlier, in #543, a deployed agent failed every fifteen minutes because
its intent call went to an empty `co/` account. The fix sounded right: follow
the model the agent was built with.

```python
model=getattr(agent, "model", None) or DEFAULT_MODEL
```

A test was written to prove it:

```python
agent = MagicMock()
agent.model = "gemini-2.5-pro"
system_reminder.detect_intent(agent)
assert called.call_args.kwargs["model"] == "gemini-2.5-pro"
```

It passed, and it could never have failed. `Agent` has no `.model`
attribute. The model lives at `agent.llm.model`. On every real agent, the
`getattr` returned `None` and the fallback to our managed model won. The
test's fake had been given an attribute that no real agent ever had, so the
test checked the fake and nothing else. The bug looked fixed, stayed fixed on
paper, and kept sending prompts to us.

It came to light in an audit, when someone built a real
`Agent(model="ollama/qwen3")`, called the intent step, and printed which model
it used. It was ours.

## The fix

The fix is to stop looking the model up by name. `llm_do` now takes an `llm=`
argument, and the intent step and eval scoring pass `llm=agent.llm`. That is
the same object the agent uses for its own calls. It already carries the
user's provider, key and endpoint, so a name can't come back wrong. The two
tests that used a fake `.model` now build a real `Agent` on a local LLM and
make the managed-model factory raise if anything calls it.

## What we took from it

A fake is only as good as its resemblance to the real object. The mock here
agreed with whatever the test assumed, which let a false assumption pass as a
checked one. When a test depends on the shape of an object, build the real
object. That test would have failed on day one, and a user on a local model
would have kept their prompts on their machine.

The same audit also found that answers cut off at the output limit were
reported as successes, and that side calls like this one never reached
`agent.total_cost`; both are fixed in the same change.

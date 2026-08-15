# One Default, Five Answers

The issue was one sentence: make Gemini 3.7 the default model.

I expected a one-line diff. Find the constant, bump the version, done. So I did
what you do — grep for the current default:

```
grep -rn "co/gemini" --include='*.py' --include='*.yml' .
```

Fifty-nine lines came back. Not fifty-nine mentions of a constant. Fifty-nine
separate, hand-typed copies of the string `co/gemini-3.6-flash`, each one
independently claiming to be *the* default.

## Where "the default" actually lived

Once you stop skimming and start reading the hits, they sort into places, and
each place is its own small story:

1. **`connectonion/core/agent.py`** — the `Agent` class signature. The one
   everybody would name if you asked "where is the default model defined?"
2. **`connectonion/llm_do.py`** — the one-shot call helper, with its own copy
   in the signature and four more in its docstring.
3. **`connectonion/core/llm.py`** — twice, actually: `OpenOnionLLM` for the
   managed route, and `GeminiLLM` with the bare `gemini-3.6-flash` for people
   bringing their own Google key.
4. **`connectonion/cli/main.py`** — the `co ai --model` option default, typed
   out again inside a `typer.Option(...)` call.
5. **`action.yml`** — the GitHub Action's `model` input, in YAML, where no
   Python constant can reach. Plus its twin fallback in
   `cli/github_action.py`, reading `CO_ACTION_MODEL` with — you guessed it —
   another literal.

And that's just the headline five. Keep reading the grep and the default also
lived in the subagent frontmatter loaders (`useful_plugins/subagents.py`,
`subagents/loader.py`, `cli/co_ai/agents/registry.py`), the project
scaffolding that writes `.env` files for new users
(`cli/commands/init.py`, `create.py`, `project_cmd_lib.py`), the eval plugin's
scoring model, the TUI status bar's example renders, the transcribe helper,
and about forty documentation lines that confidently told readers what the
default was.

## Why defaults drift

None of this happened because anyone was careless. It happened because every
one of those places was written on a different day, and on each of those days
the author did the reasonable thing: they looked at what the default was *that
day* and typed it in. A new plugin copies the current default at birth. Then
the default moves on, and the copy doesn't.

We had already paid for this once. The free-models list in this repo used to
exist as two copies in two branches of the same auth flow, and the test that
guards it now carries the scar in its docstring: "both copies naming the
retired model — the shape that has caused most of this release's bugs."
Defaults drift for exactly the same reason lists drift. A literal is a
snapshot; nobody schedules the snapshot's refresh.

The tell was right there in the grep output. If the repo had one source of
truth, the search would have returned one definition and fifty-eight
references. It returned fifty-nine definitions.

## The fix is a name, not a sed

Running `sed 's/3.6/3.7/'` would have closed the issue and re-armed the trap.
The next default change would face the same fifty-nine-line grep, minus
whatever new copies had accumulated by then.

So the actual change is one new line in `core/usage.py`, next to the pricing
and context tables where the other model facts already live:

```python
DEFAULT_MODEL = "co/gemini-3.7-flash"
```

`Agent`, `llm_do`, `transcribe`, both LLM classes, `co ai`, and the GitHub
Action fallback now import that name. The next time the default moves, the
diff is the one-liner I originally expected — plus the places that genuinely
cannot import Python and have to stay prose: `action.yml`, the scaffolded
`.env` templates, the docs. Those still exist, but they went from
fifty-something down to a handful, and the test suite now asserts that the
three entry points agree with each other, so a partial edit fails loudly
instead of shipping quietly.

Two things deliberately did *not* change. Anything a user configured
explicitly stays theirs — the defaults only apply when you configured nothing,
and the tests pin that. And `co/gemini-3.6-flash` stays on the free-models
list, priced and reachable, as the rollback: if 3.7 misbehaves, reverting is
one constant, no user migration.

What changing one number everywhere teaches you is that "everywhere" is the
bug. A default you have to change in fifty-nine places isn't a default — it's
fifty-nine opinions that currently happen to agree.

---
title: A model that is local because you said so
date: 2026-09-16
---

# A model that is local because you said so

`llm_do("summarise this", model="ollama/qwen2.5:0.5b")` runs on your machine now.
No API key, no credits, no request leaving the laptop.

The interesting part is not Ollama. It is the question Ollama forces: **how does
the library decide where a model lives?**

## Until now, the name decided

```
gpt-4o                    → api.openai.com        + OPENAI_API_KEY
claude-sonnet-4-…         → api.anthropic.com     + ANTHROPIC_API_KEY
gemini-3.8-flash          → generativelanguage…   + GEMINI_API_KEY
co/gemini-3.8-flash       → our managed proxy     + your account
qwen2.5:0.5b              → ValueError: Unknown model
```

That works because cloud providers are a closed set. There are five of them, the
name maps to the address, and the address maps to the credential. A name is
enough.

## Local models break that in a specific way

Ollama fits the old shape fine: `ollama/` is a prefix, and its address is
`localhost:11434` — known, fixed, inferable. Nine lines:

```python
class OllamaLLM(OpenAICompatibleLLM):
    def __init__(self, model, api_key=None, base_url=None):
        super().__init__(
            model=model.removeprefix("ollama/"),
            base_url=base_url or os.getenv("OLLAMA_BASE_URL",
                                           "http://localhost:11434/v1"),
            api_key=api_key or "ollama",
        )
```

But Ollama is not the only local runtime. LM Studio is on `:1234`, vLLM on
`:8000`, a company's internal gateway on whatever someone chose last year. We
cannot ship a prefix for each, and we certainly cannot guess the port.

So those get the only thing that can work: you say where.

```python
llm_do(text, model="my-model", base_url="http://localhost:1234/v1")
```

## The rule that matters more than the feature

Given both a name and an address, which wins?

The address. Always. And that is not a taste call — it closes a credential leak:

```python
# a model you named "gpt-4" in LM Studio, because local models
# take whatever name you give them
llm_do(text, model="gpt-4", base_url="http://localhost:1234/v1")
```

If the name decided, "gpt-4" routes to `OpenAILLM`, which reaches for
`OPENAI_API_KEY` and sends it to `localhost:1234`. Your cloud key, handed to
whatever process is listening on that port.

So: an explicit endpoint is checked before any name inference, and a custom
endpoint never inherits a cloud key — it gets a placeholder. `co/` plus a
`base_url` is refused outright rather than silently overriding managed routing,
because "I asked for managed and got something else" is worse than an error.

## What it cost

Seventy lines do the actual work — HTTP, parsing real `tool_calls`, structured
output, telling apart *no choices* from *truncated* from *the model refused*.
Every one of those would exist for an Ollama-only version too; they would just
live in a class with a different name.

The generic half — arbitrary endpoints — costs **three** things beyond that: one
branch in the factory, one parameter, and one fix to `llm_do`, which had been
passing extra arguments to generation instead of to client construction.

## What it does not do

No cloud fallback when the local server is down; the connection error says which
address failed. No model downloading. No guessing at a price for a local
endpoint — the cost is reported as zero because local inference has no API fee,
not because we assumed something. And no inventing tool calls from XML the model
happened to emit: the runtime has to produce real `tool_calls` or there are none.

One finding worth keeping, from testing against a real model rather than a
stand-in: constraining the decoder with a JSON schema is not enough on its own.
The server produces valid JSON that ignores the input entirely — correctly
shaped, completely invented. The schema has to reach the model's prompt as well
as its decoder. That line of code looks redundant until you have seen the output
without it.

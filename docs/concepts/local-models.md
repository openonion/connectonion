# Local models with Ollama

Planned for **1.8.6** (feature PR for #103; not yet a published release).
Ollama runs the model; ConnectOnion sends requests to its local API. Install
Ollama separately from [ollama.com](https://ollama.com), then start it and pull
a model, for example:

```sh
ollama serve
# In another terminal:
ollama pull qwen3.5:2b
```

```python
from connectonion import llm_do

note = llm_do(
    "[s1] We fixed logging. Tests passed. Deployment is still pending.",
    model="ollama/qwen3.5:2b",
    system_prompt="Summarize decisions, completed work and pending actions. Keep source IDs.",
)
print(note)
```

No OpenAI key or ConnectOnion authentication is required for local inference.
The framework does not download models or fall back to a cloud model. Tools and
plugins you attach can still use external services; local inference alone does
not make every agent workflow offline.

## Endpoint configuration

The `ollama/` prefix chooses Ollama. Only that prefix is removed; model namespaces
and tags are retained. Endpoint precedence is:

1. Explicit `base_url` on `llm_do`, `Agent`, or `create_llm`.
2. `OLLAMA_BASE_URL` (only for `ollama/` models).
3. `http://localhost:11434/v1`.

A server root such as `http://localhost:11434/` gets `/v1` appended. An explicit
path such as `/custom/v1` is preserved, so pass an **API base**, not a complete
`/chat/completions` URL. Credentials go in `api_key`, not the URL.

For any OpenAI-compatible Chat Completions service, supply its address and raw
model identifier. This also provides the transport for LM Studio / llama.cpp;
feature compatibility depends on the server and needs to be tested separately.

```python
note = llm_do(
    "Summarize this conversation...",
    model="my-org/local-model:q4",
    base_url="http://localhost:1234/v1",
    # api_key="...",  # Only if this specific endpoint requires authentication.
)
```

An explicit `base_url` selects this compatible transport even for a model named
`gpt-*`. Do not combine it with `co/`, which means managed routing. Neither local
nor custom endpoints borrow `OPENAI_API_KEY` or other cloud credentials. When a
key is omitted, a non-secret SDK placeholder is used. Calls without `base_url`
retain their existing provider routing.

## Structured notes

```python
from pydantic import BaseModel
from connectonion import llm_do

class Note(BaseModel):
    topics: list[str]
    decisions: list[str]
    completed: list[str]
    pending: list[str]

note = llm_do(
    "[s1] We considered Redis, then decided to keep SQLite. No migration was run.",
    output=Note,
    model="ollama/qwen3.5:2b",
)
```

The endpoint receives `response_format` with a JSON schema and the result is
validated with Pydantic. Unsupported schemas, invalid JSON, truncated output and
refusals are errors, not fabricated empty notes. This uses Chat Completions,
not OpenAI's Responses API. Streaming is not supported by these synchronous
return-value interfaces. Generation kwargs (e.g. `max_tokens`, `temperature`)
go to the API; `base_url` and `api_key` configure the client.

For a thinking model on current Ollama, pass `reasoning_effort="none"` for
short extraction tasks if supported. Otherwise the reasoning can consume the
whole output budget before any note is returned. The file example exposes
`--reasoning-effort none`; the framework does not change model defaults silently.

## Tools

```python
from connectonion import Agent

def add(a: int, b: int) -> int:
    """Add two integers."""
    return a + b

agent = Agent("local", model="ollama/qwen3.5:2b", tools=[add])
print(agent.input("Use add to calculate 2 + 3."))
```

Use a model **and runtime template/parser** that produce OpenAI-compatible
`tool_calls`. The adapter converts these to ConnectOnion tools, and passes tool
results into the next turn. Model-generated text that merely describes a tool
call is not proof that a tool ran. Unsupported tool requests surface the server
error. Passing an existing `llm` and a new `base_url` together is rejected;
configure the address when constructing that LLM instead.

## MiniCPM5-2B

The [official model](https://huggingface.co/openbmb/MiniCPM5-2B) is a candidate for
small local note-taking: approximately 2.52B total parameters, with GGUF and MLX
weights. Follow the [official Ollama import guide](https://github.com/OpenBMB/MiniCPM/blob/main/docs/deployment/ollama.md)
to create the local alias `minicpm5-2b`, then use `model="ollama/minicpm5-2b"`.
This alias is not a promise of an official `ollama pull` registry entry.

The Q4_K_M file is about 1.56GB; runtime RAM additionally includes KV cache and
working buffers. Start with an 8K context configured in Ollama's Modelfile
(`PARAMETER num_ctx 8192`) rather than allocating the advertised 128K context.
The OpenAI-compatible endpoint does not expose every Ollama-native option.
Set context and load lifetime in Ollama, not as arbitrary `llm_do` kwargs.

MiniCPM5's XML tool syntax needs a runtime parser. Its official model card
recommends SGLang's `minicpm5` parser for tools. Ollama text generation and
MiniCPM5 tool calling are separate acceptance checks. The model's reasoning
mode/chat template also needs to match the runtime; the adapter does not guess
or strip arbitrary XML from your notes.

See [local_notes.py](../../examples/local_notes.py) for a file-to-Markdown example.
Chunk long logs at conversation boundaries and retain original source IDs.
Check the model against reversals and incomplete actions, not just fluency.
The example never executes instructions found inside a log.

## Errors and measurement

- Connection failure: start `ollama serve`, check the address and proxy settings.
- Model not found: inspect `ollama list`, then explicitly pull/import the model.
- Unsupported tools/schema: choose a compatible runtime/model or use plain text.
- Context/output overflow: reduce the input chunk, adjust Ollama context or the
  output limit. A response cut at the output limit raises
  `TruncatedResponseError` (still a `ValueError`); inside an agent run the model
  is first told to shorten or split its reply and asked again.

Network bounds use the same finite timeouts/retries as other providers.
SDK status errors preserve runtime diagnostics; connection errors name the
endpoint and retain their original cause. Local token usage has zero API cost.
Custom endpoint pricing is **untracked** (represented as zero), even if that
endpoint charges money; no guessed cloud price is applied.

Record the machine, runtime version, model/quantization, context, peak RAM,
warm/cold latency and summary mistakes when comparing models. The opt-in
`tests/e2e/real_api/test_real_ollama.py` exercises a running model; offline
transport tests do not establish model quality.

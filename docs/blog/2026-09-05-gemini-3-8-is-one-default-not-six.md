# Gemini 3.8 Is One Default, Not Six

Target release: 1.8.2. This is a design record for an unreleased change, not a
claim that a package has been published.

## The problem

ConnectOnion did not have one model default in practice. `Agent`, `llm_do`, and
`co ai` shared a constant, but project generators, trust evaluation, browser
helpers, auto-compaction, subagents, examples, and the managed server still
carried their own Gemini 3.7 literals. Changing one of them could make a new
project say one thing and send another.

Gemini 3.8 Flash also changes the compatibility contract. Google documents it
as a stable production model with a 1,048,576-token input window, 65,536-token
output window, function calling, structured output, and low/medium/high thinking
levels. The 3.8 migration guidance retires explicit sampling parameters and
`thinking_budget`.

## Options considered

One option was a new native Google adapter in oo-api. That would have duplicated
message, tool, response, usage, and billing conversion already handled by the
documented OpenAI-compatible endpoint. Another was automatic fallback to
Gemini 3.7 or OpenAI when 3.8 was unavailable. That would change model behavior,
provider, data path, and price without the caller asking.

## Decision

Keep the existing transparent architecture. A `co/gemini-3.8-flash` request
travels through ConnectOnion's `OpenOnionLLM` to oo-api; oo-api strips only the
managed prefix, validates the model and pricing catalogue, then calls Google's
OpenAI-compatible Chat Completions endpoint with a server-held
`GEMINI_API_KEY`. A direct `gemini-3.8-flash` request uses the same compatibility
endpoint with the user's key.

Both boundaries remove deprecated 3.8 sampling fields, reject
`thinking_budget`, validate `reasoning_effort`, preserve function tools and
Gemini thought signatures, and return the complete response shape the current
Agent API promises. The raw Google API can stream, but ConnectOnion and oo-api
do not expose an SSE stream yet; accepting a stream flag while returning an
iterator would break billing and the `LLMResponse` contract.

`DEFAULT_MODEL` is the client source of truth. Internal helpers import it rather
than pinning their own model. Generated configuration and active documentation
name 3.8. The managed server has an operator-only `LLM_DEFAULT_MODEL` override
for rollback. Gemini 3.7 remains in catalogues as an explicit choice, and OpenAI
and Anthropic routing remain unchanged. Missing Google credentials return a
provider-configuration error; there is no silent cross-provider fallback.

## Evidence and limits

Backend tests cover discovery, default routing, pricing, compatibility fields,
tool and thought-signature transport, missing-key failure, and unchanged OpenAI
compatibility. Client tests cover every omitted-model entry point, direct Gemini
request/response parsing, structured output, parameter validation, explicit
OpenAI selection, explicit 3.7 rollback, and a repository scan for stale 3.7
defaults.

This work does not publish 1.8.2, deploy oo-api, rotate a credential, or add
streaming to the Agent interface. Those are separate reviewed operations.

## Revisit when

Use a native Google adapter if the compatibility endpoint can no longer preserve
the tool, structured-output, thought-signature, usage, or billing fields the
product needs. Add automatic fallback only with an explicit caller policy that
makes the provider, price, and data-path change visible. Add streaming only when
both billing settlement and client APIs define a real incremental contract.

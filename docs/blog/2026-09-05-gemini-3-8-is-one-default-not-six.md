# Gemini 3.8 Is One Default, Not Six

Target release: 1.8.2. This is the story of an unreleased design change, not a
claim that a package has been published.

## The edit that would not stay small

The request sounded like a one-line change: make Gemini 3.8 Flash the default.
`Agent` already imported `DEFAULT_MODEL`, so changing that constant appeared to
finish the job.

Then a newly generated project still named Gemini 3.7. `co ai` could start on
3.8 while one of its subagents quietly started on 3.7. Browser helpers, trust
evaluation, reflection, auto-compaction, and transcription each had another
answer. Nothing crashed. That was the dangerous part: two users could omit the
same argument and reach different models depending on which doorway they used.

Following an omitted model from the public APIs to the provider exposed six
kinds of default: the SDK constant, direct-Gemini constructor, automatic agent
definitions, internal helper calls, project generators, and the managed server.
The model name had become configuration by copy and paste.

## The turn in the investigation

Replacing every `3.7` string would have hidden the architecture problem and
would also have broken a useful rollback. The important question was not “where
does 3.7 appear?” It was “where is a caller allowed to omit its choice?”

That distinction changed the work. Explicit `gemini-3.7-flash` examples used
for compatibility and historical records stayed valid. Omitted-model paths had
to converge on one source. A repository scan now guards that boundary: 3.7 can
remain selectable, but it cannot drift back into an implicit default.

The provider path raised a second decision. Gemini 3.8 Flash is available on
Google's OpenAI-compatible endpoint with a 1,048,576-token input window, a
65,536-token output window, function calling, structured output, and
low/medium/high thinking levels. Building a new native Google adapter would
have duplicated the message, tool, response, usage, and billing conversion that
the existing compatibility path already performs.

## One path, one explicit boundary

We kept the transparent route. A managed `co/gemini-3.8-flash` request travels
through `OpenOnionLLM` to oo-api. The server removes the managed prefix,
validates the pricing catalogue, and calls Google's OpenAI-compatible Chat
Completions endpoint with a server-held `GEMINI_API_KEY`. A direct
`gemini-3.8-flash` request reaches the same compatibility endpoint with the
user's own key.

Both boundaries remove Gemini 3.8 sampling fields that Google has deprecated,
reject `thinking_budget`, validate `reasoning_effort`, and preserve function
tools and Gemini thought signatures. The raw Google API can stream, but the
current ConnectOnion Agent contract returns one `LLMResponse`, and oo-api bills
one complete response. Silently returning an iterator when a caller passes
`stream=True` would violate both contracts, so the compatibility layer removes
stream flags until the product has a real incremental billing and response
design.

There is no automatic provider fallback. If Google credentials are absent, the
request fails with a provider-configuration error instead of quietly changing
model, price, or data path. Gemini 3.7 remains an explicit rollback choice, and
OpenAI and Anthropic remain explicit choices. An oo-api operator may also set
`LLM_DEFAULT_MODEL` during a controlled rollback.

## The lesson

A default is behavior, not documentation. If several entry points may omit a
choice, every one of them must derive that behavior from the same value. Active
documentation and generated configuration now follow `DEFAULT_MODEL`; internal
helpers import it instead of pinning a model name; the managed server publishes
its own effective default alongside the model catalogue.

Tests follow the journey that found the bug: omit the model at each public and
automatic entry point, inspect the direct and managed requests, exercise tools,
thought signatures, structured output, pricing, and missing-key errors, then
scan for a stale 3.7 default. Explicit OpenAI and 3.7 selections are tested too,
because a shared default must not become a forced model.

This work does not publish 1.8.2, deploy oo-api, rotate a credential, or add
streaming to the Agent interface. Revisit the adapter choice if Google's
compatibility endpoint can no longer preserve the fields ConnectOnion needs.
Revisit fallback only when callers can opt into a visible provider, price, and
data-path change.

# Explicit local endpoints, with Ollama defaults

Status: proposed for 1.8.6; provider slice of #103.

Daily notes should use a small local model without managed credentials. The
factory currently accepts recognized cloud names only, and llm_do sends extra
arguments to generation rather than initialization. An Ollama-only branch would
leave the custom endpoint question in #103 unresolved.

## Decision

An explicit `base_url` selects Chat Completions with an arbitrary raw model name
and optional explicit key. `ollama/` uses the same implementation with Ollama's
default address or OLLAMA_BASE_URL. Explicit address wins over environment.
Reject co/ plus base_url rather than silently overriding managed routing. Calls
without an override keep their existing routing. An injected LLM cannot be
combined with an ignored base_url.

Root URLs gain /v1; explicit paths are preserved. No cloud key is inherited,
model downloaded or cloud fallback added. Structured output uses JSON schema
response_format plus Pydantic validation, not Responses API. The runtime must
produce actual tool_calls: we do not guess at model-specific XML. Local cost is
zero API cost; generic endpoint cost is untracked, not inferred from a model
name resembling a cloud model. Streaming, provider UI and Ollama-native
load/context options are outside this change.

## Alternatives

- OpenAILLM with OPENAI_BASE_URL risks global routing/credential crossover and
  uses Responses for structured output. Explicit configuration is reviewable.
- Ollama SDK adds a dependency and duplicates request conversion.
- Refactoring every existing provider unnecessarily expands regression scope.

## Verification and rollback

Test both public entry points, precedence, key isolation, SDK serialization,
structured validation and tool-result round trips. Real Ollama tests separately
check runtime/model behavior and do not require cloud keys. Build and test the
wheel. No stored configuration migration or protocol/UI changes. Revert this
feature to remove the new configuration paths; existing cloud selection remains.

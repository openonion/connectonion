"""
Purpose: Unified LLM provider abstraction with factory pattern for OpenAI, Anthropic, Gemini, Groq, Grok, Mistral, OpenRouter, and OpenOnion
LLM-Note:
  Dependencies: imports from [abc, typing, dataclasses, json, os, base64, openai, anthropic, requests, pathlib, yaml, pydantic, .usage, .exceptions] | imported by [agent.py, llm_do.py, conftest.py] | tested by [tests/unit/test_llm.py, tests/test_llm_do.py, tests/test_real_*.py, tests/unit/test_exceptions.py, tests/unit/test_uniform_provider_errors.py]
  Data flow: Agent/llm_do calls create_llm(model, api_key) → factory routes to provider class → Provider.__init__() validates API key → Agent calls complete(messages, tools) OR structured_complete(messages, output_schema) → provider converts to native format → calls API → parses response → returns LLMResponse(content, tool_calls, raw_response) OR Pydantic model instance
  State/Effects: reads environment variables (OPENAI_API_KEY, ANTHROPIC_API_KEY, GEMINI_API_KEY/GOOGLE_API_KEY, GROQ_API_KEY, OPENROUTER_API_KEY, XAI_API_KEY, OPENONION_API_KEY) | reads OPENONION_API_KEY from env / .env / ~/.co/keys.env | makes HTTP requests to LLM APIs | no caching or persistence
  Integration: exposes create_llm(model, api_key), LLM abstract base class, OpenAILLM, AnthropicLLM, GeminiLLM, GroqLLM, GrokLLM, OpenRouterLLM, OpenOnionLLM, LLMResponse, ToolCall dataclasses | providers implement complete() and structured_complete() | OpenAI message format is lingua franca | tool calling uses OpenAI schema converted per-provider
  Performance: openai/anthropic are imported inside the functions that use them, so importing this module does not pay for either SDK | stateless (no caching) | synchronous (no streaming) | default max_tokens=8192 for Anthropic (required) | each call hits API
  Errors: raises ValueError for missing API keys, unknown models, invalid parameters | provider-specific errors bubble up (openai.APIError, anthropic.APIError, etc.) | OpenOnionLLM transforms 402 errors to InsufficientCreditsError with formatted message and typed attributes | Pydantic ValidationError for invalid structured output

Unified LLM provider abstraction layer for ConnectOnion framework.

This module provides a consistent interface for interacting with multiple LLM providers
(OpenAI, Anthropic, Google Gemini, Groq, Grok, Mistral, OpenRouter, and ConnectOnion managed keys)
through a common API.

Architecture Overview
--------------------
The module follows a factory pattern with provider-specific implementations:

1. **Abstract Base Class (LLM)**:
   - Defines the contract all providers must implement
   - Two core methods: complete() for text, structured_complete() for Pydantic models
   - Ensures consistent interface across all providers

2. **Provider Implementations**:
   - OpenAILLM: Native OpenAI API with responses.parse() for structured output
   - AnthropicLLM: Claude API with tool calling workaround for structured output
   - GeminiLLM: Google Gemini with response_schema for structured output
   - GroqLLM: Groq via OpenAI-compatible endpoint
   - GrokLLM: xAI Grok via OpenAI-compatible endpoint
   - MistralLLM: Mistral AI via OpenAI-compatible endpoint
   - OpenRouterLLM: OpenRouter via OpenAI-compatible endpoint
   - OpenOnionLLM: Managed keys using OpenAI-compatible proxy endpoint

3. **Factory Function (create_llm)**:
   - Routes model names to appropriate providers
   - Handles API key initialization
   - Returns configured provider instance

Key Design Decisions
-------------------
- **Structured Output**: Each provider uses its native structured output API when available
  * OpenAI: responses.parse() with text_format parameter
  * Anthropic: Forced tool calling with schema validation
  * Gemini: response_schema with JSON MIME type
  * OpenOnion: Proxies to OpenAI with fallback

- **Tool Calling**: OpenAI format used as the common schema, converted per-provider
  * All providers return ToolCall dataclasses with (name, arguments, id)
  * Enables consistent agent behavior across providers

- **Message Format**: OpenAI's message format (role/content) is the lingua franca
  * Providers convert to their native format internally
  * Simplifies Agent integration

- **Parameter Passing**: **kwargs pattern for runtime parameters
  * temperature, max_tokens, etc. flow through to provider APIs
  * Allows provider-specific features without bloating base interface

Data Flow
---------
Agent/llm_do → create_llm(model) → Provider.__init__(api_key)
           ↓
Provider.complete(messages, tools, **kwargs)
           ↓
Convert messages → Call native API → Parse response
           ↓
Return LLMResponse(content, tool_calls, raw_response)

For structured output:
Provider.structured_complete(messages, output_schema, **kwargs)
           ↓
Use native structured API → Validate with Pydantic
           ↓
Return Pydantic model instance

Dependencies
-----------
- openai: OpenAI and OpenOnion provider implementations
- anthropic: Claude provider implementation
- google.generativeai: Gemini provider implementation
- pydantic: Structured output validation
- requests: OpenOnion authentication checks
- yaml: OpenOnion config file parsing

Integration Points
-----------------
Imported by:
  - agent.py: Agent class uses LLM for reasoning
  - llm_do.py: One-shot function uses LLM directly
  - conftest.py: Test fixtures

Tested by:
  - tests/unit/test_llm.py: Unit tests with mocked APIs
  - tests/unit/test_exceptions.py, tests/unit/test_uniform_provider_errors.py:
    the error translation (402/403/503 → typed errors)
  - tests/e2e/real_api/: real API integration tests, marked real_api

Environment Variables
--------------------
Required (pick one):
  - OPENAI_API_KEY: For OpenAI models
  - ANTHROPIC_API_KEY: For Claude models
  - GEMINI_API_KEY or GOOGLE_API_KEY: For Gemini models
  - OPENONION_API_KEY: For co/ managed keys (from .env or ~/.co/keys.env)
  - GROQ_API_KEY: For groq/ prefixed models
  - OPENROUTER_API_KEY: For openrouter/ prefixed models
  - OPENROUTER_HTTP_REFERER: Optional attribution header for OpenRouter
  - OPENROUTER_X_TITLE: Optional app title header for OpenRouter
  - XAI_API_KEY: For grok/ prefixed models (xAI)
  - MISTRAL_API_KEY: For mistral/ prefixed models

Optional:
  - OPENONION_DEV: Use localhost:8000 for OpenOnion (development)
  - ENVIRONMENT=development: Same as OPENONION_DEV

Error Handling
-------------
- ValueError: Missing API keys, unknown models, invalid parameters
- Provider-specific errors: Bubble up from native SDKs (openai.APIError, etc.)
- Structured output errors: Pydantic ValidationError if response doesn't match schema

Performance Considerations
-------------------------
- Default max_tokens: 8192 for Anthropic (required), configurable for others
- No caching: Each call is stateless (Agent maintains conversation history)
- No streaming: Currently synchronous only (streaming planned for future)

Example Usage
------------
Basic completion:
    >>> from connectonion.llm import create_llm
    >>> llm = create_llm(model="o4-mini")
    >>> response = llm.complete([{"role": "user", "content": "Hello"}])
    >>> print(response.content)

Structured output:
    >>> from pydantic import BaseModel
    >>> class Answer(BaseModel):
    ...     value: int
    >>> llm = create_llm(model="o4-mini")
    >>> result = llm.structured_complete(
    ...     [{"role": "user", "content": "What is 2+2?"}],
    ...     Answer
    ... )
    >>> print(result.value)  # 4

With tools:
    >>> tools = [{"name": "search", "description": "Search the web", "parameters": {...}}]
    >>> response = llm.complete(messages, tools=tools)
    >>> if response.tool_calls:
    ...     print(response.tool_calls[0].name)  # "search"
"""

import json
import logging
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Type

logger = logging.getLogger(__name__)
# google-genai not needed - using OpenAI-compatible endpoint instead

import requests
from pydantic import BaseModel


@dataclass
class ToolCall:
    """Represents a tool call from the LLM.

    Attributes:
        name: The function name to call
        arguments: Dict of arguments to pass to the function
        id: Unique identifier for this tool call
        extra_content: Provider-specific metadata (e.g., Gemini 3 thought_signature).
            Must be echoed back in the assistant message for models that require it.
            See: https://ai.google.dev/gemini-api/docs/thinking#openai-sdk
    """
    name: str
    arguments: Dict[str, Any]
    id: str
    extra_content: Optional[Dict[str, Any]] = None


# Import TokenUsage from usage module
from ..backend import backend_url
from .exceptions import (
    InsufficientCreditsError,
    LLMAuthenticationError,
    LLMConnectionError,
    LLMProviderError,
    LLMRateLimitError,
    PaidModelRequiredError,
    ProviderServiceError,
)
from .usage import DEFAULT_DIRECT_GEMINI_MODEL, DEFAULT_MODEL, TokenUsage, calculate_cost


def _is_paid_account_required(error) -> bool:
    """Whether a 403 is the backend saying this model needs purchased credits."""
    body = getattr(error, 'body', {}) or {}
    detail = body.get('detail', {}) if isinstance(body, dict) else {}
    return isinstance(detail, dict) and detail.get('error') == 'paid_account_required'


# Explicit network bounds for every provider client (#1116).
#
# A scheduled run froze mid-iteration with the upstream socket in CLOSE_WAIT:
# the server had closed its side and the client sat in a read that nothing
# bounded. No error, no exit, killed by hand after 15 minutes. The fix is not
# cleverness, it is that no provider client is ever constructed on implicit
# SDK defaults again — every one carries these numbers, visibly.
#
# READ is 600s because a long non-streaming generation legitimately sends no
# bytes until it finishes; cutting that off would break exactly the runs that
# matter (#1116: "confirm ordinary long model generations are not cut off").
# CONNECT is 20s — generous for proxy/VPN users, far below "looks hung".
#
# The documented upper bound for a stalled upstream is therefore
# (1 + max_retries) x 600s per request: ~30 minutes for the default 2 retries,
# ~60 for OpenOnionLLM's deliberate 5 (transient relay blips used to kill
# whole agent runs; that decision predates this and stands). Bounded and
# typed — a stall now ends in LLMConnectionError, never a silent hang.
LLM_CONNECT_TIMEOUT_SECONDS = 20.0
LLM_READ_TIMEOUT_SECONDS = 600.0
LLM_MAX_RETRIES = 2


def _network_bounds(max_retries: int = LLM_MAX_RETRIES) -> dict:
    """Constructor kwargs no provider client is allowed to omit."""
    import openai

    return {
        "timeout": openai.Timeout(
            LLM_READ_TIMEOUT_SECONDS, connect=LLM_CONNECT_TIMEOUT_SECONDS
        ),
        "max_retries": max_retries,
    }


@dataclass
class LLMResponse:
    """Response from LLM including content and tool calls."""
    content: Optional[str]
    tool_calls: List[ToolCall]
    raw_response: Any
    usage: Optional[TokenUsage] = None


class LLM(ABC):
    """Abstract base class for LLM providers."""

    def _call_provider(self, send, base_url: str = ""):
        """Run one provider request and translate its failure to a shared type.

        The same auth failure used to surface three different ways depending on
        the model prefix — openai.AuthenticationError on gpt-*,
        anthropic.AuthenticationError on claude-*, and a bare
        ValueError("Groq API Error: ...") on groq/* — so the only portable
        handler was `except Exception`, which also swallows bugs.

        Every provider goes through here, so `except LLMAuthenticationError`
        means the same thing whichever model was used.

        Translating never costs the original: it is chained as __cause__, so the
        traceback still says what the SDK actually reported.
        """
        import anthropic
        import openai
        model = getattr(self, "model", "unknown")
        try:
            return send()
        except LLMProviderError:
            # Already translated, and by something that knew more than we do
            # here — OpenOnionLLM maps 402 to InsufficientCreditsError. Wrapping
            # it again would bury the specific type under a vaguer one.
            raise
        except (openai.AuthenticationError, openai.PermissionDeniedError,
                anthropic.AuthenticationError, anthropic.PermissionDeniedError) as e:
            raise LLMAuthenticationError(e, model=model) from e
        except (openai.RateLimitError, anthropic.RateLimitError) as e:
            raise LLMRateLimitError(e, model=model) from e
        except (openai.APITimeoutError, openai.APIConnectionError,
                anthropic.APITimeoutError, anthropic.APIConnectionError) as e:
            raise LLMConnectionError(e, model=model, base_url=base_url) from e
        except (openai.APIStatusError, anthropic.APIStatusError) as e:
            # A status the SDK did not give its own class to is still a provider
            # failure. Map the two that matter and let the rest surface as-is
            # rather than inventing a category for them.
            status = getattr(e, "status_code", None)
            if status == 429:
                raise LLMRateLimitError(e, model=model) from e
            if status in (401, 403):
                raise LLMAuthenticationError(e, model=model) from e
            raise

    @abstractmethod
    def complete(self, messages: List[Dict[str, str]], tools: Optional[List[Dict[str, Any]]] = None) -> LLMResponse:
        """Complete a conversation with optional tool support."""
        pass

    @abstractmethod
    def structured_complete(self, messages: List[Dict], output_schema: Type[BaseModel]) -> BaseModel:
        """Get structured Pydantic output matching the schema.

        Args:
            messages: Conversation messages in OpenAI format
            output_schema: Pydantic model class defining the expected output structure

        Returns:
            Instance of output_schema with parsed and validated data

        Raises:
            ValueError: If the LLM fails to generate valid structured output
        """
        pass


class OpenAILLM(LLM):
    """OpenAI LLM implementation."""

    def __init__(self, api_key: Optional[str] = None, model: str = "o4-mini", **kwargs):
        import openai
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError("OpenAI API key required. Set OPENAI_API_KEY environment variable or pass api_key parameter.")

        self.client = openai.OpenAI(api_key=self.api_key, **_network_bounds())
        self.model = model

    def complete(self, messages: List[Dict[str, str]], tools: Optional[List[Dict[str, Any]]] = None, **kwargs) -> LLMResponse:
        """Complete a conversation with optional tool support."""
        api_kwargs = {
            "model": self.model,
            "messages": messages,
            **kwargs  # Pass through user kwargs (max_tokens, temperature, etc.)
        }

        if tools:
            api_kwargs["tools"] = [{"type": "function", "function": tool} for tool in tools]
            api_kwargs["tool_choice"] = "auto"

        response = self._call_provider(
            lambda: self.client.chat.completions.create(**api_kwargs))
        message = response.choices[0].message

        # Parse tool calls if present
        tool_calls = []
        if hasattr(message, 'tool_calls') and message.tool_calls:
            for tc in message.tool_calls:
                tool_calls.append(ToolCall(
                    name=tc.function.name,
                    arguments=json.loads(tc.function.arguments),
                    id=tc.id
                ))

        # Extract token usage
        input_tokens = response.usage.prompt_tokens
        output_tokens = response.usage.completion_tokens
        cached_tokens = response.usage.prompt_tokens_details.cached_tokens if response.usage.prompt_tokens_details else 0
        cost = calculate_cost(self.model, input_tokens, output_tokens, cached_tokens)

        return LLMResponse(
            content=message.content,
            tool_calls=tool_calls,
            raw_response=response,
            usage=TokenUsage(
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cached_tokens=cached_tokens,
                cost=cost,
            ),
        )

    def structured_complete(self, messages: List[Dict], output_schema: Type[BaseModel], **kwargs) -> BaseModel:
        """Get structured Pydantic output using OpenAI's native responses.parse API.

        Uses the new OpenAI responses.parse() endpoint with text_format parameter
        for guaranteed schema adherence.
        """
        response = self.client.responses.parse(
            model=self.model,
            input=messages,
            text_format=output_schema,
            **kwargs  # Pass through temperature, max_tokens, etc.
        )

        # Handle edge cases
        if response.status == "incomplete":
            if response.incomplete_details.reason == "max_output_tokens":
                raise ValueError("Response incomplete: maximum output tokens reached")
            elif response.incomplete_details.reason == "content_filter":
                raise ValueError("Response incomplete: content filtered")

        # Check for refusal
        if response.output and len(response.output) > 0:
            first_content = response.output[0].content[0] if response.output[0].content else None
            if first_content and hasattr(first_content, 'type') and first_content.type == "refusal":
                raise ValueError(f"Model refused to respond: {first_content.refusal}")

        # Return the parsed Pydantic object
        return response.output_parsed


class AnthropicLLM(LLM):
    """Anthropic Claude LLM implementation."""

    def __init__(self, api_key: Optional[str] = None, model: str = "claude-sonnet-4-20250514", max_tokens: int = 8192, **kwargs):
        import anthropic
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        if not self.api_key:
            raise ValueError("Anthropic API key required. Set ANTHROPIC_API_KEY environment variable or pass api_key parameter.")

        self.client = anthropic.Anthropic(api_key=self.api_key, **_network_bounds())
        self.model = model
        self.max_tokens = max_tokens  # Anthropic requires max_tokens (default 8192)

    def complete(self, messages: List[Dict[str, Any]], tools: Optional[List[Dict[str, Any]]] = None, **kwargs) -> LLMResponse:
        """Complete a conversation with optional tool support."""
        # Convert messages to Anthropic format
        anthropic_messages, system = self._convert_messages(messages)

        api_kwargs = {
            "model": self.model,
            "messages": anthropic_messages,
            "max_tokens": self.max_tokens,  # Required by Anthropic
            **kwargs  # User can override max_tokens via kwargs
        }

        if system:
            api_kwargs["system"] = system

        # Add tools if provided
        if tools:
            api_kwargs["tools"] = self._convert_tools(tools)

        response = self._call_provider(
            lambda: self.client.messages.create(**api_kwargs))

        # Parse tool calls if present
        tool_calls = []
        content = ""

        for block in response.content:
            if block.type == "text":
                content += block.text
            elif block.type == "tool_use":
                tool_calls.append(ToolCall(
                    name=block.name,
                    arguments=block.input,
                    id=block.id
                ))

        # Extract token usage - Anthropic uses input_tokens/output_tokens
        input_tokens = response.usage.input_tokens
        output_tokens = response.usage.output_tokens
        cached_tokens = getattr(response.usage, 'cache_read_input_tokens', 0) or 0
        cache_write_tokens = getattr(response.usage, 'cache_creation_input_tokens', 0) or 0
        cost = calculate_cost(self.model, input_tokens, output_tokens, cached_tokens, cache_write_tokens)

        return LLMResponse(
            content=content if content else None,
            tool_calls=tool_calls,
            raw_response=response,
            usage=TokenUsage(
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cached_tokens=cached_tokens,
                cache_write_tokens=cache_write_tokens,
                cost=cost,
            ),
        )

    def structured_complete(self, messages: List[Dict], output_schema: Type[BaseModel], **kwargs) -> BaseModel:
        """Get structured Pydantic output using tool calling method.

        Anthropic doesn't have native Pydantic support yet, so we use a tool calling
        workaround: create a dummy tool with the Pydantic schema and force its use.
        """
        # Convert messages to Anthropic format
        anthropic_messages, system = self._convert_messages(messages)

        # Create a tool with the Pydantic schema as input_schema
        tool = {
            "name": "return_structured_output",
            "description": "Returns the structured output based on the user's request",
            "input_schema": output_schema.model_json_schema()
        }

        # Set max_tokens with safe default
        api_kwargs = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "messages": anthropic_messages,
            "tools": [tool],
            "tool_choice": {"type": "tool", "name": "return_structured_output"},
            **kwargs  # User can override max_tokens, temperature, etc.
        }

        if system:
            api_kwargs["system"] = system

        # Force the model to use this tool
        response = self._call_provider(
            lambda: self.client.messages.create(**api_kwargs))

        # Extract structured data from tool call
        for block in response.content:
            if block.type == "tool_use" and block.name == "return_structured_output":
                # Validate and return as Pydantic model
                return output_schema.model_validate(block.input)

        raise ValueError("No structured output received from Claude")

    def _convert_messages(self, messages: List[Dict[str, Any]]) -> tuple[List[Dict[str, Any]], Optional[str]]:
        """Convert OpenAI-style messages to Anthropic format."""
        anthropic_messages = []
        system_parts = []
        i = 0

        while i < len(messages):
            msg = messages[i]

            # Anthropic accepts system instructions as a top-level request parameter.
            if msg["role"] == "system":
                if msg.get("content"):
                    system_parts.append(msg["content"])
                i += 1
                continue

            # Handle assistant messages with tool calls
            if msg["role"] == "assistant" and msg.get("tool_calls"):
                content_blocks = []
                if msg.get("content"):
                    content_blocks.append({
                        "type": "text",
                        "text": msg["content"]
                    })

                for tc in msg["tool_calls"]:
                    content_blocks.append({
                        "type": "tool_use",
                        "id": tc["id"],
                        "name": tc["function"]["name"],
                        "input": json.loads(tc["function"]["arguments"]) if isinstance(tc["function"]["arguments"], str) else tc["function"]["arguments"]
                    })

                anthropic_messages.append({
                    "role": "assistant",
                    "content": content_blocks
                })

                # Now collect all the tool responses that follow immediately
                i += 1
                tool_results = []
                while i < len(messages) and messages[i]["role"] == "tool":
                    tool_msg = messages[i]
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tool_msg["tool_call_id"],
                        "content": tool_msg["content"]
                    })
                    i += 1

                # Add all tool results in a single user message
                if tool_results:
                    anthropic_messages.append({
                        "role": "user",
                        "content": tool_results
                    })

            # Handle tool role messages that aren't immediately after assistant tool calls
            elif msg["role"] == "tool":
                # This shouldn't happen in normal flow, but handle it just in case
                anthropic_messages.append({
                    "role": "user",
                    "content": [{
                        "type": "tool_result",
                        "tool_use_id": msg["tool_call_id"],
                        "content": msg["content"]
                    }]
                })
                i += 1

            # Handle user messages
            elif msg["role"] == "user":
                if isinstance(msg.get("content"), list):
                    # This is already a structured message
                    anthropic_msg = {
                        "role": "user",
                        "content": []
                    }
                    for item in msg["content"]:
                        if item.get("type") == "tool_result":
                            anthropic_msg["content"].append({
                                "type": "tool_result",
                                "tool_use_id": item["tool_call_id"],
                                "content": item["content"]
                            })
                    anthropic_messages.append(anthropic_msg)
                else:
                    # Regular text message
                    anthropic_messages.append({
                        "role": "user",
                        "content": msg["content"]
                    })
                i += 1

            # Handle regular assistant messages
            elif msg["role"] == "assistant":
                anthropic_messages.append({
                    "role": "assistant",
                    "content": msg["content"]
                })
                i += 1

            else:
                i += 1

        system = "\n\n".join(system_parts)
        return anthropic_messages, system or None

    def _convert_tools(self, tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Convert OpenAI-style tools to Anthropic format."""
        anthropic_tools = []

        for tool in tools:
            # Tools already in our internal format
            anthropic_tool = {
                "name": tool["name"],
                "description": tool.get("description", ""),
                "input_schema": tool.get("parameters", {
                    "type": "object",
                    "properties": {},
                    "required": []
                })
            }
            anthropic_tools.append(anthropic_tool)

        return anthropic_tools


_GEMINI_38_SAMPLING_PARAMETERS = ("temperature", "top_p", "top_k", "candidate_count")
_GEMINI_38_REASONING_LEVELS = frozenset({"low", "medium", "high"})


def _normalize_gemini_chat_kwargs(model: str, kwargs: Dict[str, Any]) -> Dict[str, Any]:
    """Keep Gemini 3.8 calls within Google's OpenAI-compatibility contract."""
    normalized = dict(kwargs)
    # This abstraction returns one complete LLMResponse. Keep an accidental
    # OpenAI stream flag from changing the SDK return type underneath it;
    # managed calls enforce the same complete-response boundary in oo-api.
    normalized.pop("stream", None)
    normalized.pop("stream_options", None)
    if model != "gemini-3.8-flash":
        return normalized

    ignored = [
        parameter
        for parameter in _GEMINI_38_SAMPLING_PARAMETERS
        if parameter in normalized
    ]
    for parameter in ignored:
        normalized.pop(parameter)
    if ignored:
        logger.warning(
            "Gemini 3.8 Flash ignores deprecated sampling parameters: %s",
            ", ".join(ignored),
        )

    if "thinking_budget" in normalized:
        raise ValueError(
            "gemini-3.8-flash does not accept thinking_budget; use "
            "reasoning_effort='low', 'medium', or 'high'"
        )
    effort = normalized.get("reasoning_effort")
    if effort is not None and effort not in _GEMINI_38_REASONING_LEVELS:
        raise ValueError(
            "gemini-3.8-flash reasoning_effort must be 'low', 'medium', or 'high'"
        )
    return normalized


class GeminiLLM(LLM):
    """Google Gemini LLM implementation using OpenAI-compatible endpoint."""

    # gemini-2.0-flash-exp was the default and Google has retired it: a bare
    # GeminiLLM(api_key=...) answered 404 for every call.
    def __init__(self, api_key: Optional[str] = None, model: str = DEFAULT_DIRECT_GEMINI_MODEL, **kwargs):
        import openai
        self.api_key = api_key or os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        if not self.api_key:
            raise ValueError("Gemini API key required. Set GEMINI_API_KEY environment variable or pass api_key parameter. (GOOGLE_API_KEY is also supported for backward compatibility)")

        # Use Gemini's OpenAI-compatible endpoint
        self.client = openai.OpenAI(
            api_key=self.api_key,
            base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
            **_network_bounds(),
        )
        self.model = model

    def complete(self, messages: List[Dict[str, Any]], tools: Optional[List[Dict[str, Any]]] = None, **kwargs) -> LLMResponse:
        """Complete a conversation using Gemini's OpenAI-compatible endpoint."""
        kwargs = _normalize_gemini_chat_kwargs(self.model, kwargs)
        api_kwargs = {
            "model": self.model,
            "messages": messages,
            **kwargs
        }

        if tools:
            api_kwargs["tools"] = [{"type": "function", "function": tool} for tool in tools]
            api_kwargs["tool_choice"] = "auto"

        response = self._call_provider(
            lambda: self.client.chat.completions.create(**api_kwargs))
        message = response.choices[0].message

        # Parse tool calls if present
        # Preserve extra_content for providers that need it (e.g., Gemini 3 thought_signature)
        tool_calls = []
        if hasattr(message, 'tool_calls') and message.tool_calls:
            for tc in message.tool_calls:
                extra = getattr(tc, 'extra_content', None)
                tool_calls.append(ToolCall(
                    name=tc.function.name,
                    arguments=json.loads(tc.function.arguments) if isinstance(tc.function.arguments, str) else tc.function.arguments,
                    id=tc.id,
                    extra_content=extra
                ))

        # Extract token usage (OpenAI-compatible format)
        usage = None
        if hasattr(response, 'usage') and response.usage:
            input_tokens = response.usage.prompt_tokens
            output_tokens = response.usage.completion_tokens
            cached_tokens = 0
            if hasattr(response.usage, 'prompt_tokens_details') and response.usage.prompt_tokens_details:
                cached_tokens = getattr(response.usage.prompt_tokens_details, 'cached_tokens', 0) or 0
            cost = calculate_cost(self.model, input_tokens, output_tokens, cached_tokens)
            usage = TokenUsage(
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cached_tokens=cached_tokens,
                cost=cost,
            )

        return LLMResponse(
            content=message.content,
            tool_calls=tool_calls,
            raw_response=response,
            usage=usage,
        )

    def structured_complete(self, messages: List[Dict], output_schema: Type[BaseModel], **kwargs) -> BaseModel:
        """Get structured Pydantic output using Gemini's OpenAI-compatible endpoint with beta.chat.completions.parse."""
        kwargs = _normalize_gemini_chat_kwargs(self.model, kwargs)
        completion = self._call_provider(lambda: self.client.beta.chat.completions.parse(
            model=self.model,
            messages=messages,
            response_format=output_schema,
            **kwargs
        ))
        return completion.choices[0].message.parsed


class GroqLLM(LLM):
    """Groq LLM implementation using OpenAI-compatible endpoint."""

    def __init__(self, api_key: Optional[str] = None, model: str = "groq/llama-3.3-70b-versatile", **kwargs):
        import openai
        self.api_key = api_key or os.getenv("GROQ_API_KEY")
        if not self.api_key:
            raise ValueError("Groq API key required. Set GROQ_API_KEY environment variable or pass api_key parameter.")

        self.model = model.removeprefix("groq/")
        self.client = openai.OpenAI(
            api_key=self.api_key,
            base_url="https://api.groq.com/openai/v1",
            **_network_bounds(),
        )

    def complete(self, messages: List[Dict[str, Any]], tools: Optional[List[Dict[str, Any]]] = None, **kwargs) -> LLMResponse:
        """Complete a conversation using Groq's OpenAI-compatible endpoint."""
        api_kwargs = {
            "model": self.model,
            "messages": messages,
            **kwargs
        }

        if tools:
            api_kwargs["tools"] = [{"type": "function", "function": tool} for tool in tools]
            api_kwargs["tool_choice"] = "auto"

        response = self._call_provider(
            lambda: self.client.chat.completions.create(**api_kwargs))

        message = response.choices[0].message

        tool_calls = []
        if hasattr(message, 'tool_calls') and message.tool_calls:
            for tc in message.tool_calls:
                tool_calls.append(ToolCall(
                    name=tc.function.name,
                    arguments=json.loads(tc.function.arguments) if isinstance(tc.function.arguments, str) else tc.function.arguments,
                    id=tc.id
                ))

        usage = None
        if hasattr(response, 'usage') and response.usage:
            input_tokens = response.usage.prompt_tokens
            output_tokens = response.usage.completion_tokens
            cost = calculate_cost(self.model, input_tokens, output_tokens)
            usage = TokenUsage(
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost=cost,
            )

        return LLMResponse(content=message.content, tool_calls=tool_calls, raw_response=response, usage=usage)

    def structured_complete(self, messages: List[Dict], output_schema: Type[BaseModel], **kwargs) -> BaseModel:
        """Get structured Pydantic output using JSON-mode + schema validation.

        Uses chat.completions with JSON response format for compatibility with
        OpenAI-like providers that may not support beta parse endpoints.
        """
        schema_json = json.dumps(output_schema.model_json_schema(), indent=2)
        schema_instruction = (
            "Return ONLY valid JSON (no markdown) that matches this JSON Schema:\n"
            f"{schema_json}"
        )

        structured_messages = [{"role": "system", "content": schema_instruction}, *messages]

        completion = self._call_provider(lambda: self.client.chat.completions.create(
            model=self.model,
            messages=structured_messages,
            response_format={"type": "json_object"},
            **kwargs,
        ))
        content = completion.choices[0].message.content or "{}"
        return output_schema.model_validate_json(content)


class GrokLLM(LLM):
    """Grok (xAI) LLM implementation using OpenAI-compatible endpoint."""

    def __init__(self, api_key: Optional[str] = None, model: str = "grok/grok-4", **kwargs):
        import openai
        self.api_key = api_key or os.getenv("XAI_API_KEY")
        if not self.api_key:
            raise ValueError("Grok API key required. Set XAI_API_KEY environment variable or pass api_key parameter.")

        self.model = model.removeprefix("grok/")
        self.client = openai.OpenAI(
            api_key=self.api_key,
            base_url="https://api.x.ai/v1",
            **_network_bounds(),
        )

    def complete(self, messages: List[Dict[str, Any]], tools: Optional[List[Dict[str, Any]]] = None, **kwargs) -> LLMResponse:
        """Complete a conversation using Grok's OpenAI-compatible endpoint."""
        api_kwargs = {
            "model": self.model,
            "messages": messages,
            **kwargs
        }

        if tools:
            api_kwargs["tools"] = [{"type": "function", "function": tool} for tool in tools]
            api_kwargs["tool_choice"] = "auto"

        response = self._call_provider(
            lambda: self.client.chat.completions.create(**api_kwargs))
        message = response.choices[0].message

        tool_calls = []
        if hasattr(message, 'tool_calls') and message.tool_calls:
            for tc in message.tool_calls:
                tool_calls.append(ToolCall(
                    name=tc.function.name,
                    arguments=json.loads(tc.function.arguments) if isinstance(tc.function.arguments, str) else tc.function.arguments,
                    id=tc.id
                ))

        usage = None
        if hasattr(response, 'usage') and response.usage:
            input_tokens = response.usage.prompt_tokens
            output_tokens = response.usage.completion_tokens
            cost = calculate_cost(self.model, input_tokens, output_tokens)
            usage = TokenUsage(
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost=cost,
            )

        return LLMResponse(content=message.content, tool_calls=tool_calls, raw_response=response, usage=usage)

    def structured_complete(self, messages: List[Dict], output_schema: Type[BaseModel], **kwargs) -> BaseModel:
        """Get structured Pydantic output using JSON-mode + schema validation."""
        schema_json = json.dumps(output_schema.model_json_schema(), indent=2)
        schema_instruction = (
            "Return ONLY valid JSON (no markdown) that matches this JSON Schema:\n"
            f"{schema_json}"
        )

        structured_messages = [{"role": "system", "content": schema_instruction}, *messages]

        completion = self._call_provider(lambda: self.client.chat.completions.create(
            model=self.model,
            messages=structured_messages,
            response_format={"type": "json_object"},
            **kwargs,
        ))
        content = completion.choices[0].message.content or "{}"
        return output_schema.model_validate_json(content)


class OpenRouterLLM(LLM):
    """OpenRouter LLM implementation using OpenAI-compatible endpoint."""

    def __init__(self, api_key: Optional[str] = None, model: str = "openrouter/openai/o4-mini", **kwargs):
        import openai
        self.api_key = api_key or os.getenv("OPENROUTER_API_KEY")
        if not self.api_key:
            raise ValueError("OpenRouter API key required. Set OPENROUTER_API_KEY environment variable or pass api_key parameter.")

        self.model = model.removeprefix("openrouter/")

        # OpenRouter recommends these optional headers for request attribution.
        default_headers = {}
        if os.getenv("OPENROUTER_HTTP_REFERER"):
            default_headers["HTTP-Referer"] = os.getenv("OPENROUTER_HTTP_REFERER")
        if os.getenv("OPENROUTER_X_TITLE"):
            default_headers["X-Title"] = os.getenv("OPENROUTER_X_TITLE")

        client_kwargs = {
            "api_key": self.api_key,
            "base_url": "https://openrouter.ai/api/v1",
            **_network_bounds(),
        }
        if default_headers:
            client_kwargs["default_headers"] = default_headers

        self.client = openai.OpenAI(**client_kwargs)

    def complete(self, messages: List[Dict[str, Any]], tools: Optional[List[Dict[str, Any]]] = None, **kwargs) -> LLMResponse:
        """Complete a conversation using OpenRouter's OpenAI-compatible endpoint."""
        api_kwargs = {
            "model": self.model,
            "messages": messages,
            **kwargs
        }

        if tools:
            api_kwargs["tools"] = [{"type": "function", "function": tool} for tool in tools]
            api_kwargs["tool_choice"] = "auto"

        response = self._call_provider(
            lambda: self.client.chat.completions.create(**api_kwargs))
        message = response.choices[0].message

        tool_calls = []
        if hasattr(message, 'tool_calls') and message.tool_calls:
            for tc in message.tool_calls:
                tool_calls.append(ToolCall(
                    name=tc.function.name,
                    arguments=json.loads(tc.function.arguments) if isinstance(tc.function.arguments, str) else tc.function.arguments,
                    id=tc.id
                ))

        usage = None
        if hasattr(response, 'usage') and response.usage:
            input_tokens = response.usage.prompt_tokens
            output_tokens = response.usage.completion_tokens
            cost = calculate_cost(self.model, input_tokens, output_tokens)
            usage = TokenUsage(
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost=cost,
            )

        return LLMResponse(content=message.content, tool_calls=tool_calls, raw_response=response, usage=usage)

    def structured_complete(self, messages: List[Dict], output_schema: Type[BaseModel], **kwargs) -> BaseModel:
        """Get structured Pydantic output using JSON-mode + schema validation.

        Uses chat.completions with JSON response format for compatibility with
        OpenAI-like providers that may not support beta parse endpoints.
        """
        schema_json = json.dumps(output_schema.model_json_schema(), indent=2)
        schema_instruction = (
            "Return ONLY valid JSON (no markdown) that matches this JSON Schema:\n"
            f"{schema_json}"
        )

        structured_messages = [{"role": "system", "content": schema_instruction}, *messages]

        completion = self._call_provider(lambda: self.client.chat.completions.create(
            model=self.model,
            messages=structured_messages,
            response_format={"type": "json_object"},
            **kwargs,
        ))
        content = completion.choices[0].message.content or "{}"
        return output_schema.model_validate_json(content)


class MistralLLM(LLM):
    """Mistral AI LLM implementation using OpenAI-compatible endpoint."""

    def __init__(self, api_key: Optional[str] = None, model: str = "mistral/mistral-large-latest", **kwargs):
        import openai
        self.api_key = api_key or os.getenv("MISTRAL_API_KEY")
        if not self.api_key:
            raise ValueError("Mistral API key required. Set MISTRAL_API_KEY environment variable or pass api_key parameter.")

        self.model = model.removeprefix("mistral/")
        self.client = openai.OpenAI(
            api_key=self.api_key,
            base_url="https://api.mistral.ai/v1",
            **_network_bounds(),
        )

    def complete(self, messages: List[Dict[str, Any]], tools: Optional[List[Dict[str, Any]]] = None, **kwargs) -> LLMResponse:
        """Complete a conversation using Mistral's OpenAI-compatible endpoint."""
        api_kwargs = {
            "model": self.model,
            "messages": messages,
            **kwargs
        }

        if tools:
            api_kwargs["tools"] = [{"type": "function", "function": tool} for tool in tools]
            api_kwargs["tool_choice"] = "auto"

        response = self._call_provider(
            lambda: self.client.chat.completions.create(**api_kwargs))
        message = response.choices[0].message

        tool_calls = []
        if hasattr(message, 'tool_calls') and message.tool_calls:
            for tc in message.tool_calls:
                tool_calls.append(ToolCall(
                    name=tc.function.name,
                    arguments=json.loads(tc.function.arguments) if isinstance(tc.function.arguments, str) else tc.function.arguments,
                    id=tc.id
                ))

        usage = None
        if hasattr(response, 'usage') and response.usage:
            input_tokens = response.usage.prompt_tokens
            output_tokens = response.usage.completion_tokens
            cost = calculate_cost(self.model, input_tokens, output_tokens)
            usage = TokenUsage(
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost=cost,
            )

        return LLMResponse(content=message.content, tool_calls=tool_calls, raw_response=response, usage=usage)

    def structured_complete(self, messages: List[Dict], output_schema: Type[BaseModel], **kwargs) -> BaseModel:
        """Get structured Pydantic output using JSON-mode + schema validation.

        Uses chat.completions with JSON response format for compatibility with
        OpenAI-like providers that may not support beta parse endpoints.
        """
        schema_json = json.dumps(output_schema.model_json_schema(), indent=2)
        schema_instruction = (
            "Return ONLY valid JSON (no markdown) that matches this JSON Schema:\n"
            f"{schema_json}"
        )

        structured_messages = [{"role": "system", "content": schema_instruction}, *messages]

        completion = self._call_provider(lambda: self.client.chat.completions.create(
            model=self.model,
            messages=structured_messages,
            response_format={"type": "json_object"},
            **kwargs,
        ))
        content = completion.choices[0].message.content or "{}"
        return output_schema.model_validate_json(content)


# Model registry mapping model names to providers
MODEL_REGISTRY = {
    # OpenAI models
    "o3-mini": "openai",
    "o4-mini": "openai",

    # Claude 4 models
    "claude-opus-4.1": "anthropic",
    "claude-opus-4-1-20250805": "anthropic",
    "claude-opus-4-1": "anthropic",  # Alias
    "claude-opus-4": "anthropic",
    "claude-opus-4-20250514": "anthropic",
    "claude-opus-4-0": "anthropic",  # Alias
    "claude-sonnet-4": "anthropic",
    "claude-sonnet-4-20250514": "anthropic",
    "claude-sonnet-4-0": "anthropic",  # Alias
    "claude-3-7-sonnet-latest": "anthropic",
    "claude-3-7-sonnet-20250219": "anthropic",

    # Google Gemini models
    "gemini-3.8-flash": "google",
    "gemini-3.7-flash": "google",
    "gemini-3.6-flash": "google",
    "gemini-3.5-flash": "google",
    "gemini-3-pro-image-preview": "google",
    "gemini-2.5-pro": "google",
    "gemini-2.5-flash": "google",
    # gemini-3-pro-preview, gemini-2.0-flash-exp and gemini-2.0-flash-thinking-exp
    # used to be here. Google answers each with 404 "no longer available", and
    # -flash-exp was this module's own GeminiLLM default, so a bare
    # GeminiLLM(api_key=...) could not complete a call.
    #
    # Removing them does not stop anyone selecting them: create_llm falls
    # through to the prefix branch below and a `gemini-` name routes regardless.
    # This table is the curated list — what we vouch for and price — so what
    # dropping them buys is that we no longer recommend a dead name.
    #
    # Note that ListModels still advertises gemini-3-pro-preview and
    # gemini-2.0-flash. Being listed is not being callable, which is why
    # test_the_registry_offers_models_that_exist sends a real request per model
    # instead of comparing against that list.
}


def _response_mapping(value: Any) -> dict:
    """Read SDK-preserved extension objects without depending on one SDK type."""
    if isinstance(value, dict):
        return value
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        dumped = model_dump()
        return dumped if isinstance(dumped, dict) else {}
    if hasattr(value, "__dict__"):
        return {
            key: item
            for key, item in vars(value).items()
            if not key.startswith("_")
        }
    return {}


def _managed_token_usage(raw_usage: Any, model: str) -> TokenUsage:
    """Keep the managed server's measured usage and charge as one contract."""
    normalized = _response_mapping(getattr(raw_usage, "normalized", None))
    cost_details = _response_mapping(getattr(raw_usage, "cost_details", None))

    if normalized:
        input_tokens = int(normalized["input_tokens_total"])
        output_tokens = int(normalized["output_tokens"])
        cache_read = int(normalized.get("cache_read_input_tokens", 0))
        cache_write = int(normalized.get("cache_write_input_tokens", 0))
        cost = getattr(raw_usage, "cost_usd", None)
        if cost is None:
            cost = calculate_cost(
                model, input_tokens, output_tokens, cache_read, cache_write
            )
        provider_cost = normalized.get("provider_reported_cost_usd")
        return TokenUsage(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cached_tokens=cache_read,
            cache_write_tokens=cache_write,
            cost=float(cost),
            total_tokens=input_tokens + output_tokens,
            input_tokens_total=input_tokens,
            input_tokens_uncached=int(normalized["input_tokens_uncached"]),
            cache_read_input_tokens=cache_read,
            cache_write_input_tokens=cache_write,
            cache_write_5m_input_tokens=int(
                normalized.get("cache_write_5m_input_tokens", 0)
            ),
            cache_write_1h_input_tokens=int(
                normalized.get("cache_write_1h_input_tokens", 0)
            ),
            cache_metadata_status=normalized.get("cache_metadata_status"),
            provider=normalized.get("provider"),
            requested_model=normalized.get("requested_model"),
            provider_model=normalized.get("provider_model"),
            provider_reported_cost_usd=(
                float(provider_cost) if provider_cost is not None else None
            ),
            pricing_version=cost_details.get("pricing_version"),
            pricing_tier=cost_details.get("pricing_tier"),
            cost_details=cost_details or None,
        )

    # Compatibility with older oo-api deployments: preserve their OpenAI shape
    # and prefer the server's cost when present.
    input_tokens = raw_usage.prompt_tokens
    output_tokens = raw_usage.completion_tokens
    details = getattr(raw_usage, "prompt_tokens_details", None)
    cached_tokens = getattr(details, "cached_tokens", 0) or 0
    cost = getattr(raw_usage, "cost_usd", None)
    if cost is None:
        cost = calculate_cost(model, input_tokens, output_tokens, cached_tokens)
    server_total = getattr(raw_usage, "total_tokens", 0) or 0
    return TokenUsage(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cached_tokens=cached_tokens,
        cost=cost,
        total_tokens=(
            server_total if server_total > input_tokens + output_tokens else 0
        ),
    )


class OpenOnionLLM(LLM):
    """OpenOnion managed keys LLM implementation using OpenAI-compatible API."""

    def __init__(self, api_key: Optional[str] = None, model: str = DEFAULT_MODEL, **kwargs):
        # For co/ models, api_key is actually the auth token
        # Framework auto-loads .env, so OPENONION_API_KEY will be in environment
        import openai
        if api_key:
            # Explicit dependency injection is caller-owned. Only the implicit
            # environment fallback is checked against the local project.
            self.auth_token = api_key
        else:
            from ..credentials import require_ambient_api_key

            self.auth_token = require_ambient_api_key()

        # Strip co/ prefix - it's only for client-side routing
        self.model = model.removeprefix("co/")

        # All managed services share the same selected backend (#733).
        self.base_url = f"{backend_url()}/v1"

        # Use OpenAI client with OpenOnion endpoint.
        # SDK default connect timeout is 5s with 2 retries; one transient network
        # blip killed whole agent runs with APITimeoutError, so allow 20s connects
        # and more retries.
        self.client = openai.OpenAI(
            base_url=self.base_url,
            api_key=self.auth_token,
            **_network_bounds(max_retries=5),
        )

    def complete(self, messages: List[Dict[str, Any]], tools: Optional[List[Dict[str, Any]]] = None, **kwargs) -> LLMResponse:
        """Complete a conversation with optional tool support using OpenAI-compatible API."""
        api_kwargs = {
            "model": self.model,
            "messages": messages,
            **kwargs  # Pass through user kwargs (temperature, max_tokens, etc.)
        }

        # Add tools if provided
        if tools:
            api_kwargs["tools"] = [{"type": "function", "function": tool} for tool in tools]
            api_kwargs["tool_choice"] = "auto"

        response = self._call(lambda: self.client.chat.completions.create(**api_kwargs))

        message = response.choices[0].message

        # Parse tool calls if present
        # Preserve extra_content for providers that need it (e.g., Gemini 3 thought_signature)
        tool_calls = []
        if hasattr(message, 'tool_calls') and message.tool_calls:
            for tc in message.tool_calls:
                extra = getattr(tc, 'extra_content', None)
                tool_calls.append(ToolCall(
                    name=tc.function.name,
                    arguments=json.loads(tc.function.arguments) if isinstance(tc.function.arguments, str) else tc.function.arguments,
                    id=tc.id,
                    extra_content=extra
                ))

        usage = (
            _managed_token_usage(response.usage, self.model)
            if hasattr(response, 'usage') and response.usage
            else None
        )

        return LLMResponse(
            content=message.content,
            tool_calls=tool_calls,
            raw_response=response,
            usage=usage,
        )

    def _call(self, send):
        """Make one request and translate the failures callers are written against.

        Shared by complete() and structured_complete(), because a depleted
        balance is a depleted balance whichever one you called. structured_complete()
        had no handling at all, so the documented InsufficientCreditsError — the
        one carrying balance, required, shortfall and address — surfaced as a raw
        openai.APIStatusError, and every `except InsufficientCreditsError` written
        against the documented behaviour missed it.

        One helper rather than a copied block: two copies of a translation table
        drift, and the half that drifts is the half nobody tested.
        """
        import openai
        try:
            return send()
        except openai.APIStatusError as e:
            if e.status_code == 402:
                raise InsufficientCreditsError(e) from e
            elif e.status_code == 503:
                raise ProviderServiceError(e) from e
            elif e.status_code == 403 and _is_paid_account_required(e):
                # Keyed on the backend's own error code, not on the status: a
                # 403 can mean other things, and guessing from the status alone
                # would tell a suspended account to go buy credits.
                raise PaidModelRequiredError(e) from e
            elif e.status_code == 401:
                # Managed-provider credentials live on oo-api, not on the
                # caller's machine. Still use the shared provider-error family
                # so library and CLI callers can handle this without depending
                # on an OpenAI-compatible transport implementation.
                raise LLMAuthenticationError(e, model=f"co/{self.model}") from e
            logger.error(f"APIStatusError: status={e.status_code}, message={e.message}, body={getattr(e, 'body', None)}")
            raise
        except (openai.APITimeoutError, openai.APIConnectionError) as e:
            raise LLMConnectionError(e, model=f"co/{self.model}", base_url=self.base_url) from e
        except Exception as e:
            logger.error(f"LLM error: {type(e).__name__}: {e}")
            raise

    def structured_complete(self, messages: List[Dict], output_schema: Type[BaseModel], **kwargs) -> BaseModel:
        """Get structured Pydantic output using OpenAI-compatible chat completions API.

        Uses beta.chat.completions.parse() which routes through /v1/chat/completions,
        allowing proper provider routing for Gemini, OpenAI, and other models.
        """
        completion = self._call(lambda: self.client.beta.chat.completions.parse(
            model=self.model,
            messages=messages,
            response_format=output_schema,
            **kwargs
        ))
        return completion.choices[0].message.parsed

    def get_balance(self) -> Optional[float]:
        """Fetch current account balance from OpenOnion API.

        Makes a GET request to /api/v1/auth/me endpoint to retrieve the user's
        current balance. This is called once at agent startup to display balance
        in the banner.

        Returns:
            Balance in USD (e.g., 4.22 for $4.22), or None if request fails

        Note:
            - Fast timeout (5s) to avoid hanging on network issues
            - Only called for co/ models (OpenOnion managed keys)
            - Returns None on any error (network, auth, etc.)
            - ~200ms typical latency, acceptable for startup
        """

        # Build auth endpoint URL (strip /v1 suffix)
        auth_url = f"{self.base_url.rstrip('/v1')}/api/v1/auth/me"

        # 15s timeout: balance ~200ms typical, but proxy/VPN users need more headroom
        # Network errors return None — balance is non-critical banner info
        try:
            response = requests.get(
                auth_url,
                headers={"Authorization": f"Bearer {self.auth_token}"},
                timeout=15
            )
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError):
            return None

        if response.status_code == 200:
            data = response.json()
            return data.get("balance_usd")

        return None


# OpenAI's reasoning models, matched by explicit prefix.
#
# A bare startswith("o") sent every unprefixed model beginning with the letter o
# to OpenAI — "orca-2-13b" and "olmo" are real open-model names, and the caller
# got an OpenAI 404 for a model they never asked OpenAI about, with nothing
# pointing at the routing as the cause. Naming the families keeps a new one a
# one-line addition here, which is the only place it should need to be made.
OPENAI_REASONING_PREFIXES = ("o1", "o3", "o4")


def create_llm(model: str, api_key: Optional[str] = None, **kwargs) -> LLM:
    """Factory function to create the appropriate LLM based on model name.
    
    Args:
        model: The model name (e.g., "o4-mini", "claude-sonnet-4-20250514", "gemini-3.8-flash")
        api_key: Optional API key to override environment variable
        **kwargs: Additional arguments to pass to the LLM constructor
    
    Returns:
        An LLM instance for the specified model
    
    Raises:
        ValueError: If the model is not recognized
    """
    # Check if it's a co/ model (OpenOnion managed keys)
    if model.startswith("co/"):
        return OpenOnionLLM(api_key=api_key, model=model, **kwargs)

    # Explicit provider prefixes for OpenAI-compatible third-party providers
    if model.startswith("groq/"):
        return GroqLLM(api_key=api_key, model=model, **kwargs)
    if model.startswith("openrouter/"):
        return OpenRouterLLM(api_key=api_key, model=model, **kwargs)
    if model.startswith("grok/"):
        return GrokLLM(api_key=api_key, model=model, **kwargs)
    if model.startswith("mistral/"):
        return MistralLLM(api_key=api_key, model=model, **kwargs)

    # Get provider from registry
    provider = MODEL_REGISTRY.get(model)

    if not provider:
        # Try to infer provider from model name
        if model.startswith("gpt") or model.startswith(OPENAI_REASONING_PREFIXES):
            provider = "openai"
        elif model.startswith("claude"):
            provider = "anthropic"
        elif model.startswith("gemini"):
            provider = "google"
        else:
            raise ValueError(f"Unknown model '{model}'")

    # Create the appropriate LLM
    if provider == "openai":
        return OpenAILLM(api_key=api_key, model=model, **kwargs)
    elif provider == "anthropic":
        return AnthropicLLM(api_key=api_key, model=model, **kwargs)
    elif provider == "google":
        return GeminiLLM(api_key=api_key, model=model, **kwargs)
    else:
        raise ValueError(f"Provider '{provider}' not implemented")

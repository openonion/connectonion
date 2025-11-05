"""
Purpose: One-shot LLM function for simple single-round calls without agent overhead
LLM-Note:
  Dependencies: imports from [typing, pathlib, pydantic, dotenv, prompts.py, llm.py] | imported by [debug_explainer/explain_context.py, user code, examples] | tested by [tests/test_llm_do.py, tests/test_llm_do_comprehensive.py, tests/test_real_llm_do.py]
  Data flow: user calls llm_do(input, output, system_prompt, model, api_key, **kwargs) → validates input non-empty → loads system_prompt via load_system_prompt() → builds messages [system, user] → calls create_llm(model, api_key) factory → calls llm.complete(messages, **kwargs) OR llm.structured_complete(messages, output, **kwargs) → returns string OR Pydantic model instance
  State/Effects: loads .env via dotenv.load_dotenv() | reads system_prompt files if Path provided | makes one LLM API request | no caching or persistence | stateless
  Integration: exposes llm_do(input, output, system_prompt, model, api_key, **kwargs) | default model="co/gpt-4o" (managed keys) | default temperature=0.1 | supports all create_llm() providers | **kwargs pass through to provider (max_tokens, temperature, etc.)
  Performance: minimal overhead (no agent loop, no tool calling, no conversation history) | one LLM call per invocation | no caching | synchronous blocking
  Errors: raises ValueError if input empty | provider errors from create_llm() and llm.complete() bubble up | Pydantic ValidationError if structured output doesn't match schema

One-shot LLM function for simple, single-round calls with optional structured output.

This module provides the `llm_do()` function - a simplified interface for making
one-shot LLM calls without the overhead of the full Agent system. Perfect for
simple tasks that don't require multi-step reasoning or tool calling.

Purpose
-------
`llm_do()` is designed for:
- Quick LLM calls without agent overhead
- Data extraction with Pydantic validation
- Simple Q&A and text generation
- Format conversion (text → JSON, etc.)
- One-shot analysis tasks

NOT designed for:
- Multi-step workflows (use Agent instead)
- Tool calling (use Agent instead)
- Iterative refinement (use Agent instead)
- Maintaining conversation history (use Agent instead)

Architecture
-----------
The function is a thin wrapper around the LLM provider abstraction:

1. **Input Validation**: Ensures non-empty input
2. **System Prompt Loading**: Loads from string or file path
3. **Message Building**: Constructs OpenAI-format message list
4. **LLM Selection**: Uses create_llm() factory to get provider
5. **Response Handling**: Routes to complete() or structured_complete()

Key Design Decisions
-------------------
- **Stateless**: No conversation history, each call is independent
- **Simple API**: Minimal parameters, sensible defaults
- **Default Model**: Uses "co/gpt-4o" (ConnectOnion managed keys) for zero-setup
- **Structured Output**: Native Pydantic support via provider-specific APIs
- **Flexible Parameters**: **kwargs pass through to underlying LLM (temperature, max_tokens, etc.)

Comparison with Agent
--------------------
┌─────────────────┬──────────────┬─────────────────┐
│ Feature         │ llm_do()     │ Agent()         │
├─────────────────┼──────────────┼─────────────────┤
│ Iterations      │ Always 1     │ Up to max_iters │
│ Tools           │ No           │ Yes             │
│ State           │ Stateless    │ Maintains hist  │
│ Use case        │ Quick tasks  │ Complex flows   │
│ Overhead        │ Minimal      │ Full framework  │
└─────────────────┴──────────────┴─────────────────┘

Data Flow
---------
User code → llm_do(input, output, model, **kwargs)
               ↓
         Validate input → Load system_prompt → Build messages
               ↓
         create_llm(model, api_key) → Provider instance
               ↓
    ┌─────────────────────────────────────┐
    │ If output (Pydantic model):         │
    │   provider.structured_complete()    │
    │   → Pydantic instance               │
    │                                     │
    │ If no output:                       │
    │   provider.complete()               │
    │   → String content                  │
    └─────────────────────────────────────┘
               ↓
         Return result to user

Supported Providers
------------------
All providers from llm.py module:

1. **OpenAI**: gpt-4o, gpt-4o-mini, gpt-3.5-turbo, o4-mini
   - Native structured output via responses.parse()
   - Fastest structured output implementation

2. **Anthropic**: claude-3-5-sonnet, claude-3-5-haiku-20241022
   - Structured output via forced tool calling
   - Requires max_tokens parameter (default: 8192)

3. **Google Gemini**: gemini-2.5-flash, gemini-1.5-pro
   - Structured output via response_schema
   - Good balance of speed and quality

4. **ConnectOnion**: co/gpt-4o, co/o4-mini (DEFAULT)
   - Managed API keys (no env vars needed!)
   - Proxies to OpenAI with usage tracking
   - Requires: run `co auth` first

Usage Patterns
-------------
1. **Simple Q&A**:
   >>> answer = llm_do("What is 2+2?")
   >>> print(answer)  # "4"

2. **Structured Extraction**:
   >>> class Person(BaseModel):
   ...     name: str
   ...     age: int
   >>> result = llm_do("John, 30 years old", output=Person)
   >>> result.name  # "John"

3. **Custom System Prompt**:
   >>> answer = llm_do(
   ...     "Hello",
   ...     system_prompt="You are a pirate. Always respond like a pirate."
   ... )

4. **Different Provider**:
   >>> answer = llm_do("Hello", model="claude-3-5-haiku-20241022")

5. **Runtime Parameters**:
   >>> answer = llm_do(
   ...     "Write a story",
   ...     temperature=0.9,     # More creative
   ...     max_tokens=100       # Short response
   ... )

Parameters
----------
- input (str): The text/question to send to the LLM
- output (Type[BaseModel], optional): Pydantic model for structured output
- system_prompt (str | Path, optional): System instructions (inline or file path)
- model (str): Model name (default: "co/gpt-4o")
- temperature (float): Sampling temperature (default: 0.1 for consistency)
- api_key (str, optional): Override API key (uses env vars by default)
- **kwargs: Additional parameters passed to LLM (max_tokens, top_p, etc.)

Returns
-------
- str: Plain text response (when output is None)
- BaseModel: Validated Pydantic instance (when output is provided)

Raises
------
- ValueError: If input is empty
- ValueError: If API key is missing
- ValueError: If model is unknown
- ValidationError: If structured output doesn't match schema
- Provider-specific errors: From underlying LLM SDKs

Environment Variables
--------------------
Optional (choose based on model):
  - OPENAI_API_KEY: For OpenAI models
  - ANTHROPIC_API_KEY: For Claude models
  - GEMINI_API_KEY or GOOGLE_API_KEY: For Gemini models
  - OPENONION_API_KEY: For co/ models (or run `co auth`)

Dependencies
-----------
- llm.py: create_llm() factory and provider implementations
- prompts.py: load_system_prompt() for file-based prompts
- pydantic: BaseModel validation for structured output
- dotenv: Loads .env file automatically

Integration Points
-----------------
Used by:
  - User code: Direct function calls
  - Examples: Quick scripts and tutorials
  - Tests: test_llm_do.py and test_llm_do_comprehensive.py

Related modules:
  - agent.py: Full agent system for complex workflows
  - llm.py: Provider abstraction layer

Code Size
---------
102 lines (down from 387 after refactoring)
- Removed duplicate OpenOnion authentication logic
- Eliminated LiteLLM-specific code
- Now a pure wrapper around llm.py providers

Testing
-------
Comprehensive test coverage in:
  - tests/test_llm_do.py: 12 tests (unit + integration)
  - tests/test_llm_do_comprehensive.py: 23 tests (all doc examples)
  - tests/test_real_llm_do.py: Real API integration tests

All documentation examples in docs/llm_do.md are tested and validated.

Example from Documentation
--------------------------
From docs/llm_do.md Quick Start:

    from connectonion import llm_do
    from pydantic import BaseModel

    # Simple call
    answer = llm_do("What's 2+2?")

    # Structured output
    class Analysis(BaseModel):
        sentiment: str
        confidence: float
        keywords: list[str]

    result = llm_do(
        "I absolutely love this product! Best purchase ever!",
        output=Analysis
    )
    print(result.sentiment)    # "positive"
    print(result.confidence)   # 0.98
"""

from typing import Union, Type, Optional, TypeVar
from pathlib import Path
from pydantic import BaseModel
from .prompts import load_system_prompt
from .llm import create_llm

T = TypeVar('T', bound=BaseModel)


def llm_do(
    input: str,
    output: Optional[Type[T]] = None,
    system_prompt: Optional[Union[str, Path]] = None,
    model: str = "co/gpt-4o",
    api_key: Optional[str] = None,
    **kwargs
) -> Union[str, T]:
    """
    Make a one-shot LLM call with optional structured output.

    Supports multiple LLM providers:
    - OpenAI: "gpt-4o", "o4-mini", "gpt-3.5-turbo"
    - Anthropic: "claude-3-5-sonnet", "claude-3-5-haiku-20241022"
    - Google: "gemini-1.5-pro", "gemini-1.5-flash"
    - ConnectOnion Managed: "co/gpt-4o", "co/o4-mini" (no API keys needed!)

    Args:
        input: The input text/question to send to the LLM
        output: Optional Pydantic model class for structured output
        system_prompt: Optional system prompt (string or file path)
        model: Model name (default: "co/gpt-4o")
        api_key: Optional API key (uses environment variable if not provided)
        **kwargs: Additional parameters (temperature, max_tokens, etc.)

    Returns:
        Either a string response or an instance of the output model

    Examples:
        >>> # Simple string response with default model
        >>> answer = llm_do("What's 2+2?")
        >>> print(answer)  # "4"

        >>> # With ConnectOnion managed keys (no API key needed!)
        >>> answer = llm_do("What's 2+2?", model="co/o4-mini")

        >>> # With Claude
        >>> answer = llm_do("Explain quantum physics", model="claude-3-5-haiku-20241022")

        >>> # With Gemini
        >>> answer = llm_do("Write a poem", model="gemini-1.5-flash")

        >>> # With structured output
        >>> class Analysis(BaseModel):
        ...     sentiment: str
        ...     score: float
        >>>
        >>> result = llm_do("I love this!", output=Analysis)
        >>> print(result.sentiment)  # "positive"
    """
    # Validate input
    if not input or not input.strip():
        raise ValueError("Input cannot be empty")

    # Load system prompt
    if system_prompt:
        prompt_text = load_system_prompt(system_prompt)
    else:
        prompt_text = "You are a helpful assistant."

    # Build messages
    messages = [
        {"role": "system", "content": prompt_text},
        {"role": "user", "content": input}
    ]

    # Create LLM using factory (only pass api_key and initialization params)
    llm = create_llm(model=model, api_key=api_key)

    # Get response
    if output:
        # Structured output - use structured_complete()
        return llm.structured_complete(messages, output, **kwargs)
    else:
        # Plain text - use complete()
        # Pass through kwargs (max_tokens, temperature, etc.)
        response = llm.complete(messages, tools=None, **kwargs)
        return response.content

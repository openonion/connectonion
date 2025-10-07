"""One-shot LLM function for simple LLM calls with optional structured output.

Supports multiple LLM providers through unified interface:
- OpenAI (GPT models)
- Anthropic (Claude models)
- Google (Gemini models)
- ConnectOnion managed keys (co/ prefix)
"""

from typing import Union, Type, Optional, TypeVar
from pathlib import Path
from pydantic import BaseModel
from dotenv import load_dotenv
from .prompts import load_system_prompt
from .llm import create_llm

# Load environment variables from .env file
load_dotenv()

T = TypeVar('T', bound=BaseModel)


def llm_do(
    input: str,
    output: Optional[Type[T]] = None,
    system_prompt: Optional[Union[str, Path]] = None,
    model: str = "co/gpt-4o",
    temperature: float = 0.1,
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
        temperature: Sampling temperature (default: 0.1 for consistency)
        api_key: Optional API key (uses environment variable if not provided)
        **kwargs: Additional parameters to pass to the LLM

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
        return llm.structured_complete(messages, output, temperature=temperature, **kwargs)
    else:
        # Plain text - use complete()
        # Pass through kwargs (max_tokens, temperature, etc.)
        response = llm.complete(messages, tools=None, temperature=temperature, **kwargs)
        return response.content

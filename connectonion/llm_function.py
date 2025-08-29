"""One-shot LLM function for simple LLM calls with optional structured output."""

from typing import Union, Type, Optional, TypeVar
from pathlib import Path
from pydantic import BaseModel
import json
import os
from .prompts import load_system_prompt

T = TypeVar('T', bound=BaseModel)


def llm_do(
    input: str,
    output: Optional[Type[T]] = None,
    system_prompt: Optional[Union[str, Path]] = None,
    model: str = "gpt-4o-mini",
    temperature: float = 0.1,
    api_key: Optional[str] = None
) -> Union[str, T]:
    """
    Make a one-shot LLM call with optional structured output.
    
    Args:
        input: The input text/question to send to the LLM
        output: Optional Pydantic model class for structured output
        system_prompt: Optional system prompt (string or file path)
        model: OpenAI model to use (default: "gpt-4o-mini")
        temperature: Sampling temperature (default: 0.1 for consistency)
        api_key: Optional OpenAI API key (uses environment variable if not provided)
    
    Returns:
        Either a string response or an instance of the output model
    
    Examples:
        >>> # Simple string response
        >>> answer = llm("What's 2+2?")
        >>> print(answer)  # "4"
        
        >>> # With structured output
        >>> class Analysis(BaseModel):
        ...     sentiment: str
        ...     score: float
        >>> 
        >>> result = llm("I love this!", output=Analysis)
        >>> print(result.sentiment)  # "positive"
        
        >>> # With custom system prompt
        >>> translation = llm_do(
        ...     "Hello world",
        ...     system_prompt="You are a translator. Translate to Spanish."
        ... )
    """
    # Validate input
    if not input or not input.strip():
        raise ValueError("Input cannot be empty")
    
    # Load system prompt
    if system_prompt:
        prompt_text = load_system_prompt(system_prompt)
    else:
        prompt_text = "You are a helpful assistant."
    
    # Get API key
    api_key = api_key or os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OpenAI API key required. Set OPENAI_API_KEY environment variable or pass api_key parameter.")
    
    try:
        import openai
    except ImportError:
        raise ImportError("Please install openai: pip install openai>=1.0.0")
    
    client = openai.OpenAI(api_key=api_key)
    
    # Build messages
    messages = [
        {"role": "system", "content": prompt_text},
        {"role": "user", "content": input}
    ]
    
    # Make the API call
    try:
        if output:
            # Use structured outputs with Pydantic model
            response = client.beta.chat.completions.parse(
                model=model,
                messages=messages,
                temperature=temperature,
                response_format=output
            )
            
            # Get the parsed result
            parsed = response.choices[0].message.parsed
            if parsed:
                return parsed
            
            # Handle refusal
            if response.choices[0].message.refusal:
                raise ValueError(f"Model refused to respond: {response.choices[0].message.refusal}")
            
            raise ValueError("No parsed output in response")
        else:
            # Simple string response
            response = client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature
            )
            
            return response.choices[0].message.content or ""
            
    except openai.APIError as e:
        raise RuntimeError(f"OpenAI API error: {str(e)}")
    except Exception as e:
        if "parse" in str(e) and "beta" in str(e):
            raise RuntimeError(
                "Structured outputs require openai>=1.40.0. "
                "Please upgrade: pip install --upgrade openai"
            )
        raise RuntimeError(f"Unexpected error: {str(e)}")
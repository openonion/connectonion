"""One-shot LLM function for simple LLM calls with optional structured output.

Uses LiteLLM to support 100+ LLM providers including:
- OpenAI (GPT models)
- Anthropic (Claude models)  
- Google (Gemini models)
- Azure OpenAI
- AWS Bedrock
- Ollama (local models)
- And many more...
"""

from typing import Union, Type, Optional, TypeVar
from pathlib import Path
from pydantic import BaseModel
import json
import os
import toml
import requests
from .prompts import load_system_prompt
from .llm import MODEL_REGISTRY

T = TypeVar('T', bound=BaseModel)


def _get_litellm_model_name(model: str) -> str:
    """Convert model name to LiteLLM format.
    
    For most models, we use the simple name (e.g., "gpt-4o", "claude-3-5-sonnet").
    Special prefixes:
    - co/model_name for ConnectOnion managed keys (stripped for actual API call)
    - ollama/model_name for local Ollama models
    - azure/deployment_name for Azure OpenAI
    - bedrock/model_id for AWS Bedrock
    """
    # Handle ConnectOnion managed keys prefix
    if model.startswith("co/"):
        # Strip the co/ prefix for the actual model name
        model = model[3:]
    
    # If already has a provider prefix, return as-is
    if "/" in model:
        return model
    
    # Check if it's a Gemini model that needs the prefix
    provider = MODEL_REGISTRY.get(model)
    if provider == "google" and not model.startswith("gemini/"):
        # Add gemini/ prefix for Google models in LiteLLM
        return f"gemini/{model}"
    
    # For OpenAI and Anthropic models, use as-is
    # LiteLLM handles them without prefixes
    return model


def _get_auth_token() -> Optional[str]:
    """Get authentication token from environment or .co/config.toml."""
    # First check environment variable (from .env file)
    token = os.getenv("OPENONION_API_KEY")
    if token:
        return token

    # Then check .co/config.toml
    try:
        co_dir = Path(".co")
        if co_dir.exists():
            config_path = co_dir / "config.toml"
            if config_path.exists():
                config = toml.load(config_path)
                return config.get("auth", {}).get("token")
    except Exception:
        pass
    return None


def llm_do(
    input: str,
    output: Optional[Type[T]] = None,
    system_prompt: Optional[Union[str, Path]] = None,
    model: str = "gpt-4o-mini",
    temperature: float = 0.1,
    api_key: Optional[str] = None,
    **kwargs
) -> Union[str, T]:
    """
    Make a one-shot LLM call with optional structured output using LiteLLM.
    
    Supports 100+ LLM providers. Most models work with simple names:
    - OpenAI: "gpt-4o", "o4-mini", "gpt-3.5-turbo"
    - Anthropic: "claude-3-5-sonnet", "claude-3-5-haiku", "claude-3-opus"
    - Google: "gemini-1.5-pro", "gemini-1.5-flash"
    
    Special providers need prefixes:
    - ConnectOnion Managed: "co/gpt-4o", "co/claude-3-5-sonnet" (no API keys needed!)
    - Ollama: "ollama/llama2", "ollama/mistral"
    - Azure: "azure/<deployment-name>"
    - Bedrock: "bedrock/anthropic.claude-v2"
    
    Args:
        input: The input text/question to send to the LLM
        output: Optional Pydantic model class for structured output
        system_prompt: Optional system prompt (string or file path)
        model: Model name (e.g., "gpt-4o", "co/gpt-4o", "claude-3-5-sonnet")
        temperature: Sampling temperature (default: 0.1 for consistency)
        api_key: Optional API key (uses environment variable if not provided)
        **kwargs: Additional parameters to pass to LiteLLM
    
    Returns:
        Either a string response or an instance of the output model
    
    Examples:
        >>> # Simple string response with OpenAI
        >>> answer = llm_do("What's 2+2?")
        >>> print(answer)  # "4"
        
        >>> # With ConnectOnion managed keys (no API key needed!)
        >>> answer = llm_do("What's 2+2?", model="co/o4-mini")
        
        >>> # With Claude (simple name)
        >>> answer = llm_do("Explain quantum physics", model="claude-3-5-haiku-20241022")
        
        >>> # With Gemini (simple name)
        >>> answer = llm_do("Write a poem", model="gemini-1.5-flash")
        
        >>> # With local Ollama (needs prefix)
        >>> answer = llm_do("Hello", model="ollama/llama2")
        
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
    
    # Check if using ConnectOnion managed keys
    is_managed_model = model.startswith("co/")
    
    # Load system prompt
    if system_prompt:
        prompt_text = load_system_prompt(system_prompt)
    else:
        prompt_text = "You are a helpful assistant."
    
    # Handle co/ models through our backend
    if is_managed_model:
        import requests
        
        # Get auth token
        auth_token = _get_auth_token()
        if not auth_token:
            raise ValueError(
                "No authentication token found for co/ models.\n"
                "Run 'co auth' to authenticate first."
            )
        
        # Build messages
        messages = [
            {"role": "system", "content": prompt_text},
            {"role": "user", "content": input}
        ]
        
        # Prepare request - use OpenAI-compatible endpoint
        if os.getenv("OPENONION_DEV") or os.getenv("ENVIRONMENT") == "development":
            api_url = "http://localhost:8000/v1/chat/completions"
        else:
            api_url = "https://oo.openonion.ai/v1/chat/completions"
        
        headers = {
            "Authorization": f"Bearer {auth_token}",
            "Content-Type": "application/json"
        }
        
        # Build payload with proper parameters for different models
        payload = {
            "model": model,  # Keep the full model name with co/ prefix
            "messages": messages,
        }

        # Handle o4-mini special requirements
        if "o4-mini" in model:
            payload["max_completion_tokens"] = kwargs.get("max_completion_tokens", 16384)
            payload["temperature"] = 1  # o4-mini requires temperature=1
        else:
            payload["max_tokens"] = kwargs.get("max_tokens", 16384)
            payload["temperature"] = temperature

        # Add any other kwargs that aren't already set
        for key, value in kwargs.items():
            if key not in payload and key not in ["max_completion_tokens", "max_tokens", "temperature"]:
                payload[key] = value
        
        # Handle structured output
        if output:
            schema = output.model_json_schema()
            json_instruction = (
                f"\n\nPlease respond with a JSON object that matches this schema:\n"
                f"{json.dumps(schema, indent=2)}\n"
                f"Return ONLY valid JSON, no other text."
            )
            messages[-1]["content"] += json_instruction
            payload["messages"] = messages
        
        try:
            response = requests.post(api_url, json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()
            
            content = data["choices"][0]["message"]["content"]
            
            if output:
                # Parse structured output
                import re
                json_match = re.search(r'\{.*\}', content, re.DOTALL)
                if json_match:
                    json_str = json_match.group(0)
                    json_data = json.loads(json_str)
                    return output.model_validate(json_data)
                else:
                    # Try parsing entire content
                    json_data = json.loads(content)
                    return output.model_validate(json_data)
            else:
                return content
                
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 401:
                raise ValueError("Authentication expired. Run 'co auth' again.")
            else:
                raise ValueError(f"API error: {e.response.text}")
        except Exception as e:
            raise ValueError(f"Failed to call managed model: {e}")
    
    # Import LiteLLM for non-managed models
    try:
        from litellm import completion
        import litellm
    except ImportError:
        raise ImportError(
            "Please install litellm: pip install litellm\n"
            "This enables support for 100+ LLM providers."
        )
    
    # Convert model name to LiteLLM format
    litellm_model = _get_litellm_model_name(model)
    
    # Set API key if provided
    if api_key:
        # Detect provider and set appropriate env var
        provider = MODEL_REGISTRY.get(model)
        if not provider and "/" not in model:
            # Try to infer from model name
            if model.startswith("gpt") or model.startswith("o"):
                provider = "openai"
            elif model.startswith("claude"):
                provider = "anthropic"
            elif model.startswith("gemini"):
                provider = "google"
        
        if provider == "openai":
            os.environ["OPENAI_API_KEY"] = api_key
        elif provider == "anthropic":
            os.environ["ANTHROPIC_API_KEY"] = api_key
        elif provider == "google":
            os.environ["GEMINI_API_KEY"] = api_key
    
    # Build messages
    messages = [
        {"role": "system", "content": prompt_text},
        {"role": "user", "content": input}
    ]
    
    # Prepare completion kwargs
    completion_kwargs = {
        "model": litellm_model,
        "messages": messages,
        "temperature": temperature,
        **kwargs  # Pass through any additional parameters
    }
    
    # Make the API call
    try:
        if output:
            # Check if model supports structured outputs
            try:
                from litellm import supports_response_schema
                
                # For structured output with Pydantic model
                if supports_response_schema(model=litellm_model):
                    # Model supports native structured outputs
                    completion_kwargs["response_format"] = output
                else:
                    # Fallback: Use JSON mode with schema validation
                    # Enable client-side validation for models that don't support json_schema
                    litellm.enable_json_schema_validation = True
                    
                    # Add JSON instruction to the prompt
                    schema = output.model_json_schema()
                    json_instruction = (
                        f"\n\nPlease respond with a JSON object that matches this schema:\n"
                        f"{json.dumps(schema, indent=2)}\n"
                        f"Return ONLY valid JSON, no other text."
                    )
                    messages[-1]["content"] += json_instruction
                    
                    # Try to use JSON mode if supported
                    try:
                        from litellm import get_supported_openai_params
                        params = get_supported_openai_params(model=litellm_model)
                        if "response_format" in params:
                            completion_kwargs["response_format"] = {"type": "json_object"}
                    except:
                        pass  # Model doesn't support response_format
            except ImportError:
                # Older version of LiteLLM, use JSON instruction approach
                schema = output.model_json_schema()
                json_instruction = (
                    f"\n\nPlease respond with a JSON object that matches this schema:\n"
                    f"{json.dumps(schema, indent=2)}\n"
                    f"Return ONLY valid JSON, no other text."
                )
                messages[-1]["content"] += json_instruction
            
            # Make the completion call
            response = completion(**completion_kwargs)
            
            # Extract the content
            content = response.choices[0].message.content
            
            # Parse the response
            if hasattr(response.choices[0].message, 'parsed') and response.choices[0].message.parsed:
                # Direct structured output support
                return response.choices[0].message.parsed
            else:
                # Parse JSON from text response
                import re
                
                # Try to extract JSON from the response
                json_match = re.search(r'\{.*\}', content, re.DOTALL)
                if json_match:
                    json_str = json_match.group(0)
                    try:
                        json_data = json.loads(json_str)
                        return output.model_validate(json_data)
                    except (json.JSONDecodeError, Exception) as e:
                        # Try to clean up common JSON issues
                        json_str = json_str.replace("'", '"')  # Replace single quotes
                        json_str = re.sub(r',\s*}', '}', json_str)  # Remove trailing commas
                        json_str = re.sub(r',\s*]', ']', json_str)  # Remove trailing commas in arrays
                        
                        try:
                            json_data = json.loads(json_str)
                            return output.model_validate(json_data)
                        except:
                            raise ValueError(f"Failed to parse JSON response: {e}\nContent: {content}")
                else:
                    # Try parsing the entire content as JSON
                    try:
                        json_data = json.loads(content)
                        return output.model_validate(json_data)
                    except:
                        raise ValueError(f"No valid JSON found in response: {content}")
        else:
            # Simple string response
            response = completion(**completion_kwargs)
            return response.choices[0].message.content or ""
            
    except Exception as e:
        if "import litellm" in str(e):
            raise ImportError(
                "Please install litellm: pip install litellm\n"
                "This enables support for 100+ LLM providers."
            )
        elif "API" in str(e) or "api" in str(e):
            raise RuntimeError(f"API error: {str(e)}")
        elif "Failed to parse" in str(e) or "No valid JSON" in str(e):
            raise  # Re-raise parsing errors as-is
        else:
            raise RuntimeError(f"Unexpected error: {str(e)}")
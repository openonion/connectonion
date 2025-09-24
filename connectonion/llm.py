"""LLM interface for ConnectOnion."""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
import json
import os
import openai
import anthropic
import google.generativeai as genai
import requests
from pathlib import Path
import toml


@dataclass
class ToolCall:
    """Represents a tool call from the LLM."""
    name: str
    arguments: Dict[str, Any]
    id: str


@dataclass
class LLMResponse:
    """Response from LLM including content and tool calls."""
    content: Optional[str]
    tool_calls: List[ToolCall]
    raw_response: Any


class LLM(ABC):
    """Abstract base class for LLM providers."""
    
    @abstractmethod
    def complete(self, messages: List[Dict[str, str]], tools: Optional[List[Dict[str, Any]]] = None) -> LLMResponse:
        """Complete a conversation with optional tool support."""
        pass


class OpenAILLM(LLM):
    """OpenAI LLM implementation."""
    
    def __init__(self, api_key: Optional[str] = None, model: str = "o4-mini", **kwargs):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError("OpenAI API key required. Set OPENAI_API_KEY environment variable or pass api_key parameter.")
        
        self.client = openai.OpenAI(api_key=self.api_key)
        self.model = model
    
    def complete(self, messages: List[Dict[str, str]], tools: Optional[List[Dict[str, Any]]] = None) -> LLMResponse:
        """Complete a conversation with optional tool support."""
        kwargs = {
            "model": self.model,
            "messages": messages
        }

        # Set appropriate max tokens for different models
        if self.model in ["o1", "o1-mini", "o1-preview", "o4-mini"]:
            kwargs["max_completion_tokens"] = 16384
        else:
            kwargs["max_tokens"] = 16384

        if tools:
            kwargs["tools"] = [{"type": "function", "function": tool} for tool in tools]
            kwargs["tool_choice"] = "auto"

        response = self.client.chat.completions.create(**kwargs)
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
        
        return LLMResponse(
            content=message.content,
            tool_calls=tool_calls,
            raw_response=response
        )


class AnthropicLLM(LLM):
    """Anthropic Claude LLM implementation."""
    
    def __init__(self, api_key: Optional[str] = None, model: str = "claude-3-5-sonnet-20241022", **kwargs):
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        if not self.api_key:
            raise ValueError("Anthropic API key required. Set ANTHROPIC_API_KEY environment variable or pass api_key parameter.")
        
        self.client = anthropic.Anthropic(api_key=self.api_key)
        self.model = model
    
    def complete(self, messages: List[Dict[str, Any]], tools: Optional[List[Dict[str, Any]]] = None) -> LLMResponse:
        """Complete a conversation with optional tool support."""
        # Convert messages to Anthropic format
        anthropic_messages = self._convert_messages(messages)
        
        kwargs = {
            "model": self.model,
            "max_tokens": 16384,
            "messages": anthropic_messages
        }
        
        # Add tools if provided
        if tools:
            kwargs["tools"] = self._convert_tools(tools)
        
        response = self.client.messages.create(**kwargs)
        
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
        
        return LLMResponse(
            content=content if content else None,
            tool_calls=tool_calls,
            raw_response=response
        )
    
    def _convert_messages(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Convert OpenAI-style messages to Anthropic format."""
        anthropic_messages = []
        i = 0
        
        while i < len(messages):
            msg = messages[i]
            
            # Skip system messages (will be handled separately)
            if msg["role"] == "system":
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
        
        return anthropic_messages
    
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


class GeminiLLM(LLM):
    """Google Gemini LLM implementation."""
    
    def __init__(self, api_key: Optional[str] = None, model: str = "gemini-1.5-flash", **kwargs):
        self.api_key = api_key or os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
        if not self.api_key:
            raise ValueError("Google API key required. Set GOOGLE_API_KEY or GEMINI_API_KEY environment variable or pass api_key parameter.")
        
        genai.configure(api_key=self.api_key)
        self.model = model
        self.client = genai.GenerativeModel(model)
    
    def complete(self, messages: List[Dict[str, Any]], tools: Optional[List[Dict[str, Any]]] = None) -> LLMResponse:
        """Complete a conversation with optional tool support."""
        # Convert messages to Gemini format
        gemini_messages = self._convert_messages(messages)
        
        # Configure generation with tools if provided
        generation_config = genai.GenerationConfig(
            max_output_tokens=16384,
        )
        
        # If we have tools, use the GenerativeModel with tools directly
        if tools:
            # Convert tools to Gemini format
            gemini_tools = self._convert_tools(tools)
            
            # Create a new model instance with tools
            model = genai.GenerativeModel(
                self.model,
                tools=gemini_tools
            )
            
            # For Gemini, we need to use the contents directly, not a chat session
            # when dealing with function calls
            if gemini_messages and gemini_messages[-1].get("role") == "function":
                # If the last message is a function response, we need to continue the conversation
                # Build the full contents list
                contents = []
                for msg in gemini_messages:
                    # Convert parts properly - they might be strings or proto objects
                    parts_list = []
                    for part in msg["parts"]:
                        if isinstance(part, str):
                            # Convert string to Part
                            parts_list.append(genai.protos.Part(text=part))
                        else:
                            # Already a Part object
                            parts_list.append(part)
                    
                    contents.append(genai.protos.Content(
                        role=msg["role"],
                        parts=parts_list
                    ))
                
                # Generate response with the full conversation history
                response = model.generate_content(
                    contents=contents,
                    generation_config=generation_config
                )
            else:
                # Start or continue a chat
                chat = model.start_chat(
                    history=gemini_messages[:-1] if len(gemini_messages) > 1 else []
                )
                # Send the last message
                last_msg = gemini_messages[-1] if gemini_messages else {"parts": ["Hello"]}
                response = chat.send_message(
                    last_msg["parts"][0] if isinstance(last_msg["parts"][0], str) else last_msg["parts"],
                    generation_config=generation_config
                )
        else:
            # No tools, just chat
            chat = self.client.start_chat(
                history=gemini_messages[:-1] if gemini_messages else []
            )
            response = chat.send_message(
                gemini_messages[-1]["parts"][0] if gemini_messages else "Hello",
                generation_config=generation_config
            )
        
        # Parse response
        tool_calls = []
        content = ""
        
        # Handle response candidates
        if hasattr(response, 'candidates') and response.candidates:
            candidate = response.candidates[0]
            if hasattr(candidate, 'content') and hasattr(candidate.content, 'parts'):
                for part in candidate.content.parts:
                    if hasattr(part, 'text') and part.text:
                        content += part.text
                    elif hasattr(part, 'function_call'):
                        fc = part.function_call
                        tool_calls.append(ToolCall(
                            name=fc.name,
                            arguments=dict(fc.args),
                            id=f"call_{fc.name}_{len(tool_calls)}"  # Generate a unique ID
                        ))
        # Fallback to direct parts access (for older API responses)
        elif hasattr(response, 'parts'):
            for part in response.parts:
                if hasattr(part, 'text') and part.text:
                    content += part.text
                elif hasattr(part, 'function_call'):
                    fc = part.function_call
                    tool_calls.append(ToolCall(
                        name=fc.name,
                        arguments=dict(fc.args),
                        id=f"call_{fc.name}_{len(tool_calls)}"  # Generate a unique ID
                    ))
        
        return LLMResponse(
            content=content if content else None,
            tool_calls=tool_calls,
            raw_response=response
        )
    
    def _convert_messages(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Convert OpenAI-style messages to Gemini format."""
        gemini_messages = []
        i = 0
        
        while i < len(messages):
            msg = messages[i]
            
            # Skip system messages (Gemini doesn't have a direct system role)
            if msg["role"] == "system":
                i += 1
                continue
            
            # Convert user messages
            if msg["role"] == "user":
                # Handle tool result messages from OpenAI format
                if isinstance(msg.get("content"), list):
                    # This is a tool result message in OpenAI format
                    parts = []
                    for item in msg["content"]:
                        if item.get("type") == "tool_result":
                            # Create proper function response for Gemini
                            parts.append(genai.protos.Part(
                                function_response=genai.protos.FunctionResponse(
                                    name=item.get("name", "unknown"),
                                    response={"result": item["content"]}
                                )
                            ))
                    if parts:
                        gemini_messages.append({
                            "role": "function",
                            "parts": parts
                        })
                else:
                    gemini_messages.append({
                        "role": "user",
                        "parts": [msg["content"]]
                    })
                i += 1
                
            # Handle assistant messages with tool calls
            elif msg["role"] == "assistant":
                if msg.get("tool_calls"):
                    # Add the model's function calls
                    parts = []
                    if msg.get("content"):
                        parts.append(msg["content"])
                    
                    # Add function calls to parts
                    for tc in msg["tool_calls"]:
                        func_name = tc["function"]["name"]
                        func_args = tc["function"]["arguments"]
                        if isinstance(func_args, str):
                            import json
                            try:
                                func_args = json.loads(func_args)
                            except json.JSONDecodeError:
                                # If it's not valid JSON, skip the eval for security
                                func_args = {}
                        
                        parts.append(genai.protos.Part(
                            function_call=genai.protos.FunctionCall(
                                name=func_name,
                                args=func_args
                            )
                        ))
                    
                    gemini_messages.append({
                        "role": "model",
                        "parts": parts
                    })
                    
                    # Now collect all the tool responses that follow
                    i += 1
                    function_responses = []
                    while i < len(messages) and messages[i]["role"] == "tool":
                        tool_msg = messages[i]
                        # Find which tool call this response is for
                        tool_name = None
                        for tc in msg["tool_calls"]:
                            if tc["id"] == tool_msg["tool_call_id"]:
                                tool_name = tc["function"]["name"]
                                break
                        
                        if tool_name:
                            function_responses.append(genai.protos.Part(
                                function_response=genai.protos.FunctionResponse(
                                    name=tool_name,
                                    response={"result": tool_msg["content"]}
                                )
                            ))
                        i += 1
                    
                    # Add all function responses in a single message
                    if function_responses:
                        gemini_messages.append({
                            "role": "function",
                            "parts": function_responses
                        })
                else:
                    # Regular assistant message without tool calls
                    gemini_messages.append({
                        "role": "model",
                        "parts": [msg["content"]]
                    })
                    i += 1
                    
            # Skip individual tool messages (they're handled above)
            elif msg["role"] == "tool":
                i += 1
                continue
            else:
                i += 1
        
        return gemini_messages
    
    def _convert_tools(self, tools: List[Dict[str, Any]]) -> List:
        """Convert OpenAI-style tools to Gemini format."""
        gemini_tools = []
        
        for tool in tools:
            # Create function declaration for Gemini
            function_declaration = genai.protos.FunctionDeclaration(
                name=tool["name"],
                description=tool.get("description", ""),
                parameters=genai.protos.Schema(
                    type=genai.protos.Type.OBJECT,
                    properties=self._convert_properties(tool.get("parameters", {}).get("properties", {})),
                    required=tool.get("parameters", {}).get("required", [])
                )
            )
            gemini_tools.append(genai.protos.Tool(function_declarations=[function_declaration]))
        
        return gemini_tools
    
    def _convert_properties(self, properties: Dict[str, Any]) -> Dict:
        """Convert OpenAI property definitions to Gemini Schema format."""
        converted = {}
        
        for key, value in properties.items():
            prop_type = value.get("type", "string")
            
            # Map types to Gemini types
            type_map = {
                "string": genai.protos.Type.STRING,
                "number": genai.protos.Type.NUMBER,
                "integer": genai.protos.Type.NUMBER,
                "boolean": genai.protos.Type.BOOLEAN,
                "array": genai.protos.Type.ARRAY,
                "object": genai.protos.Type.OBJECT
            }
            
            schema = genai.protos.Schema(
                type=type_map.get(prop_type, genai.protos.Type.STRING),
                description=value.get("description", "")
            )
            
            # Handle enums
            if "enum" in value:
                schema.enum = value["enum"]
            
            # Handle array items
            if prop_type == "array" and "items" in value:
                items = value["items"]
                item_type = items.get("type", "string")
                schema.items = genai.protos.Schema(
                    type=type_map.get(item_type, genai.protos.Type.STRING)
                )
            
            converted[key] = schema
        
        return converted


# Model registry mapping model names to providers
MODEL_REGISTRY = {
    # OpenAI models
    "gpt-4o": "openai",
    "gpt-4o-mini": "openai",
    "gpt-4-turbo": "openai",
    "gpt-3.5-turbo": "openai",
    "o1": "openai",
    "o1-mini": "openai",
    "o1-preview": "openai",
    "o4-mini": "openai",  # Testing placeholder
    
    # Anthropic Claude models
    "claude-3-5-sonnet": "anthropic",
    "claude-3-5-sonnet-20241022": "anthropic",
    "claude-3-5-sonnet-latest": "anthropic",
    "claude-3-5-haiku": "anthropic",
    "claude-3-5-haiku-20241022": "anthropic",
    "claude-3-5-haiku-latest": "anthropic",
    "claude-3-haiku-20240307": "anthropic",
    "claude-3-opus-20240229": "anthropic",
    "claude-3-opus-latest": "anthropic",
    "claude-3-sonnet-20240229": "anthropic",
    
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
    "gemini-2.5-pro": "google",  # Testing placeholder
    "gemini-2.0-flash-exp": "google",
    "gemini-2.0-flash-thinking-exp": "google",
    "gemini-1.5-pro": "google",
    "gemini-1.5-pro-002": "google",
    "gemini-1.5-pro-001": "google",
    "gemini-1.5-flash": "google",
    "gemini-1.5-flash-002": "google",
    "gemini-1.5-flash-001": "google",
    "gemini-1.5-flash-8b": "google",
    "gemini-1.0-pro": "google",
}


class OpenOnionLLM(LLM):
    """OpenOnion managed keys LLM implementation using OpenAI-compatible API."""

    def __init__(self, api_key: Optional[str] = None, model: str = "co/o4-mini", **kwargs):
        # For co/ models, api_key is actually the auth token
        self.auth_token = api_key or self._get_auth_token()
        if not self.auth_token:
            raise ValueError(
                "No authentication token found for co/ models.\n"
                "Run 'co auth' to authenticate first."
            )

        self.model = model

        # Determine base URL for OpenAI-compatible endpoint
        if os.getenv("OPENONION_DEV") or os.getenv("ENVIRONMENT") == "development":
            base_url = "http://localhost:8000/v1"
        else:
            base_url = "https://oo.openonion.ai/v1"

        # Use OpenAI client with OpenOnion endpoint
        self.client = openai.OpenAI(
            base_url=base_url,
            api_key=self.auth_token
        )
    
    def _get_auth_token(self) -> Optional[str]:
        """Get authentication token from environment or local config."""
        # First check environment variable (from .env file)
        token = os.getenv("OPENONION_API_KEY")
        if token:
            return token

        # Try current directory first, then parent directories, then home
        config_paths = [
            Path.cwd() / ".co" / "config.toml",
            Path.cwd().parent / ".co" / "config.toml",
            Path.cwd().parent.parent / ".co" / "config.toml",
            Path.home() / ".connectonion" / ".co" / "config.toml"
        ]

        # Also check if we're running from a subdirectory
        # Look for .co in the same directory as the script being run
        import sys
        if sys.argv[0]:
            script_dir = Path(sys.argv[0]).parent.absolute()
            config_paths.insert(0, script_dir / ".co" / "config.toml")

        for config_path in config_paths:
            if config_path.exists():
                try:
                    config = toml.load(config_path)
                    if "auth" in config and "token" in config["auth"]:
                        return config["auth"]["token"]
                except Exception:
                    continue

        return None
    
    def complete(self, messages: List[Dict[str, Any]], tools: Optional[List[Dict[str, Any]]] = None) -> LLMResponse:
        """Complete a conversation with optional tool support using OpenAI-compatible API."""
        kwargs = {
            "model": self.model,
            "messages": messages
        }

        # Handle special requirements for o4-mini
        if "o4-mini" in self.model:
            # o4-mini requires max_completion_tokens instead of max_tokens
            kwargs["max_completion_tokens"] = 16384
            kwargs["temperature"] = 1
        else:
            kwargs["max_tokens"] = 16384

        # Add tools if provided
        if tools:
            kwargs["tools"] = [{"type": "function", "function": tool} for tool in tools]
            kwargs["tool_choice"] = "auto"

        try:
            response = self.client.chat.completions.create(**kwargs)
            message = response.choices[0].message

            # Parse tool calls if present
            tool_calls = []
            if hasattr(message, 'tool_calls') and message.tool_calls:
                for tc in message.tool_calls:
                    tool_calls.append(ToolCall(
                        name=tc.function.name,
                        arguments=json.loads(tc.function.arguments) if isinstance(tc.function.arguments, str) else tc.function.arguments,
                        id=tc.id
                    ))

            return LLMResponse(
                content=message.content,
                tool_calls=tool_calls,
                raw_response=response
            )

        except Exception as e:
            error_msg = f"OpenOnion API error: {str(e)}"
            raise ValueError(error_msg)


def create_llm(model: str, api_key: Optional[str] = None, **kwargs) -> LLM:
    """Factory function to create the appropriate LLM based on model name.
    
    Args:
        model: The model name (e.g., "gpt-4o", "claude-3-5-sonnet", "gemini-1.5-pro")
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
    
    # Get provider from registry
    provider = MODEL_REGISTRY.get(model)
    
    if not provider:
        # Try to infer provider from model name
        if model.startswith("gpt") or model.startswith("o"):
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
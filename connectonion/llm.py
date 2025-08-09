"""LLM interface for ConnectOnion."""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
import json
import os

try:
    import openai
except ImportError:
    raise ImportError("Please install openai: pip install openai>=1.0.0")


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
    
    def __init__(self, api_key: Optional[str] = None, model: str = "gpt-5-mini"):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError("OpenAI API key required. Set OPENAI_API_KEY environment variable or pass api_key parameter.")
        
        self.client = openai.OpenAI(api_key=self.api_key)
        self.model = model
    
    def complete(self, messages: List[Dict[str, str]], tools: Optional[List[Dict[str, Any]]] = None) -> LLMResponse:
        """Complete a conversation with optional tool support."""
        try:
            kwargs = {
                "model": self.model,
                "messages": messages
            }
            
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
            
        except openai.APIError as e:
            raise RuntimeError(f"OpenAI API error: {str(e)}")
        except Exception as e:
            raise RuntimeError(f"Unexpected error calling OpenAI: {str(e)}")
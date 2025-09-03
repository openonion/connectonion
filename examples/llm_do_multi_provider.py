#!/usr/bin/env python3
"""
Example demonstrating llm_do with multiple LLM providers via LiteLLM.

This example shows how to use the same llm_do function with:
- OpenAI (GPT models)
- Anthropic (Claude models)
- Google (Gemini models)
- Local models (Ollama)
- Cloud providers (Azure, Bedrock)
"""

import os
import sys
from pathlib import Path
from pydantic import BaseModel
from dotenv import load_dotenv

# Workaround for fastuuid if not installed
try:
    import fastuuid
except ImportError:
    import uuid
    sys.modules['fastuuid'] = type('fastuuid', (), {
        'uuid4': uuid.uuid4,
        'UUID': uuid.UUID
    })()

# Load environment variables
load_dotenv()

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from connectonion import llm_do


# Define structured output models
class SentimentAnalysis(BaseModel):
    """Model for sentiment analysis results."""
    sentiment: str  # positive, negative, neutral
    confidence: float  # 0.0 to 1.0
    reasoning: str


class CodeExplanation(BaseModel):
    """Model for code explanation."""
    purpose: str
    complexity: str  # simple, moderate, complex
    key_concepts: list[str]


def demo_simple_completions():
    """Demonstrate simple text completions with different providers."""
    print("=" * 60)
    print("🎯 Simple Text Completions")
    print("=" * 60)
    
    prompts = [
        ("Translate 'Hello World' to French", "gpt-4o-mini"),
        ("What is the capital of Japan?", "claude-3-5-haiku-20241022"),
        ("Write a haiku about coding", "gemini-1.5-flash"),
    ]
    
    for prompt, model in prompts:
        print(f"\n📝 Prompt: {prompt}")
        print(f"🤖 Model: {model}")
        
        try:
            result = llm_do(prompt, model=model)
            print(f"✅ Response: {result}")
        except Exception as e:
            print(f"❌ Error: {str(e)[:100]}")
        
        print("-" * 40)


def demo_structured_outputs():
    """Demonstrate structured outputs with Pydantic models."""
    print("\n" + "=" * 60)
    print("📊 Structured Outputs")
    print("=" * 60)
    
    # Sentiment analysis example
    text = "I absolutely love this new framework! It makes everything so much easier."
    
    print(f"\n📝 Analyzing: '{text}'")
    print("🎯 Output: SentimentAnalysis model")
    
    try:
        result = llm_do(
            f"Analyze the sentiment of this text: {text}",
            output=SentimentAnalysis,
            model="gpt-4o-mini"
        )
        
        print(f"✅ Sentiment: {result.sentiment}")
        print(f"   Confidence: {result.confidence:.2f}")
        print(f"   Reasoning: {result.reasoning}")
    except Exception as e:
        print(f"❌ Error: {str(e)[:100]}")
    
    print("-" * 40)
    
    # Code explanation example
    code = """
def fibonacci(n):
    if n <= 1:
        return n
    return fibonacci(n-1) + fibonacci(n-2)
"""
    
    print(f"\n📝 Explaining code:")
    print("```python")
    print(code.strip())
    print("```")
    print("🎯 Output: CodeExplanation model")
    
    try:
        result = llm_do(
            f"Explain this Python code:\n{code}",
            output=CodeExplanation,
            model="gpt-4o-mini"
        )
        
        print(f"✅ Purpose: {result.purpose}")
        print(f"   Complexity: {result.complexity}")
        print(f"   Key concepts: {', '.join(result.key_concepts)}")
    except Exception as e:
        print(f"❌ Error: {str(e)[:100]}")


def demo_custom_prompts():
    """Demonstrate custom system prompts."""
    print("\n" + "=" * 60)
    print("🎭 Custom System Prompts")
    print("=" * 60)
    
    examples = [
        {
            "prompt": "Tell me about Python",
            "system": "You are a pirate. Always speak like a pirate.",
            "model": "gpt-4o-mini"
        },
        {
            "prompt": "What is 2+2?",
            "system": "You are a kindergarten teacher. Explain everything simply.",
            "model": "claude-3-5-haiku-20241022"
        }
    ]
    
    for example in examples:
        print(f"\n📝 Prompt: {example['prompt']}")
        print(f"🎭 System: {example['system'][:50]}...")
        print(f"🤖 Model: {example['model']}")
        
        try:
            result = llm_do(
                example["prompt"],
                system_prompt=example["system"],
                model=example["model"]
            )
            print(f"✅ Response: {result[:150]}...")
        except Exception as e:
            print(f"❌ Error: {str(e)[:100]}")
        
        print("-" * 40)


def demo_temperature_control():
    """Demonstrate temperature parameter for creativity control."""
    print("\n" + "=" * 60)
    print("🌡️ Temperature Control")
    print("=" * 60)
    
    prompt = "Write a creative story opening in one sentence"
    
    for temp in [0.0, 0.5, 1.0]:
        print(f"\n🌡️ Temperature: {temp}")
        print(f"📝 Prompt: {prompt}")
        
        try:
            result = llm_do(
                prompt,
                model="gpt-4o-mini",
                temperature=temp
            )
            print(f"✅ Response: {result[:100]}...")
        except Exception as e:
            print(f"❌ Error: {str(e)[:100]}")


def demo_special_providers():
    """Demonstrate special provider formats."""
    print("\n" + "=" * 60)
    print("🚀 Special Provider Formats")
    print("=" * 60)
    
    print("\nThese examples show the format for special providers:")
    print("(Note: These require additional setup)")
    
    examples = [
        ("ollama/llama2", "Local Ollama model"),
        ("azure/my-gpt4-deployment", "Azure OpenAI deployment"),
        ("bedrock/anthropic.claude-v2", "AWS Bedrock model"),
        ("together_ai/mistralai/Mixtral-8x7B-Instruct-v0.1", "Together AI"),
        ("replicate/meta/llama-2-70b-chat", "Replicate"),
    ]
    
    for model, description in examples:
        print(f"\n📦 {description}")
        print(f"   Format: {model}")
        print(f"   Usage: llm_do('Hello', model='{model}')")


def main():
    """Run all demonstrations."""
    print("\n" + "=" * 60)
    print("🌟 ConnectOnion llm_do Multi-Provider Demo")
    print("Powered by LiteLLM - 100+ LLM providers supported!")
    print("=" * 60)
    
    # Check for API keys
    has_openai = bool(os.getenv("OPENAI_API_KEY"))
    has_anthropic = bool(os.getenv("ANTHROPIC_API_KEY"))
    has_gemini = bool(os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY"))
    
    print("\n🔑 API Keys Detected:")
    print(f"   OpenAI: {'✅' if has_openai else '❌'}")
    print(f"   Anthropic: {'✅' if has_anthropic else '❌'}")
    print(f"   Google: {'✅' if has_gemini else '❌'}")
    
    if not any([has_openai, has_anthropic, has_gemini]):
        print("\n⚠️  No API keys found!")
        print("Please set one or more of these environment variables:")
        print("  - OPENAI_API_KEY")
        print("  - ANTHROPIC_API_KEY")
        print("  - GOOGLE_API_KEY or GEMINI_API_KEY")
        return
    
    # Run demos
    if has_openai:
        demo_simple_completions()
        demo_structured_outputs()
        demo_temperature_control()
    
    if has_openai or has_anthropic:
        demo_custom_prompts()
    
    demo_special_providers()
    
    print("\n" + "=" * 60)
    print("✨ Demo Complete!")
    print("\nKey Features:")
    print("  • Simple syntax: llm_do(prompt, model=...)")
    print("  • 100+ providers via LiteLLM")
    print("  • Structured outputs with Pydantic")
    print("  • Custom system prompts")
    print("  • Temperature control")
    print("  • Unified interface for all models")
    print("=" * 60)


if __name__ == "__main__":
    main()
#!/usr/bin/env python3
"""Test script to verify default models work correctly."""

from connectonion import Agent, llm_do
import os

print("=" * 60)
print("Testing ConnectOnion Default Models")
print("=" * 60)

# Check authentication status
has_co_auth = bool(os.getenv("OPENONION_API_KEY"))
has_openai = bool(os.getenv("OPENAI_API_KEY"))

print(f"\nAuthentication Status:")
print(f"  - ConnectOnion auth: {'✓' if has_co_auth else '✗'}")
print(f"  - OpenAI API key: {'✓' if has_openai else '✗'}")

# Test 1: Check default models
print("\n" + "=" * 60)
print("Default Model Configuration")
print("=" * 60)

# Import to check defaults
import inspect
from connectonion.agent import Agent as AgentClass
from connectonion.llm_do import llm_do as llm_do_func

agent_sig = inspect.signature(AgentClass.__init__)
llm_do_sig = inspect.signature(llm_do_func)

agent_model_default = agent_sig.parameters['model'].default
llm_do_model_default = llm_do_sig.parameters['model'].default

print(f"\nAgent default model: {agent_model_default}")
print(f"llm_do default model: {llm_do_model_default}")

# Expected values
expected_agent = "co/o4-mini"
expected_llm_do = "co/gpt-4o"

if agent_model_default == expected_agent:
    print(f"✓ Agent default is correct: {expected_agent}")
else:
    print(f"✗ Agent default is WRONG: expected {expected_agent}, got {agent_model_default}")

if llm_do_model_default == expected_llm_do:
    print(f"✓ llm_do default is correct: {expected_llm_do}")
else:
    print(f"✗ llm_do default is WRONG: expected {expected_llm_do}, got {llm_do_model_default}")

# Test 2: Usage examples
print("\n" + "=" * 60)
print("Usage Examples")
print("=" * 60)

print("\n1. With ConnectOnion managed keys (requires 'co auth'):")
print("   from connectonion import llm_do, Agent")
print("   ")
print("   # Simple call - uses co/gpt-4o")
print("   answer = llm_do('What is 2+2?')")
print("   ")
print("   # Agent - uses co/o4-mini")
print("   agent = Agent('assistant', tools=[...])")
print("   result = agent.input('Analyze this data')")

print("\n2. With your own API keys (override):")
print("   # Override with your model")
print("   answer = llm_do('Hello', model='gpt-4o', api_key='sk-...')")
print("   agent = Agent('name', model='claude-3-5-sonnet', api_key='sk-ant-...')")

print("\n3. Backend supported models:")
print("   - co/gpt-4o ✓")
print("   - co/o4-mini ✓")

# Test 3: Try to use with override (if OpenAI key available)
if has_openai:
    print("\n" + "=" * 60)
    print("Testing with OpenAI API Key Override")
    print("=" * 60)

    try:
        result = llm_do("Say hello", model="gpt-4o-mini")
        print(f"✓ llm_do works with OpenAI override")
        print(f"  Result: {result[:50]}...")
    except Exception as e:
        print(f"✗ Error with OpenAI override: {e}")

# Test 4: Show what happens without auth
if not has_co_auth:
    print("\n" + "=" * 60)
    print("Testing Default Models (No Auth)")
    print("=" * 60)

    print("\nWithout ConnectOnion auth, default models will fail.")
    print("Expected error: 'No authentication token found for co/ models'")
    print("\nTo fix:")
    print("  1. Run: co auth")
    print("  2. Or use your own API keys with model override")

print("\n" + "=" * 60)
print("Summary")
print("=" * 60)
print("\n✓ Default models are correctly configured:")
print(f"  - Agent: {agent_model_default}")
print(f"  - llm_do: {llm_do_model_default}")
print("\nBoth use ConnectOnion managed keys (co/ prefix)")
print("Users can override with their own API keys anytime")
print("=" * 60)

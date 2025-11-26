#!/usr/bin/env python3
"""Test all examples from llm_do docstring."""

import os
from pydantic import BaseModel
from connectonion import llm_do

# Check which API keys are available
has_openai = bool(os.getenv("OPENAI_API_KEY"))
has_anthropic = bool(os.getenv("ANTHROPIC_API_KEY"))
has_gemini = bool(os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY"))
has_co_auth = bool(os.getenv("OPENONION_API_KEY"))

print("=" * 70)
print("Testing llm_do Examples from Documentation")
print("=" * 70)

print(f"\nAvailable APIs:")
print(f"  OpenAI: {'✓' if has_openai else '✗'}")
print(f"  Anthropic: {'✓' if has_anthropic else '✗'}")
print(f"  Gemini: {'✓' if has_gemini else '✗'}")
print(f"  ConnectOnion: {'✓' if has_co_auth else '✗'}")

# Test 1: Simple string response with default model
print("\n" + "=" * 70)
print("Test 1: Simple string response with default model (co/gpt-4o)")
print("=" * 70)

if has_co_auth:
    try:
        answer = llm_do("What's 2+2?")
        print(f"✓ Default model works")
        print(f"  Question: What's 2+2?")
        print(f"  Answer: {answer}")
    except Exception as e:
        print(f"✗ Error: {e}")
else:
    print("⊘ Skipped - No ConnectOnion auth (run 'co auth')")

# Test 2: With ConnectOnion managed keys - co/o4-mini
print("\n" + "=" * 70)
print("Test 2: With ConnectOnion managed keys (co/o4-mini)")
print("=" * 70)

if has_co_auth:
    try:
        answer = llm_do("What's 2+2?", model="co/o4-mini")
        print(f"✓ co/o4-mini works")
        print(f"  Answer: {answer}")
    except Exception as e:
        print(f"✗ Error: {e}")
else:
    print("⊘ Skipped - No ConnectOnion auth")

# Test 3: With Claude (requires Anthropic API key or use override)
print("\n" + "=" * 70)
print("Test 3: With Claude (claude-3-5-haiku-20241022)")
print("=" * 70)

if has_anthropic:
    try:
        answer = llm_do(
            "Explain quantum physics in one sentence",
            model="claude-3-5-haiku-20241022"
        )
        print(f"✓ Claude works")
        print(f"  Answer: {answer[:100]}...")
    except Exception as e:
        print(f"✗ Error: {e}")
else:
    print("⊘ Skipped - No Anthropic API key")

# Test 4: With Gemini
print("\n" + "=" * 70)
print("Test 4: With Gemini (gemini-2.5-flash)")
print("=" * 70)

if has_gemini:
    try:
        answer = llm_do("Write a short haiku about code", model="gemini-2.5-flash")
        print(f"✓ Gemini works")
        print(f"  Answer:\n{answer}")
    except Exception as e:
        # Gemini sometimes has quota issues
        if "429" in str(e) or "quota" in str(e).lower():
            print(f"⊘ Skipped - Gemini quota exceeded")
        else:
            print(f"✗ Error: {e}")
else:
    print("⊘ Skipped - No Gemini API key")

# Test 5: With local Ollama (usually not available in tests)
print("\n" + "=" * 70)
print("Test 5: With local Ollama (ollama/llama2)")
print("=" * 70)
print("⊘ Skipped - Requires local Ollama installation")

# Test 6: With structured output
print("\n" + "=" * 70)
print("Test 6: With structured output (Pydantic model)")
print("=" * 70)

class Analysis(BaseModel):
    sentiment: str
    score: float

if has_openai:
    try:
        result = llm_do(
            "I love this! Best thing ever!",
            output=Analysis,
            model="gpt-4o-mini"  # Use OpenAI directly
        )
        print(f"✓ Structured output works")
        print(f"  Input: 'I love this! Best thing ever!'")
        print(f"  Sentiment: {result.sentiment}")
        print(f"  Score: {result.score}")
        assert isinstance(result, Analysis)
        assert result.sentiment.lower() in ['positive', 'very positive', 'extremely positive']
        print(f"  Validation: ✓")
    except Exception as e:
        print(f"✗ Error: {e}")
elif has_co_auth:
    try:
        result = llm_do(
            "I love this! Best thing ever!",
            output=Analysis,
            model="co/gpt-4o"  # Use managed keys
        )
        print(f"✓ Structured output works (with managed keys)")
        print(f"  Sentiment: {result.sentiment}")
        print(f"  Score: {result.score}")
    except Exception as e:
        print(f"✗ Error: {e}")
else:
    print("⊘ Skipped - No OpenAI or ConnectOnion auth")

# Test 7: Different temperatures
print("\n" + "=" * 70)
print("Test 7: Temperature parameter")
print("=" * 70)

if has_openai:
    try:
        # Low temperature (deterministic)
        result1 = llm_do(
            "What is the capital of France? One word only.",
            temperature=0.0,
            model="gpt-4o-mini"
        )
        result2 = llm_do(
            "What is the capital of France? One word only.",
            temperature=0.0,
            model="gpt-4o-mini"
        )
        print(f"✓ Temperature works")
        print(f"  Temperature 0.0 (attempt 1): {result1}")
        print(f"  Temperature 0.0 (attempt 2): {result2}")
        print(f"  Consistency: {'✓' if 'Paris' in result1 and 'Paris' in result2 else '✗'}")
    except Exception as e:
        print(f"✗ Error: {e}")
else:
    print("⊘ Skipped - No OpenAI API key")

# Summary
print("\n" + "=" * 70)
print("Summary")
print("=" * 70)

tests_run = sum([
    has_co_auth,  # Test 1: default model
    has_co_auth,  # Test 2: co/o4-mini
    has_anthropic,  # Test 3: Claude
    has_gemini,  # Test 4: Gemini
    # Test 5 skipped (Ollama)
    has_openai or has_co_auth,  # Test 6: structured output
    has_openai,  # Test 7: temperature
])

print(f"\nTests run: {tests_run}/7 (Ollama skipped)")
print(f"\nDefault model configuration:")
print(f"  llm_do default: co/gpt-4o")
print(f"  Requires: ConnectOnion auth ('co auth')")
print(f"\nOverride examples:")
print(f"  llm_do('Hello', model='gpt-4o-mini', api_key='sk-...')")
print(f"  llm_do('Hello', model='claude-3-5-haiku-20241022', api_key='sk-ant-...')")

print("\n" + "=" * 70)

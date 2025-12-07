"""Test LLM functionality with co/ models."""

import os
import sys
import json
import time
import requests
from pathlib import Path
from nacl.signing import SigningKey
from nacl.encoding import HexEncoder

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

def test_co_model_direct_api():
    """Test calling co/ model directly through API."""
    
    print("Testing co/ Model Direct API Call")
    print("="*50)
    
    # First authenticate to get a token
    signing_key = SigningKey.generate()
    public_key = "0x" + signing_key.verify_key.encode(encoder=HexEncoder).decode()
    timestamp = int(time.time())
    message = f"ConnectOnion-Auth-{public_key}-{timestamp}"
    signature = signing_key.sign(message.encode()).signature.hex()
    
    # Get token
    auth_response = requests.post(
        "https://oo.openonion.ai/auth",
        json={
            "public_key": public_key,
            "message": message,
            "signature": signature
        }
    )
    
    if auth_response.status_code != 200:
        print(f"❌ Authentication failed: {auth_response.status_code}")
        return False
    
    token = auth_response.json()["token"]
    print(f"✅ Got token: {token[:20]}...")
    
    # Test LLM completion with co/ model
    print("\nTesting LLM completion...")
    
    payload = {
        "model": "co/gpt-4o-mini",  # With co/ prefix as CLI sends
        "messages": [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Say 'Hello from ConnectOnion!' in exactly 3 words."}
        ],
        "temperature": 0.1,
        "max_tokens": 10
    }
    
    print(f"Model: {payload['model']}")
    print(f"Prompt: {payload['messages'][1]['content']}")
    
    response = requests.post(
        "https://oo.openonion.ai/api/llm/completions",
        json=payload,
        headers={"Authorization": f"Bearer {token}"}
    )
    
    print(f"Response Status: {response.status_code}")
    
    if response.status_code == 200:
        data = response.json()
        content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
        print(f"✅ LLM Response: {content}")
        return True
    else:
        print(f"❌ LLM call failed: {response.text[:200]}")
        return False


def test_llm_do_function():
    """Test using llm_do function with co/ model."""
    
    print("\n\nTesting llm_do Function with co/ Model")
    print("="*50)
    
    try:
        from connectonion.llm_do import llm_do, _get_auth_token
        
        # Check if we have a token (would need to run 'co auth' first)
        token = _get_auth_token()
        
        if token:
            print(f"✅ Found saved token: {token[:20]}...")
            
            # Test llm_do with co/ model
            print("\nCalling llm_do with co/gpt-4o-mini...")
            
            # Set production mode
            os.environ.pop("OPENONION_DEV", None)
            
            try:
                response = llm_do(
                    "Reply with exactly: 'ConnectOnion works!'",
                    model="co/gpt-4o-mini",
                    temperature=0.1
                )
                print(f"✅ Response: {response}")
                return True
            except Exception as e:
                print(f"❌ llm_do failed: {e}")
                
                # Check if it's an auth issue
                if "authentication token" in str(e).lower():
                    print("   Run 'co auth' first to authenticate")
                return False
        else:
            print("⚠️  No saved token found")
            print("   Would need to run 'co auth' first")
            print("   Skipping llm_do test")
            return None
            
    except ImportError as e:
        print(f"❌ Import error: {e}")
        return False


def test_model_name_variations():
    """Test that API handles model names correctly."""
    
    print("\n\nTesting Model Name Variations")
    print("="*50)
    
    # Get a token first
    signing_key = SigningKey.generate()
    public_key = "0x" + signing_key.verify_key.encode(encoder=HexEncoder).decode()
    timestamp = int(time.time())
    message = f"ConnectOnion-Auth-{public_key}-{timestamp}"
    signature = signing_key.sign(message.encode()).signature.hex()
    
    auth_response = requests.post(
        "https://oo.openonion.ai/auth",
        json={"public_key": public_key, "message": message, "signature": signature}
    )
    
    if auth_response.status_code != 200:
        print("❌ Failed to authenticate")
        return False
    
    token = auth_response.json()["token"]
    
    # Test different model name formats
    test_cases = [
        ("co/gpt-4o-mini", "With co/ prefix (as CLI sends)"),
        ("gpt-4o-mini", "Without co/ prefix (raw model name)"),
    ]
    
    results = []
    for model_name, description in test_cases:
        print(f"\nTesting: {description}")
        print(f"  Model: {model_name}")
        
        response = requests.post(
            "https://oo.openonion.ai/api/llm/completions",
            json={
                "model": model_name,
                "messages": [
                    {"role": "user", "content": "Reply 'OK'"}
                ],
                "max_tokens": 5
            },
            headers={"Authorization": f"Bearer {token}"}
        )
        
        if response.status_code == 200:
            print(f"  ✅ Success")
            results.append(True)
        else:
            print(f"  ❌ Failed: {response.status_code}")
            results.append(False)
    
    return all(results)


def test_all_managed_models_with_tools():
    """Test tool calling with all managed models (co/ prefix).

    This tests the null value handling fix across all providers.
    Gemini models were failing with "Value is not a struct: null" error.
    """
    from connectonion import Agent

    def simple_calculator(x: int, y: int) -> str:
        """Add two numbers."""
        return f"Result: {x + y}"

    # All managed models that support tool calling
    models_to_test = [
        # OpenAI models
        "co/gpt-4o-mini",
        # "co/gpt-4o",  # More expensive, skip in regular tests
        # Google Gemini models
        "co/gemini-2.5-flash",
        # "co/gemini-2.5-pro",  # More expensive
        "co/gemini-3-pro-preview",  # The model that had null value issues
        # Anthropic models
        # "co/claude-haiku-4-5",  # If available
    ]

    print("\n\nTesting Tool Calling with Managed Models")
    print("="*50)

    results = {}
    for model in models_to_test:
        print(f"\nTesting: {model}")
        try:
            agent = Agent(
                name=f"test_{model.replace('/', '_').replace('-', '_')}",
                model=model,
                tools=[simple_calculator],
                max_iterations=3
            )

            response = agent.input("What is 2 + 3? Use the calculator.")
            if response and "5" in response:
                print(f"  ✅ Success: {response[:50]}...")
                results[model] = True
            else:
                print(f"  ⚠️ Unexpected response: {response[:50] if response else 'None'}...")
                results[model] = False
        except Exception as e:
            print(f"  ❌ Error: {str(e)[:100]}")
            results[model] = False

    # Summary
    print("\n" + "-"*50)
    print("Results:")
    for model, passed in results.items():
        status = "✅ PASSED" if passed else "❌ FAILED"
        print(f"  {model}: {status}")

    return all(results.values())


def test_gemini3_multi_turn_tools_managed():
    """Test Gemini 3 multi-turn with tools using managed keys.

    This specifically tests the fix for null value handling in tool_executor.py.
    The second turn requires the first turn's messages to be sent back
    without null values in extra_content or content fields.
    """
    from connectonion import Agent

    def word_counter(text: str) -> str:
        """Count words in text."""
        return f"Word count: {len(text.split())}"

    print("\n\nTesting Gemini 3 Multi-Turn Tool Calling (Managed)")
    print("="*50)

    try:
        agent = Agent(
            name="gemini3_multi_turn_managed",
            model="co/gemini-3-pro-preview",
            tools=[word_counter],
            max_iterations=5
        )

        # First turn
        print("Turn 1: Counting words in 'hello world'")
        response1 = agent.input("Count words in 'hello world'")
        print(f"  Response: {response1[:100] if response1 else 'None'}...")

        if not response1 or "2" not in response1:
            print("  ❌ First turn failed")
            return False

        print("  ✅ First turn passed")

        # Second turn - this is where the null value error would occur
        print("\nTurn 2: Counting words in 'a b c d e'")
        response2 = agent.input("Now count words in 'a b c d e'")
        print(f"  Response: {response2[:100] if response2 else 'None'}...")

        if not response2 or "5" not in response2:
            print("  ❌ Second turn failed")
            return False

        print("  ✅ Second turn passed")
        print("\n✅ Multi-turn tool calling works correctly!")
        return True

    except Exception as e:
        print(f"❌ Error: {e}")
        # Check for the specific null value error
        if "Value is not a struct: null" in str(e):
            print("   This is the null value error that should be fixed!")
        return False



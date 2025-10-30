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


if __name__ == "__main__":
    print("ConnectOnion co/ Models Test Suite\n")
    
    # Run tests
    test1 = test_co_model_direct_api()
    test2 = test_llm_do_function()
    test3 = test_model_name_variations()
    
    # Summary
    print("\n" + "="*50)
    print("Test Summary:")
    print(f"  Direct API Call: {'✅ PASSED' if test1 else '❌ FAILED'}")
    
    if test2 is None:
        print(f"  llm_do Function: ⏭️  SKIPPED (no token)")
    else:
        print(f"  llm_do Function: {'✅ PASSED' if test2 else '❌ FAILED'}")
    
    print(f"  Model Name Variations: {'✅ PASSED' if test3 else '❌ FAILED'}")
    
    if test1 and test3:
        print("\n🎉 Core functionality working!")
        if test2 is None:
            print("   Run 'co auth' to test llm_do function")
    else:
        print("\n⚠️  Some tests failed")
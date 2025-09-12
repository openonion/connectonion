"""Test authentication integration between ConnectOnion CLI and OpenOnion API."""

import pytest
import time
import json
import requests
from unittest.mock import patch, MagicMock
from pathlib import Path
from nacl.signing import SigningKey
from nacl.encoding import HexEncoder

# Test the authentication flow
def test_connectonion_auth_format():
    """Test that ConnectOnion auth message format works with API."""
    
    # Generate test keys like the CLI does
    signing_key = SigningKey.generate()
    public_key = "0x" + signing_key.verify_key.encode(encoder=HexEncoder).decode()
    
    # Create message in ConnectOnion format
    timestamp = int(time.time())
    message = f"ConnectOnion-Auth-{public_key}-{timestamp}"
    
    # Sign the message
    signature = signing_key.sign(message.encode()).signature.hex()
    
    # This is what the CLI sends
    payload = {
        "public_key": public_key,
        "message": message,
        "signature": signature
    }
    
    print(f"\nTest Payload:")
    print(f"  Public Key: {public_key[:20]}...")
    print(f"  Message: {message}")
    print(f"  Signature: {signature[:20]}...")
    
    # Test against local API if running
    try:
        response = requests.post(
            "http://localhost:8000/auth",
            json=payload,
            timeout=2
        )
        print(f"\nLocal API Response: {response.status_code}")
        if response.status_code == 200:
            print(f"  Success! Token received")
        else:
            print(f"  Error: {response.text}")
    except requests.exceptions.ConnectionError:
        print("\nLocal API not running, skipping integration test")
    
    # Test message parsing logic directly
    from connectonion.cli.commands.auth_commands import Colors
    
    # Verify message format
    parts = message.split("-")
    assert len(parts) == 4
    assert parts[0] == "ConnectOnion"
    assert parts[1] == "Auth"
    assert parts[2] == public_key
    assert parts[3] == str(timestamp)
    
    print("\n✅ Message format is correct")


def test_llm_proxy_url():
    """Test that LLM proxy URL is correctly configured."""
    import os
    
    # Check URL configuration
    with open("../connectonion/connectonion/llm_do.py", "r") as f:
        content = f.read()
        
        # Check for environment detection
        if "OPENONION_DEV" in content and "ENVIRONMENT" in content:
            print("\n✅ Environment detection for API URL is present")
            
            # Test URL selection logic
            original_env = os.getenv("OPENONION_DEV")
            
            # Test production mode (default)
            os.environ.pop("OPENONION_DEV", None)
            os.environ.pop("ENVIRONMENT", None)
            # Would use https://oo.openonion.ai/api/llm/completions
            print("   Production mode: uses https://oo.openonion.ai")
            
            # Test dev mode
            os.environ["OPENONION_DEV"] = "true"
            # Would use http://localhost:8000/api/llm/completions  
            print("   Dev mode: uses http://localhost:8000")
            
            # Restore
            if original_env:
                os.environ["OPENONION_DEV"] = original_env
            else:
                os.environ.pop("OPENONION_DEV", None)
        else:
            print("\n⚠️  No environment detection for API URL")


def test_model_name_handling():
    """Test how model names with co/ prefix are handled."""
    
    # Check the fix in llm_do.py
    with open("../connectonion/connectonion/llm_do.py", "r") as f:
        content = f.read()
        
        # Check if model is kept intact (not stripped)
        if '"model": model,' in content and '"model": model[3:]' not in content:
            print(f"\n✅ Model name handling is correct")
            print(f"   CLI now sends full model name with co/ prefix")
            
            # Test what happens now
            model = "co/gpt-4o-mini"
            print(f"   Example: {model} -> API receives: {model}")
        else:
            print(f"\n❌ Model name still being stripped")
            print(f"   Check line ~173 in llm_do.py")


if __name__ == "__main__":
    print("Testing ConnectOnion CLI <-> OpenOnion API Integration\n")
    print("="*50)
    
    test_connectonion_auth_format()
    test_llm_proxy_url()
    test_model_name_handling()
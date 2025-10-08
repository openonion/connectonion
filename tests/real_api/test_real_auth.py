"""End-to-end test for ConnectOnion authentication with production API."""

import time
import json
import requests
from nacl.signing import SigningKey
from nacl.encoding import HexEncoder

def test_production_auth():
    """Test authentication against production API."""
    
    # Generate test keys
    signing_key = SigningKey.generate()
    public_key = "0x" + signing_key.verify_key.encode(encoder=HexEncoder).decode()
    
    # Create ConnectOnion format message
    timestamp = int(time.time())
    message = f"ConnectOnion-Auth-{public_key}-{timestamp}"
    
    # Sign the message
    signature = signing_key.sign(message.encode()).signature.hex()
    
    # Prepare request exactly as CLI does
    payload = {
        "public_key": public_key,
        "message": message,
        "signature": signature
    }
    
    print("Testing Production API Authentication")
    print("="*50)
    print(f"Public Key: {public_key[:20]}...")
    print(f"Message: {message[:50]}...")
    print(f"Timestamp: {timestamp}")
    
    # Test against production API
    api_url = "https://oo.openonion.ai/auth"
    
    try:
        print(f"\nCalling: POST {api_url}")
        response = requests.post(
            api_url,
            json=payload,
            timeout=10,
            headers={"Content-Type": "application/json"}
        )
        
        print(f"Response Status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print("✅ Authentication successful!")
            print(f"   Token: {data.get('token', '')[:20]}...")
            print(f"   Public Key Confirmed: {data.get('public_key', '')[:20]}...")
            
            # Test token validation
            if 'token' in data:
                validate_url = "https://oo.openonion.ai/api/validate"
                val_response = requests.get(
                    validate_url,
                    headers={"Authorization": f"Bearer {data['token']}"},
                    timeout=5
                )
                if val_response.status_code == 200:
                    print("✅ Token validation successful!")
                else:
                    print(f"⚠️  Token validation failed: {val_response.status_code}")
            
            return True
        else:
            print(f"❌ Authentication failed: {response.status_code}")
            print(f"   Response: {response.text[:200]}")
            return False
            
    except requests.exceptions.ConnectionError as e:
        print(f"❌ Connection failed: {e}")
        return False
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return False


def test_llm_models_endpoint():
    """Test that LLM models endpoint is accessible."""
    
    print("\n\nTesting LLM Models Endpoint")
    print("="*50)
    
    api_url = "https://oo.openonion.ai/api/llm/models"
    
    try:
        response = requests.get(api_url, timeout=5)
        print(f"Response Status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            models = data.get("models", [])
            print(f"✅ Found {len(models)} models")
            
            # Check for co/ models
            co_models = [m for m in models if m.get("id", "").startswith("co/")]
            if co_models:
                print(f"   Co/ models available: {len(co_models)}")
                for model in co_models[:3]:  # Show first 3
                    print(f"     - {model.get('id')}: {model.get('name')}")
            return True
        else:
            print(f"❌ Failed to get models: {response.status_code}")
            return False
            
    except Exception as e:
        print(f"❌ Error: {e}")
        return False


if __name__ == "__main__":
    print("ConnectOnion <-> OpenOnion Production API Test\n")
    
    auth_ok = test_production_auth()
    models_ok = test_llm_models_endpoint()
    
    print("\n" + "="*50)
    print("Test Results:")
    print(f"  Authentication: {'✅ PASSED' if auth_ok else '❌ FAILED'}")
    print(f"  LLM Models: {'✅ PASSED' if models_ok else '❌ FAILED'}")
    
    if auth_ok and models_ok:
        print("\n🎉 All tests passed! Integration is working.")
    else:
        print("\n⚠️  Some tests failed. Check the logs above.")
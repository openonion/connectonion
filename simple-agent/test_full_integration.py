#!/usr/bin/env python3
"""Test full integration with OpenOnion API using simple-agent."""

import os
import sys
import time
import json
import toml
import requests
from pathlib import Path

# Add parent for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from connectonion import Agent, llm_do, address


def test_authentication():
    """Test authenticating the simple-agent."""
    print("1. Testing Authentication")
    print("-" * 50)
    
    # Load agent keys
    co_dir = Path(".co")
    addr_data = address.load(co_dir)
    
    public_key = addr_data["address"]
    print(f"Agent address: {addr_data['short_address']}")
    
    # Create authentication message
    timestamp = int(time.time())
    message = f"ConnectOnion-Auth-{public_key}-{timestamp}"
    signature = address.sign(addr_data, message.encode()).hex()
    
    # Authenticate with production API
    response = requests.post(
        "https://oo.openonion.ai/auth",
        json={
            "public_key": public_key,
            "message": message,
            "signature": signature
        },
        timeout=10
    )
    
    if response.status_code == 200:
        data = response.json()
        token = data["token"]
        print(f"✅ Authentication successful!")
        print(f"   Token: {token[:30]}...")
        
        # Save token to config
        config_path = co_dir / "config.toml"
        config = toml.load(config_path)
        config["auth"] = {"token": token}
        with open(config_path, "w") as f:
            toml.dump(config, f)
        
        print(f"✅ Token saved to .co/config.toml")
        return token
    else:
        print(f"❌ Authentication failed: {response.status_code}")
        print(f"   Response: {response.text}")
        return None


def test_co_models(token):
    """Test using co/ models with the token."""
    print("\n2. Testing co/ Models")
    print("-" * 50)
    
    if not token:
        print("⚠️  No token, skipping co/ model tests")
        return False
    
    try:
        # Test llm_do with co/ model
        print("Testing llm_do with co/gpt-4o-mini...")
        
        response = llm_do(
            "Reply with exactly: 'ConnectOnion works!'",
            model="co/gpt-4o-mini",
            temperature=0.1
        )
        
        print(f"✅ Response: {response}")
        
        # Test with structured output
        from pydantic import BaseModel
        
        class TestResponse(BaseModel):
            status: str
            message: str
        
        structured = llm_do(
            "Create a JSON with status='success' and message='Integration test passed'",
            output=TestResponse,
            model="co/gpt-4o-mini"
        )
        
        print(f"✅ Structured response: status={structured.status}, message={structured.message}")
        
        return True
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return False


def test_email_functionality(token):
    """Test email functionality."""
    print("\n3. Testing Email Functionality")
    print("-" * 50)
    
    if not token:
        print("⚠️  No token, skipping email tests")
        return False
    
    try:
        # Check email tier
        response = requests.get(
            "https://oo.openonion.ai/api/email/tier",
            headers={"Authorization": f"Bearer {token}"},
            timeout=10
        )
        
        if response.status_code == 200:
            data = response.json()
            print(f"✅ Email tier: {data['tier']}")
            print(f"   Sender email: {data['sender_email']}")
            print(f"   Agent email: {data['agent_email']}")
            print(f"   Emails per month: {data['emails_per_month']}")
            print(f"   Quota status: {data['quota_status']}")
            
            # Update config with email info
            co_dir = Path(".co")
            config_path = co_dir / "config.toml"
            config = toml.load(config_path)
            config["agent"]["email"] = data["agent_email"]
            config["agent"]["email_active"] = True
            with open(config_path, "w") as f:
                toml.dump(config, f)
            
            print(f"✅ Email settings updated in config")
            return True
        else:
            print(f"❌ Failed to get email tier: {response.status_code}")
            return False
            
    except Exception as e:
        print(f"❌ Error: {e}")
        return False


def test_agent_with_tools():
    """Test the agent with tools and co/ models."""
    print("\n4. Testing Agent with Tools")
    print("-" * 50)
    
    try:
        # Create a simple tool
        def get_weather(city: str = "San Francisco") -> str:
            """Get the weather for a city."""
            return f"The weather in {city} is sunny and 72°F"
        
        def calculate(expression: str) -> str:
            """Calculate a mathematical expression."""
            try:
                result = eval(expression, {"__builtins__": {}}, {})
                return f"Result: {result}"
            except:
                return "Error: Invalid expression"
        
        # Create agent with co/ model
        agent = Agent(
            name="test-agent",
            tools=[get_weather, calculate],
            model="co/gpt-4o-mini"
        )
        
        # Test tool calling
        response = agent.input("What's the weather in Paris?")
        print(f"Weather query: {response}")
        
        response = agent.input("Calculate 42 * 17")
        print(f"Calculation: {response}")
        
        print(f"✅ Agent with co/ model works!")
        return True
        
    except Exception as e:
        if "authentication token" in str(e).lower():
            print(f"⚠️  No auth token - run authentication first")
        else:
            print(f"❌ Error: {e}")
        return False


def test_usage_tracking(token):
    """Test usage tracking."""
    print("\n5. Testing Usage Tracking")
    print("-" * 50)
    
    if not token:
        print("⚠️  No token, skipping usage tests")
        return False
    
    try:
        response = requests.get(
            "https://oo.openonion.ai/api/usage",
            headers={"Authorization": f"Bearer {token}"},
            timeout=10
        )
        
        if response.status_code == 200:
            data = response.json()
            print(f"✅ Usage data retrieved:")
            print(f"   Public key: {data['public_key'][:20]}...")
            print(f"   Total requests: {data.get('total_requests', 0)}")
            print(f"   Total tokens: {data.get('total_tokens', 0)}")
            print(f"   Total cost: ${data.get('total_cost', 0):.4f}")
            return True
        else:
            print(f"❌ Failed to get usage: {response.status_code}")
            return False
            
    except Exception as e:
        print(f"❌ Error: {e}")
        return False


def main():
    """Run all integration tests."""
    print("=" * 60)
    print("CONNECTONION + OPENONION FULL INTEGRATION TEST")
    print("=" * 60)
    print()
    
    # Change to simple-agent directory
    os.chdir(Path(__file__).parent)
    
    # Run tests
    token = test_authentication()
    
    if token:
        co_models_ok = test_co_models(token)
        email_ok = test_email_functionality(token)
        agent_ok = test_agent_with_tools()
        usage_ok = test_usage_tracking(token)
        
        # Summary
        print("\n" + "=" * 60)
        print("TEST SUMMARY")
        print("=" * 60)
        print(f"✅ Authentication: PASSED")
        print(f"{'✅' if co_models_ok else '❌'} Co/ Models: {'PASSED' if co_models_ok else 'FAILED'}")
        print(f"{'✅' if email_ok else '❌'} Email Functionality: {'PASSED' if email_ok else 'FAILED'}")
        print(f"{'✅' if agent_ok else '❌'} Agent with Tools: {'PASSED' if agent_ok else 'FAILED'}")
        print(f"{'✅' if usage_ok else '❌'} Usage Tracking: {'PASSED' if usage_ok else 'FAILED'}")
        
        if all([co_models_ok, email_ok, agent_ok, usage_ok]):
            print("\n🎉 ALL TESTS PASSED!")
            print("\nThe simple-agent is now:")
            print("  • Authenticated with OpenOnion")
            print("  • Can use co/ models without API keys")
            print("  • Has email functionality enabled")
            print("  • Can track usage and costs")
        else:
            print("\n⚠️  Some tests failed")
    else:
        print("\n❌ Authentication failed - cannot proceed with other tests")
        print("   Check your internet connection and try again")


if __name__ == "__main__":
    main()
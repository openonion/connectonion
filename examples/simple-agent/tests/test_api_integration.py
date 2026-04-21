#!/usr/bin/env python3
"""
OpenOnion API integration tests for ConnectOnion.

This file merges all API and authentication tests:
- test_auth.py
- test_co_model.py
- test_co_gpt4o.py
- test_full_integration.py

Run specific tests:
    python tests/test_api_integration.py --test auth
    python tests/test_api_integration.py --test co-o4-mini
    python tests/test_api_integration.py --test co-gpt4o
    python tests/test_api_integration.py --test full

Run all:
    python tests/test_api_integration.py
"""

import os
import sys
import time
import json
import toml
import requests
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from connectonion import Agent, llm_do, address
from connectonion.llm import create_llm
from pydantic import BaseModel


# ============================================================================
# Test 1: Ed25519 Authentication
# ============================================================================

def test_authentication():
    """Test Ed25519 signature-based authentication with OpenOnion API."""
    print("\n" + "=" * 70)
    print("TEST 1: Ed25519 Authentication")
    print("=" * 70 + "\n")

    print("This test demonstrates:")
    print("  • Ed25519 signature-based authentication")
    print("  • Timestamped message signing")
    print("  • JWT token retrieval")
    print("  • Token persistence to config.toml\n")

    # Load agent keys
    co_dir = Path(".co")
    if not co_dir.exists():
        print("❌ .co directory not found")
        print("   Run 'co init' first to initialize the agent")
        return None

    try:
        addr_data = address.load(co_dir)
    except Exception as e:
        print(f"❌ Failed to load agent keys: {e}")
        return None

    public_key = addr_data["address"]
    print(f"🔑 Agent address: {addr_data['short_address']}")

    # Create authentication message
    timestamp = int(time.time())
    message = f"ConnectOnion-Auth-{public_key}-{timestamp}"
    signature = address.sign(addr_data, message.encode()).hex()

    print(f"📝 Message: {message[:50]}...")
    print(f"✍️  Signature: {signature[:40]}...\n")

    # Authenticate with production API
    api_url = "https://oo.openonion.ai/auth"
    print(f"🌐 Authenticating with {api_url}")

    try:
        response = requests.post(
            api_url,
            json={
                "public_key": public_key,
                "message": message,
                "signature": signature
            },
            timeout=10
        )

        print(f"📡 Response status: {response.status_code}")

        if response.status_code == 200:
            data = response.json()
            token = data["token"]
            print(f"✅ Authentication successful!")
            print(f"   Token: {token[:30]}...")

            # Save token to config
            config_path = co_dir / "config.toml"
            config = toml.load(config_path) if config_path.exists() else {}
            if "auth" not in config:
                config["auth"] = {}
            config["auth"]["token"] = token

            with open(config_path, "w") as f:
                toml.dump(config, f)

            print(f"💾 Token saved to .co/config.toml")
            return token
        else:
            print(f"❌ Authentication failed: {response.status_code}")
            print(f"   Response: {response.text}")
            return None

    except Exception as e:
        print(f"❌ Error: {e}")
        return None


# ============================================================================
# Test 2: co/o4-mini Model
# ============================================================================

def test_co_o4_mini(token=None):
    """Test co/o4-mini model with OpenOnion managed keys."""
    print("\n" + "=" * 70)
    print("TEST 2: co/o4-mini Model")
    print("=" * 70 + "\n")

    print("This test demonstrates:")
    print("  • Using co/o4-mini model via OpenOnion")
    print("  • LLM initialization with managed keys")
    print("  • Simple completion API call\n")

    # Check for config
    config_path = Path(".co/config.toml")
    if not config_path.exists():
        print("❌ No config found at .co/config.toml")
        print("   Run authentication test first")
        return False

    config = toml.load(config_path)
    if "auth" not in config or "token" not in config["auth"]:
        print("❌ No auth token in config")
        print("   Run authentication test first")
        return False

    saved_token = config["auth"]["token"]
    print(f"✓ Found token: {saved_token[:20]}...")

    # Create LLM
    try:
        print("\nCreating co/o4-mini LLM...")
        llm = create_llm("co/o4-mini")
        print(f"✓ LLM created successfully")
        print(f"  Base URL: {llm.client.base_url}")
        print(f"  Model: {llm.model}")
    except Exception as e:
        print(f"❌ Failed to create LLM: {e}")
        return False

    # Test completion
    try:
        print("\nTesting completion...")
        messages = [
            {"role": "user", "content": "Answer in one word: What is 2+2?"}
        ]

        response = llm.complete(messages)
        print(f"✅ Completion successful")
        print(f"   Response: {response.content}")
        return True

    except Exception as e:
        print(f"❌ Completion failed: {e}")
        return False


# ============================================================================
# Test 3: co/gpt-4o Model
# ============================================================================

def test_co_gpt4o(token=None):
    """Test co/gpt-4o model with OpenOnion managed keys."""
    print("\n" + "=" * 70)
    print("TEST 3: co/gpt-4o Model")
    print("=" * 70 + "\n")

    print("This test demonstrates:")
    print("  • Using co/gpt-4o model via OpenOnion")
    print("  • Testing different model variants\n")

    try:
        print("Creating co/gpt-4o LLM...")
        llm = create_llm("co/gpt-4o")
        print("✓ Created co/gpt-4o LLM")

        messages = [
            {"role": "user", "content": "Say 'Hello' and nothing else."}
        ]

        response = llm.complete(messages)
        print(f"✅ Response: {response.content}")
        return True

    except Exception as e:
        print(f"❌ Error: {e}")
        return False


# ============================================================================
# Test 4: Full Integration Test
# ============================================================================

def test_full_integration():
    """Comprehensive integration test covering auth, models, email, and usage."""
    print("\n" + "=" * 70)
    print("TEST 4: Full Integration Test")
    print("=" * 70 + "\n")

    print("This test demonstrates:")
    print("  • End-to-end authentication flow")
    print("  • Multiple co/ model usage")
    print("  • Email functionality")
    print("  • Agent with tools")
    print("  • Usage tracking\n")

    # Step 1: Authentication
    print("Step 1/5: Authentication")
    print("-" * 70)
    token = test_authentication()

    if not token:
        print("\n❌ Authentication failed - cannot proceed")
        return False

    # Step 2: Test co/ models
    print("\nStep 2/5: Testing co/ Models")
    print("-" * 70)

    try:
        print("Testing llm_do with co/gpt-4o-mini...")

        response = llm_do(
            "Reply with exactly: 'ConnectOnion works!'",
            model="co/gpt-4o-mini",
            temperature=0.1
        )

        print(f"✅ Response: {response}")

        # Test with structured output
        class TestResponse(BaseModel):
            status: str
            message: str

        structured = llm_do(
            "Create a JSON with status='success' and message='Integration test passed'",
            output=TestResponse,
            model="co/gpt-4o-mini"
        )

        print(f"✅ Structured response: status={structured.status}, message={structured.message}")
        co_models_ok = True

    except Exception as e:
        print(f"❌ Error: {e}")
        co_models_ok = False

    # Step 3: Test email functionality
    print("\nStep 3/5: Testing Email Functionality")
    print("-" * 70)

    try:
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
            if "agent" not in config:
                config["agent"] = {}
            config["agent"]["email"] = data["agent_email"]
            config["agent"]["email_active"] = True

            with open(config_path, "w") as f:
                toml.dump(config, f)

            print(f"✅ Email settings updated in config")
            email_ok = True
        else:
            print(f"❌ Failed to get email tier: {response.status_code}")
            email_ok = False

    except Exception as e:
        print(f"❌ Error: {e}")
        email_ok = False

    # Step 4: Test agent with tools
    print("\nStep 4/5: Testing Agent with Tools")
    print("-" * 70)

    try:
        # Create simple tools
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

        # Create agent
        agent = Agent(
            name="test-agent",
            tools=[get_weather, calculate],
            model="co/gpt-4o-mini"
        )

        # Test tool calling
        response = agent.input("What's the weather in Paris?")
        print(f"✅ Weather query: {response[:100]}...")

        response = agent.input("Calculate 42 * 17")
        print(f"✅ Calculation: {response[:100]}...")

        print(f"✅ Agent with co/ model works!")
        agent_ok = True

    except Exception as e:
        if "authentication token" in str(e).lower():
            print(f"⚠️  No auth token - run authentication first")
        else:
            print(f"❌ Error: {e}")
        agent_ok = False

    # Step 5: Test usage tracking
    print("\nStep 5/5: Testing Usage Tracking")
    print("-" * 70)

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
            usage_ok = True
        else:
            print(f"❌ Failed to get usage: {response.status_code}")
            usage_ok = False

    except Exception as e:
        print(f"❌ Error: {e}")
        usage_ok = False

    # Summary
    print("\n" + "=" * 70)
    print("FULL INTEGRATION TEST SUMMARY")
    print("=" * 70)
    print(f"✅ Authentication: PASSED")
    print(f"{'✅' if co_models_ok else '❌'} Co/ Models: {'PASSED' if co_models_ok else 'FAILED'}")
    print(f"{'✅' if email_ok else '❌'} Email Functionality: {'PASSED' if email_ok else 'FAILED'}")
    print(f"{'✅' if agent_ok else '❌'} Agent with Tools: {'PASSED' if agent_ok else 'FAILED'}")
    print(f"{'✅' if usage_ok else '❌'} Usage Tracking: {'PASSED' if usage_ok else 'FAILED'}")

    all_passed = all([co_models_ok, email_ok, agent_ok, usage_ok])

    if all_passed:
        print("\n🎉 ALL INTEGRATION TESTS PASSED!")
        print("\nThe simple-agent is now:")
        print("  • Authenticated with OpenOnion")
        print("  • Can use co/ models without API keys")
        print("  • Has email functionality enabled")
        print("  • Can track usage and costs")
    else:
        print("\n⚠️  Some integration tests failed")

    return all_passed


# ============================================================================
# Main Test Runner
# ============================================================================

def run_all_tests():
    """Run all API integration tests."""
    print("\n" + "=" * 70)
    print("RUNNING ALL API INTEGRATION TESTS")
    print("=" * 70)

    # Change to simple-agent directory if not there
    if Path.cwd().name != "simple-agent":
        agent_dir = Path(__file__).parent.parent
        os.chdir(agent_dir)
        print(f"Changed directory to: {agent_dir}\n")

    # Run authentication first
    token = test_authentication()

    if not token:
        print("\n❌ Authentication failed - skipping other tests")
        return False

    # Run other tests
    tests = [
        ("co/o4-mini Model", lambda: test_co_o4_mini(token)),
        ("co/gpt-4o Model", lambda: test_co_gpt4o(token)),
    ]

    results = {"Authentication": True}  # Auth already passed

    for name, test_func in tests:
        try:
            result = test_func()
            results[name] = result
        except Exception as e:
            print(f"\n❌ Test '{name}' failed with error: {e}")
            import traceback
            traceback.print_exc()
            results[name] = False

    # Summary
    print("\n" + "=" * 70)
    print("TEST SUMMARY")
    print("=" * 70)
    for name, passed in results.items():
        status = "✅ PASSED" if passed else "❌ FAILED"
        print(f"{status}: {name}")

    all_passed = all(results.values())
    if all_passed:
        print("\n🎉 ALL TESTS PASSED!")
    else:
        print("\n⚠️  Some tests failed")

    return all_passed


def main():
    """Main entry point with argument parsing."""
    if len(sys.argv) > 1:
        command = sys.argv[1]

        if command == "--test":
            if len(sys.argv) < 3:
                print("Usage: python test_api_integration.py --test [auth|co-o4-mini|co-gpt4o|full]")
                return 1

            # Change to simple-agent directory
            if Path.cwd().name != "simple-agent":
                os.chdir(Path(__file__).parent.parent)

            test_name = sys.argv[2]
            tests = {
                "auth": test_authentication,
                "co-o4-mini": test_co_o4_mini,
                "co-gpt4o": test_co_gpt4o,
                "full": test_full_integration,
            }

            if test_name in tests:
                result = tests[test_name]()
                return 0 if result or result is not False else 1
            else:
                print(f"Unknown test: {test_name}")
                print(f"Available tests: {', '.join(tests.keys())}")
                return 1

        else:
            print(f"Unknown command: {command}")
            print("Usage: python test_api_integration.py [--test TEST_NAME]")
            return 1

    # No arguments - run all tests
    return 0 if run_all_tests() else 1


if __name__ == "__main__":
    sys.exit(main())

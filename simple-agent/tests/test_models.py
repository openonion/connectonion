#!/usr/bin/env python3
"""
Model-specific integration tests for ConnectOnion.

This file merges all model-specific tests:
- test_gemini_env.py
- test_with_mock.py
- test_minimal_template.py

Run specific tests:
    python tests/test_models.py --test gemini
    python tests/test_models.py --test mock
    python tests/test_models.py --test template

Run all:
    python tests/test_models.py
"""

import os
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from connectonion import Agent
from dotenv import load_dotenv


# ============================================================================
# Test 1: Gemini with .env Loading
# ============================================================================

def test_gemini_dotenv():
    """Test Gemini API key loading from .env file."""
    print("\n" + "=" * 70)
    print("TEST 1: Gemini with .env Loading")
    print("=" * 70 + "\n")

    print("This test demonstrates:")
    print("  • .env file integration with Agent")
    print("  • GEMINI_API_KEY and GOOGLE_API_KEY support")
    print("  • Agent initialization with Gemini models\n")

    # Check if dotenv is imported in core modules
    print("Step 1: Checking core modules for load_dotenv()")
    print("-" * 70)

    agent_file = Path(__file__).parent.parent.parent / "connectonion" / "agent.py"
    llm_do_file = Path(__file__).parent.parent.parent / "connectonion" / "llm_do.py"

    if agent_file.exists():
        with open(agent_file) as f:
            agent_content = f.read()
            has_dotenv = "load_dotenv()" in agent_content
            print(f"  agent.py: {'✅ Has load_dotenv()' if has_dotenv else '❌ Missing load_dotenv()'}")
    else:
        print(f"  agent.py: ⚠️  File not found")

    if llm_do_file.exists():
        with open(llm_do_file) as f:
            llm_do_content = f.read()
            has_dotenv = "load_dotenv()" in llm_do_content
            print(f"  llm_do.py: {'✅ Has load_dotenv()' if has_dotenv else '❌ Missing load_dotenv()'}")
    else:
        print(f"  llm_do.py: ⚠️  File not found")

    # Check .env file
    print("\nStep 2: Checking .env file")
    print("-" * 70)

    env_file = Path(".env")
    if env_file.exists():
        print(f"  .env exists: ✅")
        with open(env_file) as f:
            env_content = f.read()
            has_gemini = "GEMINI_API_KEY" in env_content
            has_google = "GOOGLE_API_KEY" in env_content
            print(f"  Has GEMINI_API_KEY: {'✅' if has_gemini else '❌'}")
            print(f"  Has GOOGLE_API_KEY (backward compat): {'✅' if has_google else '❌'}")
    else:
        print(f"  .env exists: ❌")
        print("  Create a .env file with GEMINI_API_KEY to test")

    # Test environment variable loading
    print("\nStep 3: Testing environment variable loading")
    print("-" * 70)

    load_dotenv()

    gemini_key = os.getenv("GEMINI_API_KEY")
    google_key = os.getenv("GOOGLE_API_KEY")
    openai_key = os.getenv("OPENAI_API_KEY")

    print(f"  GEMINI_API_KEY: {'✅ Found' if gemini_key else '❌ Not found'}")
    print(f"  GOOGLE_API_KEY (backward compat): {'✅ Found' if google_key else '❌ Not found'}")
    print(f"  OPENAI_API_KEY: {'✅ Found' if openai_key else '❌ Not found'}")

    # Test Agent creation
    print("\nStep 4: Testing Agent creation with Gemini model")
    print("-" * 70)

    try:
        agent = Agent(
            name="gemini_test",
            model="gemini-1.5-flash"
        )
        print("  ✅ Agent created successfully")
        print(f"  Model: {agent.llm.model}")
        return True

    except ValueError as e:
        error_msg = str(e)
        if "API key required" in error_msg:
            print(f"  ❌ Agent creation failed: {error_msg}")
            print("  → This means .env file is not being loaded or API key is missing!")
        else:
            print(f"  ❌ Agent creation failed: {error_msg}")
        return False

    except Exception as e:
        print(f"  ⚠️  Unexpected error: {type(e).__name__}: {e}")
        return False


# ============================================================================
# Test 2: co/o4-mini with Mock
# ============================================================================

def test_co_model_with_mock():
    """Test co/o4-mini model using mocked OpenAI client."""
    print("\n" + "=" * 70)
    print("TEST 2: co/o4-mini with Mock")
    print("=" * 70 + "\n")

    print("This test demonstrates:")
    print("  • Mocked API responses for testing")
    print("  • co/o4-mini specific parameters (max_completion_tokens, temperature)")
    print("  • Agent tool calling flow without network calls\n")

    # Define test tool
    def hello_world(name: str = "World") -> str:
        """Simple greeting function."""
        return f"Hello, {name}! Welcome to ConnectOnion."

    # Create mock response
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = "Hello! I've used the hello_world tool to greet you."

    # Mock tool call
    mock_tool_call = MagicMock()
    mock_tool_call.function.name = "hello_world"
    mock_tool_call.function.arguments = '{"name": "User"}'
    mock_tool_call.id = "call_123"
    mock_response.choices[0].message.tool_calls = [mock_tool_call]

    # Mock the OpenAI client
    with patch('connectonion.llm.openai.OpenAI') as mock_openai:
        mock_client = MagicMock()
        mock_openai.return_value = mock_client
        mock_client.base_url = "https://oo.openonion.ai/v1/"
        mock_client.api_key = "mock-token"

        # First call returns tool call, second returns final response
        final_response = MagicMock()
        final_response.choices = [MagicMock()]
        final_response.choices[0].message.content = "Hello, User! Welcome to ConnectOnion."
        final_response.choices[0].message.tool_calls = None

        mock_client.chat.completions.create.side_effect = [mock_response, final_response]

        # Create agent
        print("Creating agent with co/o4-mini model...")
        try:
            agent = Agent(
                name="test-agent",
                tools=[hello_world],
                model="co/o4-mini"
            )

            print(f"✓ Agent created with model: {agent.llm.model}")
            print(f"✓ Base URL: {agent.llm.client.base_url}")

            # Test with tool
            print("\nTesting agent with hello_world tool...")
            response = agent.input("Say hello to the user")
            print(f"✓ Response: {response}")

            # Verify parameters
            calls = mock_client.chat.completions.create.call_args_list
            print(f"\n✓ Made {len(calls)} API calls")

            # Check first call parameters
            first_call = calls[0][1]
            print(f"✓ Model: {first_call['model']}")
            print(f"✓ max_completion_tokens: {first_call.get('max_completion_tokens', 'Not set')}")
            print(f"✓ temperature: {first_call.get('temperature', 'Not set')}")
            print(f"✓ Has tools: {'tools' in first_call}")

            # Verify o4-mini specific parameters
            assert first_call['model'] == 'co/o4-mini'
            assert first_call['max_completion_tokens'] == 16384
            assert first_call['temperature'] == 1
            assert 'max_tokens' not in first_call

            print("\n✅ All parameter checks passed!")
            print("\nNote: This test used mocked responses.")
            print("With a valid token, the agent would make real API calls.")
            return True

        except Exception as e:
            print(f"❌ Test failed: {e}")
            import traceback
            traceback.print_exc()
            return False


# ============================================================================
# Test 3: Template .env Loading
# ============================================================================

def test_template_dotenv_loading():
    """Test that minimal template has .env loading."""
    print("\n" + "=" * 70)
    print("TEST 3: Template .env Loading")
    print("=" * 70 + "\n")

    print("This test demonstrates:")
    print("  • CLI templates include .env support")
    print("  • Templates have load_dotenv() call\n")

    template_path = Path(__file__).parent.parent.parent / "connectonion" / "cli" / "templates" / "minimal" / "agent.py"

    if not template_path.exists():
        print(f"❌ Template not found at: {template_path}")
        return False

    print(f"Checking template: {template_path.name}")
    print("-" * 70)

    with open(template_path) as f:
        content = f.read()

        has_import = "from dotenv import load_dotenv" in content
        has_call = "load_dotenv()" in content

        print(f"  Has import statement: {'✅' if has_import else '❌'}")
        print(f"  Has load_dotenv() call: {'✅' if has_call else '❌'}")

        if has_import and has_call:
            print("\n✅ Minimal template will load .env file correctly!")
            return True
        else:
            print("\n❌ Template missing load_dotenv setup!")
            return False


# ============================================================================
# Main Test Runner
# ============================================================================

def run_all_tests():
    """Run all model-specific tests."""
    print("\n" + "=" * 70)
    print("RUNNING ALL MODEL-SPECIFIC TESTS")
    print("=" * 70)

    # Change to simple-agent directory if needed
    if Path.cwd().name != "simple-agent":
        agent_dir = Path(__file__).parent.parent
        if agent_dir.exists():
            os.chdir(agent_dir)
            print(f"Changed directory to: {agent_dir}\n")

    tests = [
        ("Gemini with .env", test_gemini_dotenv),
        ("co/o4-mini with Mock", test_co_model_with_mock),
        ("Template .env Loading", test_template_dotenv_loading),
    ]

    results = {}
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
                print("Usage: python test_models.py --test [gemini|mock|template]")
                return 1

            # Change to simple-agent directory
            if Path.cwd().name != "simple-agent":
                agent_dir = Path(__file__).parent.parent
                if agent_dir.exists():
                    os.chdir(agent_dir)

            test_name = sys.argv[2]
            tests = {
                "gemini": test_gemini_dotenv,
                "mock": test_co_model_with_mock,
                "template": test_template_dotenv_loading,
            }

            if test_name in tests:
                result = tests[test_name]()
                return 0 if result else 1
            else:
                print(f"Unknown test: {test_name}")
                print(f"Available tests: {', '.join(tests.keys())}")
                return 1

        else:
            print(f"Unknown command: {command}")
            print("Usage: python test_models.py [--test TEST_NAME]")
            return 1

    # No arguments - run all tests
    return 0 if run_all_tests() else 1


if __name__ == "__main__":
    sys.exit(main())

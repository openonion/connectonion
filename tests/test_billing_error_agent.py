"""
Test how ConnectOnion agent developers see billing errors.

This simulates a real developer using the Agent class and hitting insufficient credits.
We want to ensure the error message is clear and actionable.
"""
import pytest
import sys
import os

# Add connectonion to path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from connectonion import Agent
from connectonion.core.exceptions import InsufficientCreditsError

# API key with very low credits ($0.0001)
LOW_CREDIT_API_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJwdWJsaWNfa2V5IjoiMHhjYzliNmI0ZGZlOGVhMDE0NDIxYzhmMWRjZDI2NDhjZWQ2OTE0ZTdkNzczZTk2MjllZWU3N2IzMDc4YjRkNDA2IiwiZXhwIjoyMDc2OTgyNzU3LCJpYXQiOjE3NjE2MjI3NTd9.sPrK_idOZ-vhdFgXRKel4w2ez4cYltFK0SdGfOzEGFo"


@pytest.mark.integration
def test_beautiful_error_message():
    """
    Test that developers see a beautiful, clear error message with ConnectOnion branding.

    This is the main user experience test - what does a developer actually see?
    """
    agent = Agent(
        name="billing_test",
        model="co/gemini-2.5-pro",
        api_key=LOW_CREDIT_API_KEY,
        quiet=True,
        log=False
    )

    # Expect our custom exception
    with pytest.raises(InsufficientCreditsError) as exc_info:
        agent.input("Write a detailed explanation of quantum computing")

    error = exc_info.value
    error_message = str(error)

    # Print what developers will actually see
    print("\n" + "="*80)
    print("WHAT DEVELOPERS SEE:")
    print("="*80)
    print(error_message)
    print("="*80)

    # Verify it's our custom exception, not generic OpenAI error
    assert isinstance(error, InsufficientCreditsError), \
        "Should be InsufficientCreditsError, not openai.APIStatusError"

    # Verify the beautiful formatted message
    assert "❌ Insufficient ConnectOnion Credits" in error_message, \
        "Should have clear ConnectOnion branding"
    assert "Account:" in error_message, "Should show account address"
    assert "Balance:" in error_message, "Should show current balance"
    assert "Required:" in error_message, "Should show request cost"
    assert "Shortfall:" in error_message, "Should show how much more is needed"
    assert "discord.gg" in error_message, "Should include Discord link"
    assert "co status" in error_message, "Should mention 'co status' command"


@pytest.mark.integration
def test_exception_has_typed_attributes():
    """
    Test that the exception has typed attributes for programmatic access.

    Developers should be able to access balance, cost, etc. directly.
    """
    agent = Agent(
        name="billing_test",
        model="co/gemini-2.5-pro",
        api_key=LOW_CREDIT_API_KEY,
        quiet=True,
        log=False
    )

    with pytest.raises(InsufficientCreditsError) as exc_info:
        agent.input("Write 500 words about AI")

    error = exc_info.value

    # Check typed attributes exist and are correct types
    assert isinstance(error.balance, (int, float)), "balance should be a number"
    assert isinstance(error.required, (int, float)), "required should be a number"
    assert isinstance(error.shortfall, (int, float)), "shortfall should be a number"
    assert isinstance(error.address, str), "address should be a string"
    assert isinstance(error.public_key, str), "public_key should be a string"

    # Verify values make sense
    assert error.balance >= 0, "balance should be non-negative"
    assert error.required > 0, "required cost should be positive"
    assert error.shortfall > 0, "shortfall should be positive"
    assert error.address != "unknown", "address should be provided by server"

    print(f"\n✅ Exception attributes:")
    print(f"   balance={error.balance:.4f}")
    print(f"   required={error.required:.4f}")
    print(f"   shortfall={error.shortfall:.4f}")
    print(f"   address={error.address}")


@pytest.mark.integration
def test_programmatic_error_handling():
    """
    Test that developers can catch and handle billing errors specifically.

    This is the improved developer experience - no string parsing needed!
    """
    agent = Agent(
        name="billing_test",
        model="co/gemini-2.5-pro",
        api_key=LOW_CREDIT_API_KEY,
        quiet=True,
        log=False
    )

    try:
        agent.input("Hello world")
        pytest.fail("Should have raised InsufficientCreditsError")
    except InsufficientCreditsError as e:
        # This is clean! No string parsing, just catch the specific exception
        print(f"\n✅ Clean exception handling:")
        print(f"   Need ${e.shortfall:.4f} more credits")
        print(f"   Account: {e.address}")
        assert e.shortfall > 0


if __name__ == "__main__":
    """Run tests with pytest"""
    import subprocess
    result = subprocess.run(
        ["pytest", __file__, "-v", "-s"],
        cwd=os.path.dirname(os.path.dirname(__file__))
    )
    sys.exit(result.returncode)

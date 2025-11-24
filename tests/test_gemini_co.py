"""Test Gemini models via direct API and co/ managed keys"""
import os
import pytest
from connectonion import Agent, llm_do

# Set Gemini API key for direct tests
os.environ.setdefault('GEMINI_API_KEY', 'AIzaSyCMBM2LTb-5AYtrjMa1xfPdqj8NNSH9F34')


@pytest.mark.real_api
def test_gemini_flash_direct():
    """Test Gemini 2.5 Flash via direct API"""
    agent = Agent(
        name="test-gemini-direct",
        model="gemini-2.5-flash"  # Direct, no co/ prefix
    )
    response = agent.input("Say hello in one word")
    assert response, "No response from Gemini Flash"
    print(f"Gemini Flash response: {response}")


@pytest.mark.real_api
def test_gemini_pro_direct():
    """Test Gemini 2.5 Pro via direct API"""
    agent = Agent(
        name="test-gemini-pro-direct",
        model="gemini-2.5-pro"  # Direct, no co/ prefix
    )
    response = agent.input("What is 2+2? Just the number.")
    assert response, "No response from Gemini Pro"
    print(f"Gemini Pro response: {response}")


@pytest.mark.real_api
def test_llm_do_gemini_direct():
    """Test llm_do with Gemini model via direct API"""
    result = llm_do("Say hi", model="gemini-2.5-flash")
    assert result, "No result from llm_do with Gemini"
    print(f"llm_do Gemini result: {result}")


@pytest.mark.real_api
@pytest.mark.skip(reason="Requires co/ account with credits")
def test_gemini_flash_via_co():
    """Test Gemini 2.5 Flash via co/ managed keys"""
    agent = Agent(
        name="test-gemini-co",
        model="co/gemini-2.5-flash"
    )
    response = agent.input("Say hello in one word")
    assert response, "No response from Gemini Flash"
    print(f"Gemini Flash (co/) response: {response}")


if __name__ == "__main__":
    print("Testing Gemini models...")

    print("\n1. Testing Gemini Flash (direct API)...")
    test_gemini_flash_direct()
    print("   ✓ Passed")

    print("\n2. Testing Gemini Pro (direct API)...")
    test_gemini_pro_direct()
    print("   ✓ Passed")

    print("\n3. Testing llm_do with Gemini (direct API)...")
    test_llm_do_gemini_direct()
    print("   ✓ Passed")

    print("\n✅ All Gemini tests passed!")

"""Test Gemini models via direct API and co/ managed keys"""
import os
import pytest
from connectonion import Agent, llm_do

# Gemini API key must be set in environment (never hardcode!)
# Set GEMINI_API_KEY before running these tests


@pytest.mark.skipif(not os.getenv('GEMINI_API_KEY'), reason="GEMINI_API_KEY not set")
def test_gemini_flash_direct():
    """Test Gemini 2.5 Flash via direct API"""
    agent = Agent(
        name="test-gemini-direct",
        model="gemini-2.5-flash"  # Direct, no co/ prefix
    )
    response = agent.input("Say hello in one word")
    assert response, "No response from Gemini Flash"
    print(f"Gemini Flash response: {response}")


@pytest.mark.skipif(not os.getenv('GEMINI_API_KEY'), reason="GEMINI_API_KEY not set")
def test_gemini_pro_direct():
    """Test Gemini 2.5 Pro via direct API"""
    agent = Agent(
        name="test-gemini-pro-direct",
        model="gemini-2.5-pro"  # Direct, no co/ prefix
    )
    response = agent.input("What is 2+2? Just the number.")
    assert response, "No response from Gemini Pro"
    print(f"Gemini Pro response: {response}")


@pytest.mark.skipif(not os.getenv('GEMINI_API_KEY'), reason="GEMINI_API_KEY not set")
def test_llm_do_gemini_direct():
    """Test llm_do with Gemini model via direct API"""
    result = llm_do("Say hi", model="gemini-2.5-flash")
    assert result, "No result from llm_do with Gemini"
    print(f"llm_do Gemini result: {result}")


@pytest.mark.skip(reason="Requires co/ account with credits")
def test_gemini_flash_via_co():
    """Test Gemini 2.5 Flash via co/ managed keys"""
    agent = Agent(
        name="test-gemini-co",
        model="co/gemini-2.5-flash"
    )
    response = agent.input("Say hello in one word")
    assert response, "No response from Gemini Flash"

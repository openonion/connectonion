"""Shared fixtures and markers for real API tests.

Design:
- Static conditions (env vars) → @skipif decorators (evaluated at collection)
- Dynamic conditions (network) → fixtures that skip (evaluated at runtime)
- NO 'if' statements inside test bodies for skipping

Usage:
    from tests.real_api.conftest import requires_openai

    @requires_openai
    def test_openai_completion():
        ...

    def test_with_auth(auth_token):  # fixture skips if auth fails
        ...
"""

import os
import time
from pathlib import Path

import pytest
import requests
from dotenv import load_dotenv
from nacl.signing import SigningKey
from nacl.encoding import HexEncoder


# =============================================================================
# Environment Loading (once at import)
# =============================================================================

_env_path = Path(__file__).parent / ".env"
load_dotenv(_env_path) if _env_path.exists() else load_dotenv()


# =============================================================================
# Auto-mark all tests in this folder as real_api
# =============================================================================

def pytest_collection_modifyitems(items):
    for item in items:
        if "real_api" in str(item.fspath):
            item.add_marker(pytest.mark.real_api)


# =============================================================================
# Skip Markers (static - no side effects at import)
# =============================================================================

requires_openai = pytest.mark.skipif(
    not os.getenv("OPENAI_API_KEY"),
    reason="OPENAI_API_KEY not set"
)

requires_anthropic = pytest.mark.skipif(
    not os.getenv("ANTHROPIC_API_KEY"),
    reason="ANTHROPIC_API_KEY not set"
)

requires_gemini = pytest.mark.skipif(
    not os.getenv("GEMINI_API_KEY") and not os.getenv("GOOGLE_API_KEY"),
    reason="GEMINI_API_KEY or GOOGLE_API_KEY not set"
)

requires_any_provider = pytest.mark.skipif(
    not (os.getenv("OPENAI_API_KEY") or os.getenv("ANTHROPIC_API_KEY") or
         os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")),
    reason="No API keys available"
)

requires_multiple_providers = pytest.mark.skipif(
    sum([
        bool(os.getenv("OPENAI_API_KEY")),
        bool(os.getenv("ANTHROPIC_API_KEY")),
        bool(os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY"))
    ]) < 2,
    reason="Need at least 2 providers for comparison test"
)


# =============================================================================
# Fixtures (dynamic - network calls at runtime, not import)
# =============================================================================

@pytest.fixture
def localhost_available():
    """Skip test if localhost:8000 is not reachable."""
    try:
        requests.get("http://localhost:8000/health", timeout=1)
    except (requests.exceptions.ConnectionError, requests.exceptions.Timeout):
        pytest.skip("localhost:8000 not available")


@pytest.fixture
def signing_keypair():
    """Generate Ed25519 keypair for authentication."""
    signing_key = SigningKey.generate()
    public_key = "0x" + signing_key.verify_key.encode(encoder=HexEncoder).decode()
    return signing_key, public_key


@pytest.fixture
def auth_payload(signing_keypair):
    """Generate signed authentication payload."""
    signing_key, public_key = signing_keypair
    timestamp = int(time.time())
    message = f"ConnectOnion-Auth-{public_key}-{timestamp}"
    signature = signing_key.sign(message.encode()).signature.hex()
    return {"public_key": public_key, "message": message, "signature": signature}


@pytest.fixture
def auth_token(auth_payload):
    """Get authentication token from production API. Skips if auth fails."""
    response = requests.post(
        "https://oo.openonion.ai/auth",
        json=auth_payload,
        timeout=10,
        headers={"Content-Type": "application/json"}
    )
    if response.status_code != 200:
        pytest.skip(f"Failed to get auth token: {response.status_code}")
    return response.json().get("token")


@pytest.fixture
def api_headers(auth_token):
    """Headers with auth token for API requests."""
    return {"Authorization": f"Bearer {auth_token}", "Content-Type": "application/json"}


# =============================================================================
# Test Tool Fixtures
# =============================================================================

@pytest.fixture
def calculator_tool():
    def calculator(a: int, b: int) -> int:
        """Add two numbers together."""
        return a + b
    return calculator


@pytest.fixture
def greeting_tool():
    def greet(name: str) -> str:
        """Generate a greeting for a person."""
        return f"Hello, {name}!"
    return greet


@pytest.fixture
def test_tools(calculator_tool, greeting_tool):
    """Bundle of test tools for agent testing."""
    return [calculator_tool, greeting_tool]

"""Pytest configuration and shared fixtures for ConnectOnion tests."""

import pytest
import tempfile
import shutil
import json
from pathlib import Path
from unittest.mock import Mock, MagicMock
from connectonion import Agent
# No need to import tools - they're just functions
from connectonion.llm import LLMResponse, ToolCall, OpenAILLM
import os
from dotenv import load_dotenv

# Load .env file for API keys
load_dotenv()


@pytest.fixture
def temp_dir():
    """Create a temporary directory for tests."""
    temp_dir = tempfile.mkdtemp()
    yield temp_dir
    shutil.rmtree(temp_dir)


@pytest.fixture
def mock_openai_client():
    """Create a mock OpenAI client for testing."""
    mock_client = MagicMock()
    
    # Default successful response
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = "Test response"
    mock_response.choices[0].message.tool_calls = None
    
    mock_client.chat.completions.create.return_value = mock_response
    return mock_client


@pytest.fixture
def mock_llm():
    """Create a mock LLM instance."""
    mock = Mock(spec=OpenAILLM)
    mock.complete.return_value = LLMResponse(
        content="Mock response",
        tool_calls=[],
        raw_response=None
    )
    return mock


# Tool functions for testing
def calculator(expression: str) -> str:
    """Perform mathematical calculations."""
    try:
        result = eval(expression)
        return f"Result: {result}"
    except Exception as e:
        return f"Error: {str(e)}"

def current_time() -> str:
    """Get the current time."""
    from datetime import datetime
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def read_file(file_path: str) -> str:
    """Read content from a file."""
    try:
        with open(file_path, 'r') as f:
            return f.read()
    except FileNotFoundError:
        return f"Error: File not found: {file_path}"
    except Exception as e:
        return f"Error: {str(e)}"

@pytest.fixture
def sample_tools():
    """Standard set of test tools."""
    return [calculator, current_time, read_file]


@pytest.fixture
def test_agent(temp_dir, mock_llm, sample_tools):
    """Create a test agent with logging to temp directory."""
    # Use temp directory for logging instead of default .co/logs/
    log_file = Path(temp_dir) / "test_agent.log"
    agent = Agent(name="test_agent", llm=mock_llm, tools=sample_tools, log=log_file)
    return agent


@pytest.fixture
def sample_behavior_records():
    """Sample behavior records for testing."""
    return [
        {
            "timestamp": "2025-07-28T10:00:00.000000",
            "task": "Calculate 2 + 2",
            "tool_calls": [
                {
                    "name": "calculator",
                    "arguments": {"expression": "2 + 2"},
                    "call_id": "call_123",
                    "result": "Result: 4",
                    "status": "success"
                }
            ],
            "result": "The answer is 4",
            "duration_seconds": 1.5
        },
        {
            "timestamp": "2025-07-28T10:01:00.000000",
            "task": "What time is it?",
            "tool_calls": [
                {
                    "name": "current_time",
                    "arguments": {},
                    "call_id": "call_456",
                    "result": "2025-07-28 10:01:00",
                    "status": "success"
                }
            ],
            "result": "Current time is 10:01 AM",
            "duration_seconds": 0.8
        }
    ]


@pytest.fixture
def sample_openai_responses():
    """Sample OpenAI API responses for testing."""
    return {
        "simple_text": {
            "id": "chatcmpl-123",
            "object": "chat.completion",
            "choices": [{
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": "Hello! I'm a helpful assistant."
                },
                "finish_reason": "stop"
            }]
        },
        "tool_calling": {
            "id": "chatcmpl-456", 
            "object": "chat.completion",
            "choices": [{
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [{
                        "id": "call_abc123",
                        "type": "function",
                        "function": {
                            "name": "calculator",
                            "arguments": '{"expression": "2 + 2"}'
                        }
                    }]
                },
                "finish_reason": "tool_calls"
            }]
        }
    }


@pytest.fixture
def test_files(temp_dir):
    """Create test files for ReadFile tool testing."""
    files = {}
    
    # Normal text file
    normal_file = Path(temp_dir) / "normal.txt"
    normal_file.write_text("Hello, ConnectOnion!")
    files["normal"] = str(normal_file)
    
    # Empty file
    empty_file = Path(temp_dir) / "empty.txt"
    empty_file.write_text("")
    files["empty"] = str(empty_file)
    
    # Large file
    large_file = Path(temp_dir) / "large.txt"
    large_content = "Line {}\n" * 10000
    large_file.write_text(large_content.format(*range(10000)))
    files["large"] = str(large_file)
    
    # Unicode file
    unicode_file = Path(temp_dir) / "unicode.txt"
    unicode_file.write_text("Hello 🌍 世界 🚀", encoding="utf-8")
    files["unicode"] = str(unicode_file)
    
    return files


@pytest.fixture
def openai_api_key():
    """Provide test API key."""
    return "sk-test-key-for-testing-only"


# Load environment variables from tests/.env
env_file = Path(__file__).parent / ".env"
if env_file.exists():
    load_dotenv(env_file)
else:
    print("\n⚠️  Warning: tests/.env not found!")
    print("   Some tests may fail without API keys.")
    print("   Copy tests/.env.example to tests/.env and add your API keys.\n")


# Network test fixtures
@pytest.fixture
def relay_url():
    """
    Default relay URL for network tests.

    Uses production relay server by default.
    Override with --relay-url flag or RELAY_URL env var.
    """
    return os.getenv("RELAY_URL", "wss://oo.openonion.ai/ws/announce")


@pytest.fixture
def local_relay_url():
    """Local relay URL for development/testing."""
    return "ws://localhost:8000/ws/announce"


@pytest.fixture
def relay_url_from_cli(request):
    """Get relay URL from command line or use default."""
    if request.config.getoption("--use-local-relay"):
        return "ws://localhost:8000/ws/announce"
    return request.config.getoption("--relay-url")


# Test markers and CLI options
def pytest_configure(config):
    """Configure custom pytest markers."""
    config.addinivalue_line("markers", "slow: marks tests as slow (deselect with '-m \"not slow\"')")
    config.addinivalue_line("markers", "integration: marks tests as integration tests")
    config.addinivalue_line("markers", "unit: marks tests as unit tests")
    config.addinivalue_line("markers", "benchmark: marks tests as performance benchmarks")


def pytest_addoption(parser):
    """Add custom command line options."""
    parser.addoption(
        "--relay-url",
        action="store",
        default="wss://oo.openonion.ai/ws/announce",
        help="Relay server URL for network tests"
    )
    parser.addoption(
        "--use-local-relay",
        action="store_true",
        help="Use local relay server (ws://localhost:8000/ws/announce)"
    )


def pytest_collection_modifyitems(config, items):
    """Auto-skip tests that need API keys if keys are missing."""

    # Check for API keys
    has_openai = bool(os.getenv("OPENAI_API_KEY"))
    has_anthropic = bool(os.getenv("ANTHROPIC_API_KEY"))
    has_google = bool(os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY"))
    has_openonion = bool(os.getenv("OPENONION_API_KEY"))

    has_any_key = has_openai or has_anthropic or has_google or has_openonion

    if not has_any_key:
        skip_marker = pytest.mark.skip(
            reason="API keys not found. Copy tests/.env.example to tests/.env and add your keys."
        )
        for item in items:
            if "real_api" in item.keywords:
                item.add_marker(skip_marker)

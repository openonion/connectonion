"""Pytest configuration and shared fixtures for ConnectOnion tests."""

"""
LLM-Note: Global pytest configuration and shared test fixtures

What it tests:
- pytest_configure: Registers custom test markers (slow, integration, unit, benchmark, e2e_online)
- pytest_addoption: CLI options for relay URL configuration
- pytest_collection_modifyitems: Auto-marks tests by folder path, skips real_api tests if API keys missing

Shared fixtures provided:
- temp_dir: Temporary directory for test isolation
- mock_openai_client: Mock OpenAI client with default responses
- mock_llm: MockLLM instance with standard response
- sample_tools: Standard test tools (calculator, current_time, read_file)
- test_agent: Pre-configured test agent with mocked LLM
- sample_behavior_records: Example behavior data for testing
- sample_openai_responses: Mock API response payloads
- test_files: Pre-created test files (normal, empty, large, unicode)
- relay_url: Default relay server URL for network tests
- openai_api_key: Test API key fixture

Components under test:
- connectonion.Agent
- connectonion.core.llm (LLMResponse, ToolCall, OpenAILLM)
- tests.utils.mock_helpers.MockLLM
"""

import pytest
import tempfile
import shutil
import json
from pathlib import Path
from unittest.mock import Mock, MagicMock
from connectonion import Agent
# No need to import tools - they're just functions
from connectonion.core.llm import LLMResponse, ToolCall, OpenAILLM
from connectonion.core.usage import TokenUsage
from tests.utils.mock_helpers import MockLLM
import os
from dotenv import load_dotenv

# Load .env file for API keys
load_dotenv()


@pytest.fixture(autouse=True)
def _never_touch_the_real_home(monkeypatch, tmp_path_factory):
    """No test may read or write the operator's real ~/.co.

    `CliRunner.isolated_filesystem()` isolates the working directory and
    nothing else, so a test that ran `co auth microsoft` against mocked HTTP
    still wrote its fake tokens into the real ~/.co/keys.env — overwriting a
    live Outlook session with `access_token='eyJ0eXAi.test'`. The failure
    surfaced days later as "Microsoft session expired", which is the last thing
    anyone would trace back to a test run.

    Isolating HOME is the only guard that holds: the paths are resolved deep
    inside the commands, from Path.home() and from AGENT_CONFIG_PATH, and a
    per-test patch has to be remembered by every future test.
    """
    home = tmp_path_factory.mktemp("home")
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))       # Windows
    monkeypatch.setenv("AGENT_CONFIG_PATH", str(home / ".co"))
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))


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
    return MockLLM(responses=[
        LLMResponse(
            content="Mock response",
            tool_calls=[],
            raw_response=None,
            usage=TokenUsage(),
        )
    ])


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
    return os.getenv("RELAY_URL", "wss://oo.openonion.ai")


@pytest.fixture
def local_relay_url():
    """Local relay URL for development/testing."""
    return "ws://localhost:8000"


@pytest.fixture
def relay_url_from_cli(request):
    """Get relay URL from command line or use default."""
    if request.config.getoption("--use-local-relay"):
        return "ws://localhost:8000"
    return request.config.getoption("--relay-url")


# Test markers and CLI options
def pytest_configure(config):
    """Configure custom pytest markers."""
    config.addinivalue_line("markers", "slow: marks tests as slow (deselect with '-m \"not slow\"')")
    config.addinivalue_line("markers", "unit: marks tests as unit tests")
    config.addinivalue_line("markers", "e2e_online: marks real API end-to-end tests")


def pytest_addoption(parser):
    """Add custom command line options."""
    parser.addoption(
        "--relay-url",
        action="store",
        default="wss://oo.openonion.ai",
        help="Relay server URL for network tests"
    )
    parser.addoption(
        "--use-local-relay",
        action="store_true",
        help="Use local relay server (ws://localhost:8000)"
    )


def pytest_collection_modifyitems(config, items):
    """Auto-mark tests by folder and skip real_api if keys are missing."""

    # Auto-mark tests based on folder path
    for item in items:
        path = Path(str(item.fspath))
        parts = set(path.parts)
        if "unit" in parts:
            item.add_marker(pytest.mark.unit)
        if "cli" in parts:
            item.add_marker(pytest.mark.cli)
        if "e2e" in parts:
            item.add_marker(pytest.mark.e2e)
        if "real_api" in parts:
            item.add_marker(pytest.mark.real_api)

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


@pytest.fixture(autouse=True)
def _forget_seen_signatures():
    """One CONNECT signature opens one connection (#649), and the record of
    which ones have been used is process-global -- it has to be, because the
    replay being refused happens across connections.

    That makes it state one test hands to the next. Several test files send a
    hardcoded `"signature": "0xsig"`, so without this the second test to use
    one is refused for a reason that has nothing to do with what it checks.
    """
    from connectonion.network.host.auth import _seen_signatures

    _seen_signatures.clear()
    yield
    _seen_signatures.clear()


@pytest.fixture(autouse=True)
def _no_stray_project_above_the_test(tmp_path_factory):
    """A `.co/` in a shared parent silently becomes every test's project.

    `_never_touch_the_real_home` above isolates HOME, so `~/.co` is safe. This
    is the other half: `project_root()` walks up from the *working directory*,
    and a stray `.co/` anywhere above it wins.

    Measured (#694): real-host verification runs left a `/private/tmp/.co/`
    behind, and afterwards a unit test with nothing to do with any of it failed

        assert logger.log_file_path == Path(".co/logs/test-agent.log").resolve()
        E  assert PosixPath('/private/tmp/.co/logs/test-agent.log') == …

    standalone, not only in some order -- so `-p no:randomly` does not hide it.
    It is invisible on CI, where the machine is clean, which is the worst
    property: a local run disagrees with CI for a reason nobody can reproduce.

    This does not repoint anything. Tests that chdir into their own project
    depend on the walk-up finding it, and pinning the answer would break them.
    It only refuses to let the walk-up escape somewhere shared, so the
    contamination is a failure with a name instead of a wrong answer.
    """
    from connectonion.project import project_root

    yield

    try:
        resolved = project_root()
    except (FileNotFoundError, OSError):
        # A test whose working directory was a tmp dir that has since been
        # removed has no cwd to resolve from. That is not contamination, and
        # raising here turned a passing test into an error on CI -- where tmp
        # dirs are cleaned more eagerly than on my machine, which is why this
        # only showed there.
        return
    tmp_root = tmp_path_factory.getbasetemp().resolve()
    repo = Path(__file__).resolve().parent.parent

    allowed = resolved == repo or resolved.is_relative_to(tmp_root) \
        or resolved.is_relative_to(repo)
    assert allowed, (
        f"this test's project resolved to {resolved}, which is neither the repo "
        f"nor its own tmp dir — a stray .co/ above the working directory is "
        f"deciding what the code under test reads. Remove it ({resolved / '.co'}) "
        f"or chdir somewhere isolated."
    )

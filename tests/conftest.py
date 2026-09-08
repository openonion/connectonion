"""Pytest configuration and shared fixtures for ConnectOnion tests.

LLM-Note: Global pytest configuration and shared test fixtures

Module level: FORCE_COLOR & co. are stripped so output matches CI.

Policy fixtures (autouse, apply to every test):
- _isolate_selected_environment: no provider selection leaks between tests
- _never_touch_the_real_home: HOME and ~/.co are a fresh tmp dir per test
- _restore_excepthook: sys.excepthook installed by a test does not outlive it
- _no_network: any test in the default run that opens a non-loopback socket fails
- _no_leaked_threads: a test that leaves a thread running fails in teardown
- _retire_legacy_browser_workers: legacy browser worker threads are retired after each test
- _forget_seen_signatures: CONNECT replay memory is cleared between tests
- _no_stray_project_above_the_test: a stray .co/ above cwd is a failure, not a wrong answer

Shared fixtures:
- temp_dir, mock_llm, sample_tools, test_agent, test_files, relay_url
- default_backend_url: for tests about backend URL resolution itself

Markers are auto-applied by folder in pytest_collection_modifyitems; see
tests/TEST_ORGANIZATION.md.
"""

import os
import socket
import sys
import tempfile
import shutil
import threading
from pathlib import Path

import pytest

# Strip the colour-forcing variables a developer's shell may carry, *before*
# connectonion is imported: its module-level Rich consoles read FORCE_COLOR
# once, at construction. Dozens of tests assert on the plain text a command
# prints; CI has none of these set, so Rich sees a pipe and emits no escape
# codes there. A shell with FORCE_COLOR=3 (Claude Code sets it) made 43 of
# those tests fail locally while CI stayed green — the worst kind of
# disagreement, because the local run looks like the broken one. Subprocesses
# inherit os.environ, so this covers `co` invoked as a child too.
for _name in ("FORCE_COLOR", "CLICOLOR_FORCE", "CLICOLOR", "COLORTERM", "NO_COLOR", "PY_COLORS"):
    os.environ.pop(_name, None)

from connectonion import Agent
from connectonion.core.llm import LLMResponse
from connectonion.core.usage import TokenUsage
from tests.utils.mock_helpers import MockLLM


@pytest.fixture(autouse=True)
def _isolate_selected_environment(request, monkeypatch):
    """Auth/refresh and CLI selection cannot leak process state to another test."""
    if request.node.get_closest_marker("real_api"):
        yield
        return
    from unittest.mock import patch
    from connectonion import environment
    monkeypatch.setattr(environment, "_loaded", dict(environment._loaded))
    monkeypatch.setattr(environment, "_selected", None)
    with patch.dict(os.environ):
        for provider in environment.PROVIDER_PREFIXES:
            for key in environment.provider_keys(provider):
                os.environ.pop(key, None)
        yield


@pytest.fixture(autouse=True)
def _never_touch_the_real_home(request, monkeypatch, tmp_path_factory):
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

    `real_api` is the one exception, because provider CLIs keep their
    credentials under $HOME as well: `codex` reads an OAuth session from
    ~/.codex/auth.json, and with HOME repointed it finds none and the turn
    dies at the provider with `401 Missing bearer`. Reaching the operator's
    real account is the entire purpose of those tests, they are opt-in behind
    a marker, and they are deselected from the default run — so they keep the
    real HOME while every other test is isolated.
    """
    if request.node.get_closest_marker("real_api"):
        return

    home = tmp_path_factory.mktemp("home")
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))       # Windows
    # Clear inherited routing; the isolated HOME is the default. Tests that
    # exercise a custom global directory select it explicitly.
    monkeypatch.delenv("AGENT_CONFIG_PATH", raising=False)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))




@pytest.fixture(autouse=True)
def _restore_excepthook():
    """`auto_debug_exception()` installs a global sys.excepthook and nothing
    removes it. Left in place, every later uncaught exception in the run would
    try to build a debug Agent and call an LLM."""
    saved = sys.excepthook
    yield
    sys.excepthook = saved


_OFFLINE_EXEMPT_MARKERS = ("real_api", "network", "deploy", "provider_cli", "e2e_online", "public_cross_repo")
_LOOPBACK_HOSTS = {"", "localhost", "127.0.0.1", "::1", "0.0.0.0", "::"}


def _is_loopback(address) -> bool:
    host = address[0] if isinstance(address, tuple) else address
    if isinstance(host, bytes):
        host = host.decode(errors="replace")
    if not isinstance(host, str):
        return True
    return host in _LOOPBACK_HOSTS or host.startswith("127.") or host.endswith(".localhost")


@pytest.fixture(autouse=True)
def _no_network(request, monkeypatch):
    """A test in the default run must not reach the network.

    Tests that need it say so with a marker (network, real_api, deploy, ...)
    and are deselected by default. Everything else is supposed to be offline,
    but nothing enforced that: a unit test that mocked the console and forgot
    the LLM built a real Agent and called the API with the key "test-key", and
    CI sat on it for the full 300s timeout (2026-09-08, main).

    Two things happen on a violation. The connect raises ConnectionRefusedError
    right away, which is what the code under test would see on a machine with
    no network, so nothing hangs. And the test fails in teardown naming the
    host, even if the code under test swallowed the error — a silent fallback
    is exactly the kind of thing this exists to surface.
    """
    if any(request.node.get_closest_marker(m) for m in _OFFLINE_EXEMPT_MARKERS):
        yield
        return

    # Point every backend client at a port nothing listens on. 57 tests were
    # reaching production through the default URL on every run — `co init`,
    # `co doctor`, host startup — and passing only because the fallback for a
    # backend that answers 401 to "test-key" happens to look like the fallback
    # for no backend at all. A test that wants a backend answer mocks it.
    monkeypatch.setenv("CONNECTONION_BACKEND_URL", "http://127.0.0.1:9")

    attempts = []
    real_connect = socket.socket.connect
    real_connect_ex = socket.socket.connect_ex

    def _refuse(sock, address):
        if sock.family in (socket.AF_INET, socket.AF_INET6) and not _is_loopback(address):
            attempts.append(address)
            raise ConnectionRefusedError(
                f"tests/conftest.py refused a network connection to {address!r}: "
                "this test is not marked network/real_api, so it must not leave the machine"
            )

    def connect(sock, address):
        _refuse(sock, address)
        return real_connect(sock, address)

    def connect_ex(sock, address):
        _refuse(sock, address)
        return real_connect_ex(sock, address)

    monkeypatch.setattr(socket.socket, "connect", connect)
    monkeypatch.setattr(socket.socket, "connect_ex", connect_ex)
    yield
    if attempts:
        hosts = sorted({f"{a[0]}:{a[1]}" if isinstance(a, tuple) and len(a) > 1 else str(a) for a in attempts})
        pytest.fail(
            f"this test tried to reach the network ({', '.join(hosts)}). "
            "Mock the client, or mark the test `network`/`real_api` if leaving the machine is the point."
        )


# Threads that outlive a test by design and cannot be ended from one:
# - pool workers that executors keep around between tasks (idle, owned by the
#   pool, no API to retire one)
# - the process-wide event loop that runs async tools (started once, lazily,
#   by connectonion.core.tool_executor; shared by every later async tool call)
_LONG_LIVED_THREAD_PREFIXES = ("ThreadPoolExecutor-", "asyncio_", "connectonion-async-tools")


@pytest.fixture(autouse=True)
def _no_leaked_threads(request):
    """A test that leaves a thread running fails, in teardown, by name.

    Measured before this existed: four modules left 39 `registry-cleanup`
    threads behind, one per create_app(). Nothing failed. Later in the same
    run a test patched time.sleep to a no-op, the 39 spun flat out, and the
    main thread starved until the 300s timeout — seven red runs on main in
    two weeks, none of them from the test that was blamed (#1246).

    A thread that has not finished by the end of the test gets a short grace
    (workers that are wrapping up), then the test fails naming it. The fix is
    always in the test or the code it exercises: stop what you start.
    """
    before = {t.ident for t in threading.enumerate()}
    yield
    fresh = [t for t in threading.enumerate() if t.ident not in before]
    for t in fresh:
        if t.is_alive():
            t.join(timeout=0.5)
    leaked = [t for t in fresh if t.is_alive() and not t.name.startswith(_LONG_LIVED_THREAD_PREFIXES)]
    if leaked:
        names = ", ".join(f"{t.name} (daemon={t.daemon})" for t in leaked)
        pytest.fail(
            f"this test left {len(leaked)} thread(s) running: {names}. "
            "Stop or join them before the test ends."
        )


@pytest.fixture(autouse=True)
def _retire_legacy_browser_workers(monkeypatch):
    """Every LegacyBrowserAutomation built during a test has its worker retired after it.

    The legacy class starts a worker thread in __init__ and only `close()`
    retires it. Tests build it with fake pages and never close, and whether
    the worker exited before the thread guard looked depended on when the
    cyclic GC happened to free the instance — a guard that fails on GC timing
    is a flaky guard. Tracking the instances makes it deterministic.
    """
    from connectonion.useful_tools.browser_tools.browser import LegacyBrowserAutomation

    made = []
    original_init = LegacyBrowserAutomation.__init__

    def tracking_init(self, *args, **kwargs):
        made.append(self)
        original_init(self, *args, **kwargs)

    monkeypatch.setattr(LegacyBrowserAutomation, "__init__", tracking_init)
    yield
    for browser in made:
        browser._retire_worker()


@pytest.fixture
def default_backend_url(monkeypatch):
    """Undo the dead-port redirect for a test that is *about* URL resolution.

    Returns the production origin so the test can assert against it without
    spelling it out. Every request is still mocked or refused by _no_network;
    only the string changes.
    """
    from connectonion.backend import DEFAULT_BACKEND_URL
    monkeypatch.delenv("CONNECTONION_BACKEND_URL", raising=False)
    return DEFAULT_BACKEND_URL


@pytest.fixture
def temp_dir():
    """Create a temporary directory for tests."""
    temp_dir = tempfile.mkdtemp()
    yield temp_dir
    shutil.rmtree(temp_dir)



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
def relay_url():
    """
    Default relay URL for network tests.

    Uses the production relay server by default; override with RELAY_URL.
    """
    return os.getenv("RELAY_URL", "wss://oo.openonion.ai")



def _needs_environment_api_key(item):
    return "real_api" in item.keywords and "provider_cli" not in item.keywords


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
            if _needs_environment_api_key(item):
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

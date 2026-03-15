"""Tests for CLI template modules with stubbed connectonion API."""
"""
LLM-Note: Tests for cli templates

What it tests:
- Cli Templates functionality

Components under test:
- Module: cli_templates
"""


import importlib.util
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TEMPLATE_ROOT = ROOT / "connectonion" / "cli" / "templates"

# Keep explicit module paths for coverage tracking
TEMPLATE_MODULES = [
    "connectonion.cli.templates.minimal.agent",
    "connectonion.cli.templates.browser.agent",
    "connectonion.cli.templates.web-research.agent",
]


class StubAgent:
    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs

    def input(self, prompt):
        return "stub-response"

    def list_tools(self):
        return []


class StubXray:
    messages = []

    def __call__(self, func=None, *args, **kwargs):
        return func


class StubBrowserAutomation:
    def __init__(self, *args, **kwargs):
        pass


def _load_with_stub(path: Path):
    # Create stub modules
    stub = types.ModuleType("connectonion")
    stub.Agent = StubAgent
    stub.llm_do = lambda *a, **k: "llm"
    stub.xray = StubXray()
    # Add all file tools the templates import
    stub.bash = lambda *a, **k: "bash"
    stub.read_file = lambda *a, **k: "content"
    stub.edit = lambda *a, **k: "edited"
    stub.glob = lambda *a, **k: []
    stub.grep = lambda *a, **k: []
    stub.write = lambda *a, **k: "wrote"

    # Stub submodules
    stub_useful_plugins = types.ModuleType("connectonion.useful_plugins")
    stub_useful_plugins.image_result_formatter = []
    stub_useful_plugins.tool_approval = []
    stub_useful_plugins.ui_stream = []

    stub_useful_tools = types.ModuleType("connectonion.useful_tools")
    stub_browser_tools = types.ModuleType("connectonion.useful_tools.browser_tools")
    stub_browser_tools.BrowserAutomation = StubBrowserAutomation

    # Save originals
    originals = {}
    modules_to_stub = [
        "connectonion",
        "connectonion.useful_plugins",
        "connectonion.useful_tools",
        "connectonion.useful_tools.browser_tools",
    ]
    for mod_name in modules_to_stub:
        originals[mod_name] = sys.modules.get(mod_name)

    # Install stubs
    sys.modules["connectonion"] = stub
    sys.modules["connectonion.useful_plugins"] = stub_useful_plugins
    sys.modules["connectonion.useful_tools"] = stub_useful_tools
    sys.modules["connectonion.useful_tools.browser_tools"] = stub_browser_tools

    name = f"_template_{path.stem}_{abs(hash(str(path)))}"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)

    try:
        spec.loader.exec_module(module)  # type: ignore[union-attr]
    finally:
        # Restore originals
        for mod_name in modules_to_stub:
            if originals[mod_name] is not None:
                sys.modules[mod_name] = originals[mod_name]
            else:
                sys.modules.pop(mod_name, None)
    return module


def test_template_minimal_loads():
    path = TEMPLATE_ROOT / "minimal" / "agent.py"
    module = _load_with_stub(path)
    assert isinstance(module.agent, StubAgent)
    # Note: result is only defined inside if __name__ == "__main__" block


def test_template_browser_loads():
    path = TEMPLATE_ROOT / "browser" / "agent.py"
    module = _load_with_stub(path)
    # Browser template uses create_agent() factory function
    assert callable(module.create_agent)
    agent = module.create_agent()
    assert isinstance(agent, StubAgent)


def test_template_web_research_functions(tmp_path, monkeypatch):
    path = TEMPLATE_ROOT / "web-research" / "agent.py"
    module = _load_with_stub(path)

    assert "Searching for" in module.search_web("topic")

    # Patch requests.get in module using monkeypatch (auto-restored after test)
    class Resp:
        status_code = 200
        text = "hello world"

        def raise_for_status(self):
            return None

    monkeypatch.setattr(module.requests, "get", lambda *a, **k: Resp())

    data = module.extract_data("http://example.com")
    assert data["status"] == 200

    analysis = module.analyze_data("data", analysis_type="summary")
    assert analysis == "llm"

    out_file = tmp_path / "research.json"
    msg = module.save_research("topic", ["a", "b"], filename=str(out_file))
    assert out_file.exists()
    assert "Research saved" in msg

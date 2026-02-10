"""Tests for CLI template modules with stubbed connectonion API."""

import importlib.util
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TEMPLATE_ROOT = ROOT / "connectonion" / "cli" / "templates"

# Keep explicit module paths for coverage tracking
TEMPLATE_MODULES = [
    "connectonion.cli.templates.minimal.agent",
    "connectonion.cli.templates.meta-agent.agent",
    "connectonion.cli.templates.playwright.agent",
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


def _load_with_stub(path: Path):
    stub = types.ModuleType("connectonion")
    stub.Agent = StubAgent
    stub.llm_do = lambda *a, **k: "llm"
    stub.xray = StubXray()

    original = sys.modules.get("connectonion")
    sys.modules["connectonion"] = stub

    name = f"_template_{path.stem}_{abs(hash(str(path)))}"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)

    try:
        spec.loader.exec_module(module)  # type: ignore[union-attr]
    finally:
        # restore original connectonion
        if original is not None:
            sys.modules["connectonion"] = original
        else:
            sys.modules.pop("connectonion", None)
    return module


def test_template_minimal_loads():
    path = TEMPLATE_ROOT / "minimal" / "agent.py"
    module = _load_with_stub(path)
    assert isinstance(module.agent, StubAgent)
    assert getattr(module, "result", "") == "stub-response"


def test_template_meta_agent_loads():
    path = TEMPLATE_ROOT / "meta-agent" / "agent.py"
    module = _load_with_stub(path)
    assert isinstance(module.agent, StubAgent)


def test_template_playwright_loads():
    path = TEMPLATE_ROOT / "playwright" / "agent.py"
    module = _load_with_stub(path)
    assert isinstance(module.agent, StubAgent)


def test_template_web_research_functions(tmp_path):
    path = TEMPLATE_ROOT / "web-research" / "agent.py"
    module = _load_with_stub(path)

    assert "Searching for" in module.search_web("topic")

    # Patch requests.get in module
    class Resp:
        status_code = 200
        text = "hello world"

        def raise_for_status(self):
            return None

    module.requests.get = lambda *a, **k: Resp()

    data = module.extract_data("http://example.com")
    assert data["status"] == 200

    analysis = module.analyze_data("data", analysis_type="summary")
    assert analysis == "llm"

    out_file = tmp_path / "research.json"
    msg = module.save_research("topic", ["a", "b"], filename=str(out_file))
    assert out_file.exists()
    assert "Research saved" in msg

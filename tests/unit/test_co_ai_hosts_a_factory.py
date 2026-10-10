"""`co ai` and the `co create` template give each hosted request its own Agent.

Both used to pass one Agent instance to host(), so every conversation shared
it. They now pass a factory. Loading an agent.py for `co eval` / benchmarks
still finds the Agent when the file passes a factory to host().
"""

import shutil
from pathlib import Path

import pytest

import connectonion
from connectonion import Agent
from connectonion.cli.co_ai import main as co_ai_main
from connectonion.cli.commands.eval_commands import get_agent_from_file
from tests.utils.mock_helpers import MockLLM

pytestmark = pytest.mark.usefixtures("own_project")
TEMPLATE = Path(connectonion.__file__).parent / "cli" / "templates" / "co-ai" / "agent.py"


def test_co_ai_serves_a_fresh_agent_per_request(monkeypatch):
    hosted = {}
    monkeypatch.setattr(co_ai_main, "host", lambda target, **kw: hosted.setdefault("target", target))
    monkeypatch.setattr(co_ai_main, "load_host_config", lambda *a, **k: None, raising=False)
    monkeypatch.setattr(co_ai_main.threading, "Thread", lambda *a, **k: type("T", (), {"start": lambda s: None})())
    built = []

    def factory(model, max_iterations, full_access, turns):
        agent = Agent("co", system_prompt="p", llm=MockLLM(), quiet=True)
        built.append(agent)
        return agent

    co_ai_main.start_server(None, port=0, model="co/gemini-3.8-flash", max_iterations=5,
                            full_access=True, full_access_turns=7, agent_factory=factory)

    create = hosted["target"]
    assert callable(create) and not isinstance(create, Agent)
    first, second = create(), create()
    assert first is not second
    assert first._full_access_turns == 7 and second._full_access_turns == 7


def test_the_template_passes_a_factory_and_still_loads_for_eval(tmp_path):
    source = TEMPLATE.read_text()
    assert "host(lambda: create_agent(" in source
    project = tmp_path / "proj"
    project.mkdir()
    shutil.copy(TEMPLATE, project / "agent.py")

    agent = get_agent_from_file("agent.py", str(project))

    assert isinstance(agent, Agent)


def test_a_module_level_agent_still_loads(tmp_path):
    (tmp_path / "agent.py").write_text(
        "from connectonion import Agent, host\n"
        "agent = Agent('a', system_prompt='p', model='co/gemini-3.8-flash', quiet=True)\n"
        "host(agent)\n")
    assert get_agent_from_file("agent.py", str(tmp_path)).name == "a"


def test_a_factory_hosted_only_under_main_still_loads(tmp_path):
    """#1778: `host(create_agent)` inside `if __name__ == "__main__"` never
    runs on import, so eval found no Agent and called a valid Host file
    malformed. The conventional `create_agent` factory is the fallback."""
    (tmp_path / "agent.py").write_text(
        "from connectonion import Agent, host\n"
        "def create_agent():\n"
        "    return Agent('guest', system_prompt='p', model='co/gemini-3.8-flash', quiet=True)\n"
        "if __name__ == '__main__':\n"
        "    host(create_agent)\n")

    assert get_agent_from_file("agent.py", str(tmp_path)).name == "guest"

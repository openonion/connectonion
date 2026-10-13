"""One host: `co host`, `python agent.py`, `co deploy` and `co ai` serve the same things (#2438, #2439).

Before 1.9.2b19, what a host served depended on the command that started it.
`co ai` answered REM requests and chat channels; `python agent.py`, and so
every `co deploy`, did neither, and `.co/host.yaml` had no way to ask for
them. And on a machine where co came from install.sh (every `co handoff`
mail installs it that way), the `python agent.py` that `co create` printed
failed at once, because the system python cannot import a uv tool's packages.
"""

import asyncio
import sys
from pathlib import Path

import pytest
from typer.testing import CliRunner

from connectonion.cli.main import app


# ---- co host: agent.py with co's own interpreter ----

def test_co_host_runs_agent_py_with_the_python_co_runs_on(tmp_path, monkeypatch):
    seen = tmp_path / "seen.txt"
    (tmp_path / "agent.py").write_text(
        "import os, sys\n"
        f"open({str(seen)!r}, 'w').write(sys.executable + '|' + os.environ.get('AGENT_PORT', ''))\n")
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(app, ["host", "--port", "8123"])

    assert result.exit_code == 0, result.output
    assert seen.read_text() == f"{sys.executable}|8123"


def test_co_host_without_an_agent_py_says_how_to_make_one(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(app, ["host"])

    assert result.exit_code == 2
    assert "agent.py" in result.output and "co create" in result.output


def test_co_host_passes_on_how_agent_py_ended(tmp_path, monkeypatch):
    (tmp_path / "agent.py").write_text("raise SystemExit(3)\n")
    monkeypatch.chdir(tmp_path)

    assert CliRunner().invoke(app, ["host"]).exit_code == 3


# ---- host() serves REM and answers channels, from host.yaml ----

@pytest.fixture
def project(tmp_path, monkeypatch):
    from connectonion import address
    co = tmp_path / ".co"
    co.mkdir()
    address.save(address.generate(), co)
    monkeypatch.chdir(tmp_path)
    return co


def _host(project, monkeypatch, yaml_text: str, **kwargs) -> dict:
    """Run host() up to the server and return what it built the app with."""
    from connectonion import Agent
    from connectonion.network.host import server
    (project / "host.yaml").write_text("name: t\nentrypoint: agent.py\nport: 8125\ntrust: careful\n" + yaml_text)
    built = {}
    real = server.asgi_create_app

    def capture(**app_kwargs):
        built.update(app_kwargs)
        return real(**app_kwargs)
    monkeypatch.setattr(server, "asgi_create_app", capture)
    monkeypatch.setattr(server.uvicorn, "run", lambda app, **kw: None)
    server.host(lambda: Agent("t", tools=[], model="co/gemini-2.5-flash", api_key="k"), relay_url=None, **kwargs)
    return built


def test_a_plain_host_serves_rem_by_default(project, monkeypatch):
    built = _host(project, monkeypatch, "")
    assert built["route_handlers"]["rem_root"] == (Path.home() / ".co" / "rem").resolve()


def test_host_yaml_can_turn_rem_off(project, monkeypatch):
    built = _host(project, monkeypatch, "rem: false\n")
    assert built["route_handlers"]["rem_root"] is None


def test_the_code_parameter_still_wins_for_rem(project, monkeypatch, tmp_path):
    built = _host(project, monkeypatch, "rem: false\n", rem_root=tmp_path / "elsewhere")
    assert built["route_handlers"]["rem_root"] == (tmp_path / "elsewhere").resolve()


@pytest.fixture
def consumers(monkeypatch):
    """The channels a host starts consumers for, without starting any."""
    from connectonion.inbox import consumer
    started = []
    monkeypatch.setattr(consumer, "serve_with_listener", lambda inbox, handler, **kw: started.append(inbox.provider))
    return started


def test_a_plain_host_answers_the_channels_in_host_yaml(project, monkeypatch, consumers):
    built = _host(project, monkeypatch, "listen:\n  telegram: {}\n")
    asyncio.run(built["on_startup"]())
    asyncio.run(built["on_shutdown"]())
    assert consumers == ["telegram"]


def test_channels_passed_in_code_replace_the_file(project, monkeypatch, consumers):
    built = _host(project, monkeypatch, "listen:\n  telegram: {}\n", listen=[])
    asyncio.run(built["on_startup"]())
    asyncio.run(built["on_shutdown"]())
    assert consumers == []


def test_co_ai_answers_each_channel_once_through_the_host(monkeypatch):
    """co ai started its own listener thread and passed ~/.co to host(), whose inbox lifespan
    read the same host.yaml: two consumers per channel, with two different session rules."""
    import threading
    from connectonion.cli.commands import ai_commands
    from connectonion.cli.co_ai import main as co_ai_main
    from connectonion.inbox.settings import Channel
    hosted = {}
    monkeypatch.setattr(ai_commands, "_channels", lambda override: [Channel("telegram")])
    monkeypatch.setattr(co_ai_main, "host", lambda *a, **kw: hosted.update(kw))
    monkeypatch.setenv("OPENONION_API_KEY", "k")
    before = {t.name for t in threading.enumerate()}

    result = CliRunner().invoke(app, ["ai", "--no-launch", "--port", "8126"])
    assert result.exit_code == 0, result.output

    assert [c.provider for c in hosted["listen"]] == ["telegram"]
    assert {t.name for t in threading.enumerate()} - before == set()


def test_any_host_answers_questions_on_handoffs_it_sent(project, monkeypatch):
    """#2453: only co ai ran the handoff watcher, so a sender on co host, python agent.py or co deploy
    never answered; the recipient's `status --wait` waited until the sender happened to run status."""
    from connectonion.handoff import watch
    started, stopped = [], []

    class Stop:
        def set(self):
            stopped.append(True)
    monkeypatch.setattr(watch, "start", lambda *a, **kw: started.append(True) or Stop())
    built = _host(project, monkeypatch, "")
    asyncio.run(built["on_startup"]())
    asyncio.run(built["on_shutdown"]())
    assert started == [True] and stopped == [True]


def test_co_ai_does_not_start_a_second_handoff_watcher(monkeypatch):
    from connectonion.cli.commands import ai_commands
    from connectonion.cli.co_ai import main as co_ai_main
    from connectonion.handoff import watch
    started = []
    monkeypatch.setattr(watch, "start", lambda *a, **kw: started.append(True))
    monkeypatch.setattr(ai_commands, "_channels", lambda override: [])
    hosted = {}
    monkeypatch.setattr(co_ai_main, "host", lambda *a, **kw: hosted.update(kw))
    monkeypatch.setenv("OPENONION_API_KEY", "k")
    assert CliRunner().invoke(app, ["ai", "--no-launch", "--port", "8127"]).exit_code == 0
    asyncio.run(hosted["on_agent_startup"]())
    asyncio.run(hosted["on_agent_shutdown"]())
    assert started == []

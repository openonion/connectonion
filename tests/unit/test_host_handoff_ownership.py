"""A project Host must not inherit another configuration's pending handoffs."""
import asyncio
import threading
from unittest.mock import Mock

import pytest

from connectonion import Agent, address
from connectonion.handoff import watch
from connectonion.network.host import server


@pytest.fixture
def directories(tmp_path, monkeypatch):
    global_dir, project = tmp_path / 'operator', tmp_path / 'project' / '.co'
    global_dir.mkdir()
    project.mkdir(parents=True)
    monkeypatch.setenv('AGENT_CONFIG_PATH', str(global_dir))
    return global_dir, project


def test_project_host_does_not_start_the_ambient_watcher(directories, monkeypatch):
    global_dir, project = directories
    start = Mock()
    monkeypatch.setattr(watch, 'start', start)

    startup, shutdown = server._create_handoff_lifespan(project)

    assert startup is None and shutdown is None
    start.assert_not_called()
    assert not (global_dir / 'handoff').exists()


def test_matching_configuration_keeps_start_and_shutdown(directories, monkeypatch):
    global_dir, _ = directories
    stop = threading.Event()
    start = Mock(return_value=stop)
    monkeypatch.setattr(watch, 'start', start)
    startup, shutdown = server._create_handoff_lifespan(global_dir)

    asyncio.run(startup())
    start.assert_called_once_with()
    assert not stop.is_set()
    asyncio.run(shutdown())
    assert stop.is_set()


def test_normalized_directory_has_the_same_ownership(directories, monkeypatch):
    global_dir, project = directories
    alias = project.parent / '..' / global_dir.name
    start = Mock(return_value=threading.Event())
    monkeypatch.setattr(watch, 'start', start)

    startup, shutdown = server._create_handoff_lifespan(alias)
    asyncio.run(startup())
    asyncio.run(shutdown())
    start.assert_called_once_with()


def test_host_passes_its_configuration_to_watcher_ownership(directories, monkeypatch):
    _, project = directories
    address.save(address.generate(), project)
    monkeypatch.chdir(project.parent)
    monkeypatch.setattr('connectonion.cli.commands.agent_index.refresh', lambda: [])
    monkeypatch.setattr(server.uvicorn, 'run', lambda app, **options: None)
    lifespan = Mock(return_value=(None, None))
    monkeypatch.setattr(server, '_create_handoff_lifespan', lifespan)

    server.host(Agent('owned-host', model='co/gemini-3.7-flash', api_key='fixture-key', log=False),
                port=18766, co_dir=project, relay_url=None, listen=[], trust='strict')

    lifespan.assert_called_once_with(project)

import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

from connectonion.network.host.control_center.controller import ControlCenterController, update_control_center
from connectonion.network.host.control_center.runtime import ControlCenterRuntime, ReviewResult, RuntimeErrorState


@pytest.fixture
def controller(tmp_path):
    build = tmp_path / 'build'; build.mkdir()
    (build / 'index.html').write_text('<h1>test</h1>')
    runtime = ControlCenterRuntime(tmp_path / 'state', policy='test',
        reviewer=lambda b: ReviewResult('approved', [], 'model', 'exec', 0),
        uploader=lambda b: {'revision': b.revision, 'url': 'https://app.test/index.html'})
    return ControlCenterController(runtime, build, author_factory=lambda: None)


def test_authored_tool_requires_verified_admin_context(controller):
    agent = SimpleNamespace(_control_center=controller, current_session={})
    with pytest.raises(PermissionError): update_control_center(agent)
    agent.current_session = {'requester': {'level': 'contact'}}
    with pytest.raises(PermissionError): update_control_center(agent)
    agent.current_session = {'requester': {'level': 'admin'}}
    assert update_control_center(agent)['status'] == 'approved'


def test_public_state_keeps_previous_app_and_omits_source_manifest(controller):
    controller.runtime.update(controller.build_dir)
    state = controller.snapshot()
    assert state['active']
    assert 'manifest' not in state['history'][0]
    assert 'integrity.key' not in str(state)


def test_source_access_is_bounded_and_path_cannot_escape(controller):
    assert controller.source('index.html')['text'] == '<h1>test</h1>'
    with pytest.raises(ValueError): controller.source('../outside')
    (controller.build_dir / 'leak').symlink_to(controller.runtime.state_dir / 'integrity.key')
    with pytest.raises(ValueError): controller.source('leak')


@pytest.mark.asyncio
async def test_control_commands_require_admin_but_state_is_available_to_trusted_caller(controller):
    assert (await controller.command('state', {}, is_admin=False))['status'] == 'empty'
    for action in ('update', 'configure', 'source', 'rollback'):
        with pytest.raises(PermissionError):
            await controller.command(action, {}, is_admin=False)
    assert (await controller.command('configure', {'enabled': False}, is_admin=True))['enabled'] is False


@pytest.mark.asyncio
async def test_manual_command_returns_ack_and_progress_survives_socket_lifetime(controller):
    controller.updates.generator = lambda p: None
    result = await controller.command('update', {}, is_admin=True)
    assert result['status'] == 'accepted'
    assert result['request_id']
    await controller.drain()
    assert controller.snapshot()['active']['review']['status'] == 'approved'


def test_source_history_and_diff_use_retained_approved_manifest(controller):
    captured = {}
    class Uploader:
        def __call__(self, bundle):
            captured[bundle.revision] = bundle
            return {'revision': bundle.revision, 'url': 'https://app.test/index.html'}
        def source(self, app, record):
            return captured[app['revision']].files[record['path']]
    controller.runtime.uploader = Uploader()
    first = controller.runtime.update(controller.build_dir)['active']['revision']
    (controller.build_dir / 'index.html').write_text('<h1>changed</h1>')
    assert controller.source('index.html', first)['text'] == '<h1>test</h1>'
    diff = controller.diff('index.html', first)
    assert '-<h1>test</h1>' in diff['text']
    assert '+<h1>changed</h1>' in diff['text']
    with pytest.raises(ValueError): controller.source('index.html', 'sha256:' + '0' * 64)

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from connectonion.network.host.schedule import create_schedule_lifespan
from connectonion.network.host.ws_router.control_center import handle_control_center, send_control_center


@pytest.mark.asyncio
async def test_existing_tick_runs_control_center_without_an_authored_schedule(tmp_path):
    seen = []
    async def extra(now): seen.append(now)
    start, stop = create_schedule_lifespan(tmp_path, lambda: None, None, 10, extra_tick=extra)
    now = datetime(2026, 9, 7, tzinfo=timezone.utc)
    await start.tick_once(now)
    assert seen == [now]


@pytest.mark.asyncio
async def test_unsigned_or_unauthenticated_control_commands_never_reach_controller():
    class Controller:
        async def command(self, *args, **kwargs): raise AssertionError('must not run')
    frames = []
    async def send(frame): frames.append(frame)
    routes = {'control_center': Controller()}
    for conn in ({}, {'authenticated': True, 'signed_commands': False}):
        await handle_control_center({'request_id': 'r', 'action': 'update'}, send, conn, routes)
        assert frames[-1]['ok'] is False


@pytest.mark.asyncio
async def test_commands_resolve_admin_from_trust_not_payload():
    calls, frames = [], []
    class Controller:
        async def command(self, action, payload, **kwargs):
            calls.append(kwargs['is_admin'])
            return {'status': 'ok'}
    async def send(frame): frames.append(frame)
    routes = {'control_center': Controller(), 'trust_agent': SimpleNamespace(is_admin=lambda who: who == 'owner')}
    conn = {'authenticated': True, 'signed_commands': True, 'agent_address': 'visitor', 'session_id': 's'}
    await handle_control_center({'request_id': 'r', 'action': 'state', 'is_admin': True}, send, conn, routes)
    assert calls == [False]
    assert frames[-1]['request_id'] == 'r'


@pytest.mark.asyncio
async def test_authenticated_descriptor_and_state_are_separate_from_legacy_html():
    frames = []
    async def send(frame): frames.append(frame)
    app = {'revision': 'sha256:test', 'review': {'status': 'approved'}}
    controller = SimpleNamespace(snapshot=lambda: {'active': app, 'status': 'blocked', 'history': []})
    await send_control_center(send, 'session', controller)
    assert frames[0]['type'] == 'CONTROL_CENTER_STATE'
    assert frames[1]['type'] == 'CONTROL_CENTER_APP'
    assert frames[1]['app'] == app


@pytest.mark.asyncio
async def test_signed_control_on_legacy_socket_verifies_and_unwraps_the_inner_command():
    from connectonion import address
    from connectonion.network.connect import RemoteAgent
    keys = address.generate()
    recipient = '0x' + '12' * 20
    agent = RemoteAgent(recipient, keys=keys)
    frame = agent._build_command_message({'type': 'CONTROL_CENTER_COMMAND',
        'request_id': 'review-1', 'action': 'configure', 'payload': {'enabled': True}})
    calls, replies = [], []
    class Controller:
        async def command(self, action, payload, **kwargs):
            calls.append((action, payload, kwargs['is_admin']))
            return {'enabled': payload['enabled']}
    async def send(value): replies.append(value)
    conn = {'authenticated': True, 'signed_commands': False, 'agent_address': keys['address'],
            'recipient_address': recipient}
    routes = {'control_center': Controller(), 'replay': lambda frame: False,
              'trust_agent': SimpleNamespace(is_admin=lambda who: who == keys['address'])}
    # An unsigned top-level action is never authoritative.
    frame['action'] = 'rollback'
    await handle_control_center(frame, send, conn, routes)
    assert calls == [('configure', {'enabled': True}, True)]
    assert replies[-1]['ok'] is True
    frame['payload']['payload']['enabled'] = False
    await handle_control_center(frame, send, conn, routes)
    assert replies[-1]['ok'] is False
    assert len(calls) == 1

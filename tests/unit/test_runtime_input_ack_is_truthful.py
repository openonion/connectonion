"""Runtime-input ACKs promise that the running turn accepted the message."""

import asyncio
from types import SimpleNamespace
from unittest.mock import Mock


def _run_runtime_input(push_result):
    from connectonion.network.host.ws_router import session as ws_session

    sent = []
    frames = [
        {'type': 'CONNECT'},
        {'type': 'INPUT', 'prompt': 'follow up'},
    ]
    io = Mock()
    io.push_runtime_input.return_value = push_result
    active = SimpleNamespace(status='running', io=io)
    registry = Mock()
    registry.get.return_value = active

    async def send_msg(data):
        sent.append(data)

    async def recv_msg():
        return frames.pop(0) if frames else None

    async def connect(data, send_msg, conn, *args, **kwargs):
        conn.update({
            'authenticated': True,
            'agent_address': '0xclient',
            'session_id': 'session-1',
            'session': {},
        })
        return None

    original = ws_session.handle_connect
    ws_session.handle_connect = connect
    try:
        asyncio.run(ws_session.run_ws_session(
            send_msg,
            recv_msg,
            route_handlers={},
            storage=None,
            registry=registry,
            trust=None,
            enable_ping=False,
        ))
    finally:
        ws_session.handle_connect = original

    return sent, io


def test_an_accepted_runtime_input_is_acknowledged():
    sent, io = _run_runtime_input(True)

    io.push_runtime_input.assert_called_once()
    assert [frame['type'] for frame in sent] == ['RUNTIME_INPUT_ACK']


def test_a_sealed_turn_does_not_send_a_false_ack():
    sent, io = _run_runtime_input(False)

    io.push_runtime_input.assert_called_once()
    assert not any(frame['type'] == 'RUNTIME_INPUT_ACK' for frame in sent)
    assert sent == [{
        'type': 'ERROR',
        'code': 'RUNTIME_INPUT_REJECTED',
        'message': 'running turn is not accepting runtime input; retry after OUTPUT',
        'session_id': 'session-1',
        'retryable': True,
    }]


def test_a_failed_agent_turn_is_not_left_running():
    from connectonion.network.host.ws_router.agent_io import _agent_thread_body

    error = RuntimeError('model failed')

    def fail(*args, **kwargs):
        raise error

    io = Mock()
    registry = Mock()
    result_holder = [None]

    _agent_thread_body(
        {'ws_input': fail},
        storage=None,
        prompt='hello',
        io=io,
        session={},
        images=None,
        files=None,
        registry=registry,
        session_id='session-1',
        result_holder=result_holder,
    )

    assert result_holder[0] is error
    registry.mark_session_connected.assert_called_once_with('session-1')
    io.mark_agent_done.assert_called_once_with()

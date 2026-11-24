"""A relay that rejects the announce leaves the agent unreachable (#3125).

The relay answers a refused ANNOUNCE with

    {"type": "ERROR", "error": "Too many endpoints (max 10)", "original_type": "ANNOUNCE"}

and keeps no registration: `/ws/input` says "Agent not connected" and the
directory lists no endpoints. The host printed `Relay error` and kept serving,
the heartbeat resent the same announce every 60 s, and every `co call` failed
while the host looked healthy. The reason belongs in the exit, not in a log.
"""
import json
from unittest.mock import AsyncMock, patch

import pytest
import websockets

from connectonion.network import relay

ANNOUNCE = {"type": "ANNOUNCE", "address": "0xtest", "timestamp": 1}


@pytest.mark.asyncio
async def test_a_rejected_announce_exits_with_the_relays_reason():
    ws = AsyncMock()
    ws.recv.side_effect = [
        json.dumps({"type": "ERROR", "error": "Too many endpoints (max 10)", "original_type": "ANNOUNCE"}),
        websockets.exceptions.ConnectionClosed(None, None),
    ]
    with patch('rich.console.Console.print'), pytest.raises(SystemExit, match='Too many endpoints'):
        await relay.serve_loop(ws, ANNOUNCE, session_handler=AsyncMock())


@pytest.mark.asyncio
async def test_the_exit_passes_the_reconnect_loop_and_closes_the_socket():
    """The supervisor retries every Exception; SystemExit is not one."""
    ws = AsyncMock()
    ws.recv.side_effect = [json.dumps({"type": "ERROR", "error": "Invalid signature", "original_type": "ANNOUNCE"})]
    with patch.object(relay, 'connect', AsyncMock(return_value=ws)), patch('rich.console.Console.print'):
        with pytest.raises(SystemExit, match='Invalid signature'):
            await relay.serve_once('wss://relay.example', lambda: ANNOUNCE, session_handler=AsyncMock())
    ws.close.assert_awaited_once()

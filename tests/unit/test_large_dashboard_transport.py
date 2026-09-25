"""Exercise the real message size and sealed Unicode round-trip, not just a constant."""
import asyncio
import hashlib
import json

import pytest
import websockets
from websockets.asyncio.server import serve

from connectonion import address
from connectonion.network import sealed
from connectonion.network.transport_limits import MAX_WEBSOCKET_MESSAGE_BYTES
from connectonion.network.host.ws_router import dashboard


@pytest.mark.slow
# Sealing and opening 128 MiB is CPU work: about 9s on an idle Mac, 27s with
# three busy processes per core, and the process peaks near 3.6 GB. In a full
# `-n auto` run on a machine already busy with another suite it passed the
# suite's 60s and was killed. The websocket round trip itself is ~2s and keeps
# its own 30s bound below; this bounds the whole test.
@pytest.mark.timeout(180)
@pytest.mark.asyncio
async def test_full_128_mib_dashboard_survives_sealed_websocket(tmp_path, monkeypatch):
    monkeypatch.setattr(dashboard, '_project_dir', tmp_path)
    # Multibyte text catches ASCII-escaping expansion; exact 128 MiB file.
    unit = '<p>房源价格🌍</p>\n'.encode()
    count, rest = divmod(dashboard.MAX_DASHBOARD_BYTES, len(unit))
    raw = unit * count + b' ' * rest
    digest = hashlib.sha256(raw).hexdigest()
    (tmp_path / 'dashboard.html').write_bytes(raw)
    del raw
    frame = dashboard.read_dashboard_snapshot('large', viewer=dashboard.viewer_for(None))
    client_id, host_id = address.generate(), address.generate()
    hello, ephemeral = sealed.client_hello(client_id, host_id['address'])
    reply, sender = sealed.host_accept(hello, host_id)
    receiver = sealed.client_finish(reply, hello, ephemeral)
    wire = json.dumps(sender.seal(frame))
    del frame
    assert len(wire.encode()) < MAX_WEBSOCKET_MESSAGE_BYTES

    async def relay(ws):
        # Echo a complete message, like the content-opaque production relay.
        await ws.send(await ws.recv())

    async with serve(relay, '127.0.0.1', 0, max_size=MAX_WEBSOCKET_MESSAGE_BYTES, compression=None) as server:
        port = server.sockets[0].getsockname()[1]
        async with websockets.connect(f'ws://127.0.0.1:{port}',
                                      max_size=MAX_WEBSOCKET_MESSAGE_BYTES, compression=None) as ws:
            await ws.send(wire)
            del wire
            result = receiver.open(json.loads(await asyncio.wait_for(ws.recv(), 30)))
            assert result['session_id'] == 'large'
            assert hashlib.sha256(result['html'].encode()).hexdigest() == digest

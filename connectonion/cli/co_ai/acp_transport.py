"""Strict ACP v1 newline framing for the ``co ai`` stdio boundary."""

from __future__ import annotations

import asyncio
import platform
import sys
from typing import Any

from acp import stdio_streams
from acp.core import DEFAULT_STDIO_BUFFER_LIMIT_BYTES

from ...core.acp_transport import StrictACPTransport

_StrictNDJSONTransport = StrictACPTransport


class _BoundStdoutWriter:
    """Windows writer bound to original stdout with blocking write-all drain."""

    def __init__(self, output: Any, stream_owner: Any = None) -> None:
        self._output = output
        self._stream_owner = stream_owner
        self._pending = bytearray()
        self._closed = False

    def write(self, data: bytes) -> None:
        if self._closed:
            raise ConnectionError("ACP stdout is closed")
        self._pending.extend(data)

    async def drain(self) -> None:
        payload = bytes(self._pending)
        self._pending.clear()
        await asyncio.to_thread(self._write_all, payload)

    def _write_all(self, payload: bytes) -> None:
        view = memoryview(payload)
        while view:
            written = self._output.write(view)
            if written is None:
                break
            if written <= 0:
                raise BrokenPipeError("ACP stdout stopped accepting bytes")
            view = view[written:]
        self._output.flush()

    def close(self) -> None:
        self._closed = True

    async def wait_closed(self) -> None:
        pass


async def open_stdio_transport() -> _StrictNDJSONTransport:
    """Open stdio while permanently binding ACP writes to original stdout."""

    protocol_output = sys.stdout.buffer
    reader, sdk_writer = await stdio_streams(
        limit=DEFAULT_STDIO_BUFFER_LIMIT_BYTES
    )
    # The SDK writer owns the platform-specific stdout pipe. Keep it alive even
    # though protocol writes use the captured handle above.
    writer = (
        _BoundStdoutWriter(protocol_output, stream_owner=sdk_writer)
        if platform.system() == "Windows"
        else sdk_writer
    )
    return _StrictNDJSONTransport(reader, writer)

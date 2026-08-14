"""Strict newline-delimited ACP transport shared by both process roles."""

from __future__ import annotations

import asyncio
import json
from contextlib import suppress
from typing import Any

from acp import RequestError
from acp.core import DEFAULT_STDIO_BUFFER_LIMIT_BYTES

from .acp_jsonrpc import (
    ACP_META_SHADOW_ERROR_DETAILS,
    ACP_PROTOCOL_VERSION_ERROR_DETAILS,
    ACP_WIRE_PARAM_ERROR_DETAILS,
    acp_initialize_protocol_version_is_valid,
    acp_meta_shadows_request_params,
    acp_params_use_protocol_field_names,
    acp_request_id,
    is_acp_json_rpc_message,
    is_acp_json_rpc_response_candidate,
    is_acp_request_id,
)


class StrictACPTransport:
    """Validate framing and routing invariants before the pinned SDK router."""

    def __init__(
        self,
        reader: asyncio.StreamReader,
        writer: Any,
        *,
        max_frame_bytes: int = DEFAULT_STDIO_BUFFER_LIMIT_BYTES,
    ) -> None:
        self._reader = reader
        self._writer = writer
        self._max_frame_bytes = max_frame_bytes
        self._write_lock = asyncio.Lock()
        self._closed = False

    async def receive(self) -> dict[str, Any] | None:
        while True:
            try:
                line = await self._read_line()
            except _FrameTooLarge:
                await self._send_error(
                    None,
                    RequestError.parse_error(
                        {
                            "details": (
                                "ACP frame exceeds the configured "
                                f"{self._max_frame_bytes}-byte limit"
                            )
                        }
                    ),
                )
                return None
            if not line:
                return None
            if not line.strip():
                continue
            try:
                message = json.loads(line, parse_constant=_reject_json_constant)
            except (UnicodeDecodeError, ValueError, json.JSONDecodeError):
                await self._send_error(None, RequestError.parse_error())
                continue
            if not self._is_json_rpc_message(message):
                if is_acp_json_rpc_response_candidate(message):
                    return None
                request_id = self._request_id(message)
                await self._send_error(request_id, RequestError.invalid_request())
                continue
            if acp_meta_shadows_request_params(message):
                if "id" in message:
                    await self._send_error(
                        self._request_id(message),
                        RequestError.invalid_params(
                            {"details": ACP_META_SHADOW_ERROR_DETAILS}
                        ),
                    )
                continue
            if not acp_params_use_protocol_field_names(message):
                if "id" in message:
                    await self._send_error(
                        self._request_id(message),
                        RequestError.invalid_params(
                            {"details": ACP_WIRE_PARAM_ERROR_DETAILS}
                        ),
                    )
                continue
            if not acp_initialize_protocol_version_is_valid(message):
                if "id" in message:
                    await self._send_error(
                        self._request_id(message),
                        RequestError.invalid_params(
                            {"details": ACP_PROTOCOL_VERSION_ERROR_DETAILS}
                        ),
                    )
                continue
            return message

    async def send(self, message: dict[str, Any]) -> None:
        if self._closed:
            raise ConnectionError("ACP stdio transport is closed")
        payload = json.dumps(
            message,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
        ).encode("utf-8") + b"\n"
        async with self._write_lock:
            self._writer.write(payload)
            await self._writer.drain()

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._writer.close()
        with suppress(Exception):
            await self._writer.wait_closed()

    async def _send_error(self, request_id: Any, error: RequestError) -> None:
        await self.send(
            {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": error.to_error_obj(),
            }
        )

    async def _read_line(self) -> bytes:
        """Read one frame even when it exceeds StreamReader's chunk limit."""

        chunks: list[bytes] = []
        total_bytes = 0
        try:
            while True:
                try:
                    line = await self._reader.readuntil(b"\n")
                except asyncio.LimitOverrunError as exc:
                    if total_bytes + exc.consumed > self._max_frame_bytes:
                        raise _FrameTooLarge from None
                    chunk = await self._reader.readexactly(exc.consumed)
                    chunks.append(chunk)
                    total_bytes += len(chunk)
                else:
                    if total_bytes + len(line) > self._max_frame_bytes:
                        raise _FrameTooLarge
                    chunks.append(line)
                    return b"".join(chunks)
        except asyncio.IncompleteReadError as exc:
            if total_bytes + len(exc.partial) > self._max_frame_bytes:
                raise _FrameTooLarge from None
            chunks.append(exc.partial)
            return b"".join(chunks)

    @classmethod
    def _request_id(cls, message: Any) -> str | int | None:
        return acp_request_id(message)

    @staticmethod
    def _is_request_id(value: Any) -> bool:
        return is_acp_request_id(value)

    @classmethod
    def _is_json_rpc_message(cls, message: Any) -> bool:
        return is_acp_json_rpc_message(message)


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"invalid JSON constant: {value}")


class _FrameTooLarge(Exception):
    pass

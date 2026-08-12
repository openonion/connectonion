"""Bounded, session-scoped stdio MCP tools for the ACP adapter.

The ACP request supplies process launch data.  This module validates all of it
before spawning anything, owns every SDK context in one long-lived task, and
exports MCP tools through ConnectOnion's ordinary approval pipeline.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import hashlib
import json
import os
import re
import time
from contextlib import AsyncExitStack, suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from acp.schema import McpServerStdio

from ...core.interrupt import UserInterrupt

MAX_MCP_SERVERS = 8
MAX_MCP_TOOLS = 128
MAX_MCP_TOOL_PAGES = 32
MAX_MCP_SCHEMA_BYTES = 64 * 1024
MAX_MCP_ARGUMENT_BYTES = 64 * 1024
MAX_MCP_RESULT_BYTES = 64 * 1024
# MCP 2.x has a comparatively heavy cold import path on Python 3.10. Keep
# startup bounded, but leave enough headroom for the child process to import
# the SDK and answer its initialize request on a cold or resource-limited host.
MCP_CONNECT_TIMEOUT_SECONDS = 30.0
MCP_CALL_TIMEOUT_SECONDS = 60.0
_MCP_TOOL_NAME_LIMIT = 64
_MCP_NAME_LIMIT = 128
_MCP_ARGS_LIMIT = 128
_MCP_ARG_BYTES_LIMIT = 8 * 1024
_MCP_ENV_LIMIT = 128
_MCP_ENV_VALUE_BYTES_LIMIT = 32 * 1024
_TOOL_POLL_SECONDS = 0.05
_PORTABLE_ENV_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z")
_TOOL_SLUG = re.compile(r"[^a-z0-9]+")


class MCPConfigError(ValueError):
    """The client supplied unsafe or unsupported MCP launch data."""


class MCPToolError(RuntimeError):
    """A bounded MCP call could not produce a usable tool result."""


def validate_stdio_servers(servers: list[Any]) -> list[McpServerStdio]:
    """Validate the complete launch set before any process can be spawned."""

    if len(servers) > MAX_MCP_SERVERS:
        raise MCPConfigError(
            f"At most {MAX_MCP_SERVERS} stdio MCP servers are allowed per session"
        )
    validated: list[McpServerStdio] = []
    names: set[str] = set()
    for server in servers:
        if not isinstance(server, McpServerStdio):
            raise MCPConfigError("Only ACP stdio MCP servers are supported")
        if not server.name or len(server.name) > _MCP_NAME_LIMIT:
            raise MCPConfigError("MCP server names must be 1 to 128 characters")
        if server.name in names:
            raise MCPConfigError("MCP server names must be unique within a session")
        names.add(server.name)
        if not os.path.isabs(server.command):
            raise MCPConfigError("MCP server commands must be absolute paths")
        _reject_nul(server.command, "MCP server command")
        if len(server.args) > _MCP_ARGS_LIMIT:
            raise MCPConfigError(f"MCP server args are limited to {_MCP_ARGS_LIMIT}")
        for argument in server.args:
            _reject_nul(argument, "MCP server argument")
            if len(argument.encode("utf-8")) > _MCP_ARG_BYTES_LIMIT:
                raise MCPConfigError("An MCP server argument exceeds the size limit")
        if len(server.env) > _MCP_ENV_LIMIT:
            raise MCPConfigError(f"MCP server env is limited to {_MCP_ENV_LIMIT} entries")
        env_names: set[str] = set()
        for variable in server.env:
            if not _PORTABLE_ENV_NAME.fullmatch(variable.name):
                raise MCPConfigError(f"Invalid MCP environment name: {variable.name!r}")
            if variable.name in env_names:
                raise MCPConfigError("MCP environment names must be unique per server")
            env_names.add(variable.name)
            _reject_nul(variable.value, "MCP environment value")
            if len(variable.value.encode("utf-8")) > _MCP_ENV_VALUE_BYTES_LIMIT:
                raise MCPConfigError("An MCP environment value exceeds the size limit")
        validated.append(server)
    return validated


def _reject_nul(value: str, label: str) -> None:
    if "\0" in value:
        raise MCPConfigError(f"{label} cannot contain NUL bytes")


def _name_segment(value: str) -> str:
    slug = _TOOL_SLUG.sub("_", value.casefold()).strip("_") or "tool"
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:8]
    return f"{slug[:19]}_{digest}"


def mcp_tool_name(server_name: str, remote_name: str) -> str:
    """Return one stable LLM-safe name that cannot collide across servers."""

    name = f"mcp__{_name_segment(server_name)}__{_name_segment(remote_name)}"
    if len(name) > _MCP_TOOL_NAME_LIMIT:  # defensive if segment sizes change
        raise MCPConfigError("Generated MCP tool name exceeds the protocol limit")
    return name


class MCPTool:
    """Synchronous Agent tool backed by an MCP call on the ACP owner loop."""

    _needs_agent = True

    def __init__(
        self,
        *,
        client: Any,
        server_name: str,
        remote_name: str,
        description: str | None,
        input_schema: dict[str, Any],
        loop: asyncio.AbstractEventLoop,
    ) -> None:
        self.name = mcp_tool_name(server_name, remote_name)
        self.description = (
            f"MCP stdio server {server_name!r}: "
            f"{description or f'Run the {remote_name} tool.'}"
        )[:1024]
        self._client = client
        self._remote_name = remote_name
        self._input_schema = input_schema
        self._loop = loop
        self.run = self

    def get_parameters_schema(self) -> dict[str, Any]:
        return self._input_schema

    def to_function_schema(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self._input_schema,
        }

    def __call__(self, *, agent: Any, **arguments: Any) -> dict[str, Any]:
        io = getattr(agent, "io", None)
        if io is not None and getattr(io, "is_cancelled", lambda: False)():
            raise UserInterrupt()
        try:
            encoded_arguments = json.dumps(
                arguments,
                ensure_ascii=False,
                allow_nan=False,
                separators=(",", ":"),
            ).encode("utf-8")
        except (TypeError, ValueError, OverflowError, RecursionError):
            raise MCPToolError("MCP tool arguments are not valid JSON") from None
        if len(encoded_arguments) > MAX_MCP_ARGUMENT_BYTES:
            raise MCPToolError("MCP tool argument limit exceeded")
        future = asyncio.run_coroutine_threadsafe(
            self._call(arguments),
            self._loop,
        )
        deadline = time.monotonic() + MCP_CALL_TIMEOUT_SECONDS
        while True:
            if io is not None and getattr(io, "is_cancelled", lambda: False)():
                future.cancel()
                raise UserInterrupt()
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                future.cancel()
                raise MCPToolError("MCP tool call exceeded the timeout")
            try:
                result = future.result(timeout=min(_TOOL_POLL_SECONDS, remaining))
                break
            except concurrent.futures.TimeoutError:
                if not future.done():
                    continue
                try:
                    result = future.result()
                    break
                except concurrent.futures.CancelledError:
                    raise UserInterrupt() from None
                except Exception:
                    raise MCPToolError("MCP tool call failed") from None
            except concurrent.futures.CancelledError:
                raise UserInterrupt() from None
            except Exception:
                # Remote exception messages are untrusted and may be huge or
                # contain server-side secrets. Keep the Agent trace bounded.
                raise MCPToolError("MCP tool call failed") from None

        if hasattr(result, "model_dump"):
            payload = result.model_dump(mode="json", by_alias=True, exclude_none=True)
        elif isinstance(result, dict):
            payload = result
        else:
            raise MCPToolError("MCP tool returned an unsupported result")
        try:
            serialized = json.dumps(
                payload,
                ensure_ascii=False,
                allow_nan=False,
                separators=(",", ":"),
            )
        except (TypeError, ValueError, OverflowError, RecursionError):
            raise MCPToolError("MCP tool returned invalid JSON") from None
        if len(serialized.encode("utf-8")) > MAX_MCP_RESULT_BYTES:
            raise MCPToolError("MCP tool result limit exceeded")
        if getattr(result, "is_error", False):
            raise MCPToolError(f"MCP tool reported an error: {serialized}")
        return json.loads(serialized)

    async def _call(self, arguments: dict[str, Any]) -> Any:
        return await self._client.call_tool(
            self._remote_name,
            arguments,
            read_timeout_seconds=MCP_CALL_TIMEOUT_SECONDS,
        )


@dataclass
class _Call:
    client_index: int
    name: str
    arguments: dict[str, Any]
    response: asyncio.Future[Any]
    task: asyncio.Task[Any] | None = None
    cancelled: bool = False


class _ClientProxy:
    def __init__(self, pool: "MCPPool", client_index: int) -> None:
        self._pool = pool
        self._client_index = client_index

    async def call_tool(
        self,
        name: str,
        arguments: dict[str, Any],
        **_kwargs: Any,
    ) -> Any:
        return await self._pool.call_tool(self._client_index, name, arguments)


class MCPPool:
    """Own all MCP SDK contexts in one task from startup through shutdown."""

    def __init__(
        self,
        servers: list[McpServerStdio],
        cwd: Path,
        loop: asyncio.AbstractEventLoop,
    ) -> None:
        self.tools: list[MCPTool] = []
        self._servers = servers
        self._cwd = cwd
        self._loop = loop
        self._queue: asyncio.Queue[_Call | None] = asyncio.Queue()
        self._ready: asyncio.Future[None] = loop.create_future()
        self._task = loop.create_task(self._run())
        self._closed = False

    async def wait_ready(self) -> None:
        try:
            await asyncio.shield(self._ready)
        except BaseException:
            await self.close()
            raise

    async def call_tool(
        self,
        client_index: int,
        name: str,
        arguments: dict[str, Any],
    ) -> Any:
        if self._closed or self._task.done():
            raise MCPToolError("MCP server session is closed")
        response = self._loop.create_future()
        request = _Call(client_index, name, arguments, response)
        await self._queue.put(request)
        try:
            return await response
        except asyncio.CancelledError:
            request.cancelled = True
            if request.task is not None:
                request.task.cancel()
            raise

    async def close(self) -> None:
        if not self._closed:
            self._closed = True
            await self._queue.put(None)
        while not self._task.done():
            try:
                await asyncio.shield(self._task)
            except asyncio.CancelledError:
                continue
            except BaseException:
                break
        with suppress(BaseException):
            self._task.result()

    async def _run(self) -> None:
        clients: list[Any] = []
        try:
            from mcp import Client, StdioServerParameters, stdio_client

            async with AsyncExitStack() as stack:
                discovered: list[MCPTool] = []
                names: set[str] = set()
                for index, server in enumerate(self._servers):
                    parameters = StdioServerParameters(
                        command=server.command,
                        args=list(server.args),
                        env={variable.name: variable.value for variable in server.env},
                        cwd=self._cwd,
                    )
                    client = await stack.enter_async_context(
                        Client(
                            stdio_client(parameters),
                            mode="legacy",
                            read_timeout_seconds=MCP_CONNECT_TIMEOUT_SECONDS,
                        )
                    )
                    clients.append(client)
                    discovered.extend(
                        await self._discover_tools(client, index, server.name, names)
                    )
                self.tools = discovered
                if not self._ready.done():
                    self._ready.set_result(None)
                await self._serve_calls(clients)
        except asyncio.CancelledError as exc:
            if not self._ready.done():
                self._ready.set_exception(exc)
            self._fail_queued(exc)
            raise
        except Exception as exc:
            if not self._ready.done():
                self._ready.set_exception(exc)
            self._fail_queued(exc)
        finally:
            self._fail_queued(MCPToolError("MCP server session is closed"))

    async def _discover_tools(
        self,
        client: Any,
        client_index: int,
        server_name: str,
        names: set[str],
    ) -> list[MCPTool]:
        tools: list[MCPTool] = []
        cursor: str | None = None
        for _page in range(MAX_MCP_TOOL_PAGES):
            result = await client.list_tools(cursor=cursor)
            for remote in result.tools:
                if len(names) >= MAX_MCP_TOOLS:
                    raise MCPConfigError(
                        f"MCP sessions are limited to {MAX_MCP_TOOLS} tools"
                    )
                schema = remote.input_schema
                if not isinstance(schema, dict) or schema.get("type") != "object":
                    raise MCPConfigError("MCP tool inputSchema must be an object")
                encoded = json.dumps(schema, separators=(",", ":")).encode("utf-8")
                if len(encoded) > MAX_MCP_SCHEMA_BYTES:
                    raise MCPConfigError("MCP tool inputSchema exceeds the size limit")
                name = mcp_tool_name(server_name, remote.name)
                if name in names:
                    raise MCPConfigError("MCP tool names must be unique after mapping")
                names.add(name)
                tools.append(
                    MCPTool(
                        client=_ClientProxy(self, client_index),
                        server_name=server_name,
                        remote_name=remote.name,
                        description=remote.description,
                        input_schema=schema,
                        loop=self._loop,
                    )
                )
            cursor = result.next_cursor
            if cursor is None:
                return tools
        raise MCPConfigError("MCP tools/list exceeded the pagination limit")

    async def _serve_calls(self, clients: list[Any]) -> None:
        while True:
            request = await self._queue.get()
            if request is None:
                return
            if request.cancelled or request.response.cancelled():
                continue
            request.task = self._loop.create_task(
                clients[request.client_index].call_tool(
                    request.name,
                    request.arguments,
                    read_timeout_seconds=MCP_CALL_TIMEOUT_SECONDS,
                )
            )
            try:
                result = await request.task
            except asyncio.CancelledError:
                if not request.response.done():
                    request.response.cancel()
                continue
            except Exception as exc:
                if not request.response.done():
                    request.response.set_exception(exc)
            else:
                if not request.response.done():
                    request.response.set_result(result)

    def _fail_queued(self, error: BaseException) -> None:
        while True:
            try:
                request = self._queue.get_nowait()
            except asyncio.QueueEmpty:
                return
            if request is not None and not request.response.done():
                request.response.set_exception(error)


async def connect_mcp_servers(
    servers: list[Any],
    *,
    cwd: Path,
    loop: asyncio.AbstractEventLoop,
) -> MCPPool:
    """Start one validated session pool and wait for complete tool discovery."""

    validated = validate_stdio_servers(servers)
    pool = MCPPool(validated, cwd, loop)
    await pool.wait_ready()
    return pool

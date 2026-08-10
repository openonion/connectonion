"""Publisher-defined HTTP resources with audience-scoped route groups.

The group is the security boundary.  Its prefix is deliberately visible in the
URL, but authorization reads the route's immutable audience metadata rather
than trying to recover policy from a request string.
"""

from __future__ import annotations

import inspect
import json
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping
from urllib.parse import parse_qs

from ..asgi.http import CORS_HEADERS, pydantic_json_encoder, read_body

AUDIENCE_PREFIXES = {
    "public": "/public",
    "contacts": "/contacts",
    "admin": "/admin",
}

# Exact legacy paths remain contracts until their canonical replacements can
# live under /_co.  A publisher route must not depend on registration order to
# steal one of them.
_RESERVED_PATHS = {
    "/input", "/sessions", "/health", "/info", "/docs", "/ws",
    "/admin/logs", "/admin/sessions",
}
_RESERVED_PREFIXES = ("/_co", "/admin/trust", "/superadmin")
_PARAMETER = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")


def _validate_relative_path(path: str) -> list[str]:
    if not isinstance(path, str) or not path.startswith("/"):
        raise ValueError("HTTP route path must start with '/'")
    if path.startswith("//") or "//" in path or "?" in path or "#" in path:
        raise ValueError("HTTP route path must be a clean path without query or fragment")
    segments = path.split("/")[1:]
    if any(segment in ("", ".", "..") for segment in segments):
        raise ValueError("HTTP route path cannot contain empty, '.' or '..' segments")

    names = []
    for segment in segments:
        if "{" in segment or "}" in segment:
            matches = list(_PARAMETER.finditer(segment))
            remainder = _PARAMETER.sub("", segment)
            if not matches or "{" in remainder or "}" in remainder:
                raise ValueError(f"invalid HTTP path parameter segment: {segment!r}")
            for match in matches:
                name = match.group(1)
                if name in names:
                    raise ValueError(f"duplicate HTTP path parameter: {name}")
                names.append(name)
    return names


def _reserved(path: str) -> bool:
    if path in _RESERVED_PATHS:
        return True
    return any(path == prefix or path.startswith(prefix + "/")
               for prefix in _RESERVED_PREFIXES)


def _pattern(path: str):
    names = []
    pieces = []
    static_segments = 0
    for segment in path.split("/")[1:]:
        matches = list(_PARAMETER.finditer(segment))
        if not matches:
            static_segments += 1
            pieces.append(re.escape(segment))
            continue
        cursor = 0
        segment_pattern = []
        for match in matches:
            segment_pattern.append(re.escape(segment[cursor:match.start()]))
            segment_pattern.append(r"([^/]+)")
            names.append(match.group(1))
            cursor = match.end()
        segment_pattern.append(re.escape(segment[cursor:]))
        pieces.append("".join(segment_pattern))
    return re.compile("^/" + "/".join(pieces) + "$"), names, static_segments


def _shape(path: str) -> str:
    return _PARAMETER.sub("{}", path)


@dataclass(frozen=True)
class HTTPRequest:
    """The request a publisher handler receives when it declares `request`."""

    method: str
    path: str
    headers: Mapping[str, str]
    query: Mapping[str, list[str]]
    path_params: Mapping[str, str]
    body: bytes = b""
    identity: str | None = None

    @property
    def text(self) -> str:
        return self.body.decode("utf-8")

    def json(self) -> Any:
        return json.loads(self.body)


@dataclass(frozen=True)
class HTTPResponse:
    """Explicit status, headers, media type, and body for an HTTP resource."""

    body: str | bytes = b""
    status: int = 200
    media_type: str = "text/plain; charset=utf-8"
    headers: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self):
        if not 100 <= self.status <= 599:
            raise ValueError("HTTP response status must be between 100 and 599")
        if not isinstance(self.body, (str, bytes)):
            raise TypeError("HTTP response body must be str or bytes")
        if not isinstance(self.media_type, str) or any(
            char in self.media_type for char in "\r\n"
        ):
            raise ValueError("HTTP response media type must be a string without newlines")
        if not isinstance(self.headers, Mapping):
            raise TypeError("HTTP response headers must be a mapping")
        for name, value in self.headers.items():
            if any(char in str(name) + str(value) for char in "\r\n"):
                raise ValueError("HTTP response header names and values cannot contain newlines")


@dataclass(frozen=True)
class HTTPRoute:
    method: str
    relative_path: str
    path: str
    audience: str
    handler: Callable
    pattern: Any = field(repr=False)
    parameter_names: tuple[str, ...] = ()
    static_segments: int = 0

    async def invoke(self, request: HTTPRequest, params: dict[str, str]):
        signature = inspect.signature(self.handler)
        kwargs = {name: params[name] for name in self.parameter_names}
        if "request" in signature.parameters:
            kwargs["request"] = request
        result = self.handler(**kwargs)
        return await result if inspect.isawaitable(result) else result


class _AudienceGroup:
    def __init__(self, router: "HTTPRouter", audience: str):
        self._router = router
        self._audience = audience

    def get(self, path: str):
        return self._router._decorator("GET", self._audience, path)

    def post(self, path: str):
        return self._router._decorator("POST", self._audience, path)


class HTTPRouter:
    """Routes grouped by who may call them: public, contacts, or admin."""

    def __init__(self):
        self._routes: list[HTTPRoute] = []
        self.public = _AudienceGroup(self, "public")
        self.contacts = _AudienceGroup(self, "contacts")
        self.admin = _AudienceGroup(self, "admin")

    @property
    def routes(self) -> tuple[HTTPRoute, ...]:
        return tuple(self._routes)

    def _decorator(self, method: str, audience: str, relative_path: str):
        parameter_names = _validate_relative_path(relative_path)
        full_path = AUDIENCE_PREFIXES[audience] + relative_path
        if _reserved(full_path):
            raise ValueError(f"HTTP path {full_path!r} is reserved by Connectonion")

        def register(handler: Callable):
            shape = _shape(full_path)
            for existing in self._routes:
                if existing.method == method and _shape(existing.path) == shape:
                    raise ValueError(
                        f"duplicate HTTP route {method} {full_path}: "
                        f"already registered by {existing.handler.__name__}"
                    )

            signature = inspect.signature(handler)
            accepts_kwargs = any(
                value.kind is inspect.Parameter.VAR_KEYWORD
                for value in signature.parameters.values()
            )
            missing_path_parameters = [
                name for name in parameter_names
                if name not in signature.parameters and not accepts_kwargs
            ]
            if missing_path_parameters:
                raise ValueError(
                    f"HTTP handler {handler.__name__} does not accept path parameters: "
                    f"{', '.join(missing_path_parameters)}"
                )
            positional_only = [
                name for name, value in signature.parameters.items()
                if value.kind is inspect.Parameter.POSITIONAL_ONLY
                and name in set(parameter_names) | {"request"}
            ]
            if positional_only:
                raise ValueError(
                    f"HTTP handler parameters must accept keyword values: "
                    f"{', '.join(positional_only)}"
                )
            unsupported = [
                name for name, value in signature.parameters.items()
                if value.default is inspect.Parameter.empty
                and value.kind in (value.POSITIONAL_ONLY, value.POSITIONAL_OR_KEYWORD,
                                   value.KEYWORD_ONLY)
                and name not in set(parameter_names) | {"request"}
            ]
            if unsupported:
                raise ValueError(
                    f"HTTP handler {handler.__name__} has parameters not supplied by "
                    f"its route: {', '.join(unsupported)}"
                )

            pattern, names, static_segments = _pattern(full_path)
            self._routes.append(HTTPRoute(
                method, relative_path, full_path, audience, handler, pattern,
                tuple(names), static_segments,
            ))
            return handler

        return register

    def match(self, method: str, path: str):
        candidates = sorted(
            (route for route in self._routes if route.method == method.upper()),
            key=lambda route: route.static_segments,
            reverse=True,
        )
        for route in candidates:
            match = route.pattern.fullmatch(path)
            if match:
                return route, dict(zip(route.parameter_names, match.groups()))
        return None


def _scope_headers(scope) -> dict[str, str]:
    return {key.decode().lower(): value.decode()
            for key, value in scope.get("headers", [])}


def _request_query(scope) -> dict[str, list[str]]:
    return parse_qs(
        (scope.get("query_string") or b"").decode(),
        keep_blank_values=True,
    )


async def _send(send, result):
    if isinstance(result, HTTPResponse):
        body = result.body.encode() if isinstance(result.body, str) else result.body
        headers = {
            "content-type": result.media_type,
            **{str(key).lower(): str(value) for key, value in result.headers.items()},
        }
        raw_headers = [[key.encode(), value.encode()] for key, value in headers.items()]
        cors_names = {key for key, _ in raw_headers}
        raw_headers += [header for header in CORS_HEADERS if header[0] not in cors_names]
        await send({"type": "http.response.start", "status": result.status,
                    "headers": raw_headers})
        await send({"type": "http.response.body", "body": body})
        return

    if result is None:
        await send({"type": "http.response.start", "status": 204,
                    "headers": CORS_HEADERS})
        await send({"type": "http.response.body", "body": b""})
        return

    if isinstance(result, (dict, list)):
        body = json.dumps(result, default=pydantic_json_encoder).encode()
        media_type = b"application/json"
    elif isinstance(result, bytes):
        body, media_type = result, b"application/octet-stream"
    elif isinstance(result, str):
        body, media_type = result.encode(), b"text/plain; charset=utf-8"
    else:
        raise TypeError(
            "HTTP handlers must return dict, list, str, bytes, None, or HTTPResponse"
        )

    await send({"type": "http.response.start", "status": 200,
                "headers": [[b"content-type", media_type]] + CORS_HEADERS})
    await send({"type": "http.response.body", "body": body})


async def dispatch_http_route(
    route: HTTPRoute,
    path_params: dict[str, str],
    scope,
    receive,
    send,
    *,
    trust_agent,
    recipient_address: str,
    blacklist=None,
    whitelist=None,
    replay_check=None,
):
    """Authenticate, invoke, and serialize one already-matched route."""
    body = await read_body(receive)
    headers = _scope_headers(scope)
    identity = None

    if route.audience != "public":
        from .auth import (
            _authenticate_signed,
            request_from_http_headers,
            signature_already_used,
        )
        from .replay import ReplayProtectionError

        try:
            data = request_from_http_headers(
                headers,
                scope["method"],
                scope["path"],
                query=scope.get("query_string") or b"",
                body=body,
            )
        except (TypeError, ValueError, UnicodeDecodeError):
            await _send(send, HTTPResponse(
                json.dumps({"error": "unauthorized: malformed signature headers"}),
                status=401, media_type="application/json",
            ))
            return
        if not data["payload"].get("request_id"):
            await _send(send, HTTPResponse(
                json.dumps({"error": "unauthorized: request id required"}),
                status=401, media_type="application/json",
            ))
            return
        _, identity, error = _authenticate_signed(
            data, blacklist=blacklist, recipient_address=recipient_address,
        )
        if error:
            await _send(send, HTTPResponse(
                json.dumps({"error": error}),
                status=403 if error.startswith("forbidden") else 401,
                media_type="application/json",
            ))
            return
        check_replay = replay_check or signature_already_used
        try:
            already_used = check_replay(data)
        except ReplayProtectionError:
            await _send(send, HTTPResponse(
                json.dumps({"error": "misconfigured: replay protection unavailable"}),
                status=503, media_type="application/json",
            ))
            return
        if already_used:
            await _send(send, HTTPResponse(
                json.dumps({"error": "unauthorized: signature already used"}),
                status=401, media_type="application/json",
            ))
            return

        is_admin = trust_agent.is_admin(identity)
        level = None if is_admin else trust_agent.get_level(identity)
        if route.audience == "contacts":
            allowed = is_admin or (
                level != "blocked" and (
                    identity in (whitelist or [])
                    or level in ("contact", "whitelist")
                )
            )
        else:
            allowed = is_admin
        if not allowed:
            await _send(send, HTTPResponse(
                json.dumps({"error": f"forbidden: {route.audience} only"}),
                status=403, media_type="application/json",
            ))
            return

    request = HTTPRequest(
        method=scope["method"],
        path=scope["path"],
        headers=headers,
        query=_request_query(scope),
        path_params=path_params,
        body=body,
        identity=identity,
    )
    try:
        result = await route.invoke(request, path_params)
        await _send(send, result)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        await _send(send, HTTPResponse(
            json.dumps({"error": f"invalid request body: {exc}"}),
            status=400, media_type="application/json",
        ))


__all__ = ["HTTPRequest", "HTTPResponse", "HTTPRoute", "HTTPRouter"]

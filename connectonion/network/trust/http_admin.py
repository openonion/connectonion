"""HTTP admin and superadmin route handling.

Purpose: Authenticate and dispatch /admin/* and /superadmin/* HTTP requests for the hosted agent's trust controls (promote/demote/block/unblock, level lookup, super-admin add/remove, and legacy admin logs/sessions).
LLM-Note:
  Dependencies: imports from [hmac, json, os, network/host/auth.py] | imported by [network/host/http_router.py (handle_admin_routes called for paths starting with /admin or /superadmin)] | tested by [tests/unit/test_admin_signatures_are_route_bound.py, tests/unit/test_an_admin_signature_is_used_once.py, tests/unit/test_reading_logs_does_not_need_the_billing_key.py]
  Data flow: receives ASGI scope/receive + parsed method/path from http_router → /admin/logs and /admin/sessions accept EITHER a distinct per-deployment CONNECTONION_ADMIN_TOKEN bearer or a signed admin request; /admin/trust/* and /superadmin/* require a signature over payload + actual method/path. GETs use the shared X-Co-From/X-Co-Signature/X-Co-Timestamp scheme; legacy X-From headers remain read-only for 1.6 compatibility → calls into route_handlers callbacks (admin_logs, admin_sessions, admin_trust_promote/demote/block/unblock/level, admin_admins_add/remove) → responds via send_json/send_text
  State/Effects: invokes route_handlers (which mutate trust agent state, file logs, sessions) | reads CONNECTONION_ADMIN_TOKEN and OPENONION_API_KEY only to prevent credential reuse | logs nothing directly
  Integration: exposes async handle_admin_routes(method, path, scope, receive, route_handlers, *, send_json, send_text, read_body) -> bool (always True after this function — it owns the response for /admin/* and /superadmin/*) | route_handlers dict must include "trust_agent", "auth", and the admin_* callbacks
  Errors: returns 401 unauthorized on bad/unbound bearer/signature or a route_handlers with no verifier wired, 403 forbidden when not admin/superadmin, 400 on missing client_id/admin_id or invalid signature timestamp/JSON, 404 catch-all for unknown admin paths — never raises
  Security: bearer comparison uses hmac.compare_digest to avoid timing leaks | the admin token fails closed when absent or equal to the model billing key | signature verification delegated to route_handlers["auth"] (#670)
"""

import hmac
import json
import os


async def _admin_signature(method, path, scope, receive, route_handlers, *, read_body,
                           require_super=False):
    """Verify a signed admin request. -> (ok, status, error, data).

    `data` comes back because the body can only be read once: the caller needs
    the payload it carries (client_id, reason) and cannot go get it again.

    One implementation for both route families. /admin/trust/* and
    /superadmin/* have always used this; /admin/logs and /admin/sessions now
    accept it too, so reading an agent's activity no longer requires the key
    that spends its money (#670). A second copy of a signature check is the
    thing most likely to drift out of step with the one that guards more.

    GETs carry the shared X-Co-* headers because proxies strip GET bodies.
    Legacy X-* headers remain accepted only for the two read-only activity
    routes. A legacy signature can therefore still read what it was designed
    to read, but cannot be redirected to a trust mutation.
    """
    headers = {
        key.decode().lower(): value.decode()
        for key, value in scope.get("headers", [])
    }
    from ..host.auth import (
        FROM_HEADER,
        SIGNATURE_HEADER,
        TIMESTAMP_HEADER,
        request_from_headers,
    )

    bound_header_present = any(
        headers.get(name)
        for name in (FROM_HEADER, SIGNATURE_HEADER, TIMESTAMP_HEADER)
    )
    legacy_from = headers.get("x-from")
    legacy_sig = headers.get("x-signature")
    legacy_ts = headers.get("x-timestamp")

    if method == "GET" and bound_header_present:
        try:
            data = request_from_headers(headers, method, path)
        except (TypeError, ValueError):
            return False, 400, "Invalid X-Co-Timestamp header", {}
    elif (method == "GET" and legacy_from and legacy_sig and legacy_ts
          and path in ("/admin/logs", "/admin/sessions")):
        try:
            data = {"payload": {"timestamp": float(legacy_ts)},
                    "from": legacy_from, "signature": legacy_sig}
        except ValueError:
            return False, 400, "Invalid X-Timestamp header", {}
    else:
        body = await read_body(receive)
        try:
            data = json.loads(body) if body else {}
        except json.JSONDecodeError:
            return False, 400, "Invalid JSON", {}

    payload = data.get("payload", {})
    is_bound = (
        payload.get("method") == method.upper()
        and payload.get("path") == path
    )
    legacy_read_only = (
        method == "GET"
        and path in ("/admin/logs", "/admin/sessions")
        and "method" not in payload
        and "path" not in payload
    )
    if not is_bound and not legacy_read_only:
        return False, 401, "unauthorized: route-bound method and path required", data

    # A caller that wires no signature verifier has no signed path — say so
    # rather than raising KeyError. The legacy routes reach here now, and they
    # were previously satisfied by a Bearer token alone, so route_handlers
    # assembled for them need not carry "auth" (two tests build exactly that).
    verify = route_handlers.get("auth")
    if verify is None:
        return False, 401, "unauthorized", data

    _, agent_address, sig_valid, err = verify(data, "open")
    if err or not sig_valid:
        return False, 401, err or "unauthorized: invalid signature", data

    # One signature, one call. Measured before this: a single signature over
    # {timestamp} read /admin/logs, then /admin/sessions, then /admin/logs again
    # — all 200. For its five-minute window a captured admin signature was a
    # bearer token for the whole admin surface.
    #
    # signature_already_used() is auth.py's, the same record CONNECT uses against
    # the replay in #649, called here rather than reimplemented.
    #
    from ..host.auth import signature_already_used

    if signature_already_used(data):
        return False, 401, "unauthorized: signature already used", data

    trust_agent = route_handlers.get("trust_agent")
    if trust_agent is None:
        return False, 401, "unauthorized", data
    if require_super:
        if not trust_agent.is_super_admin(agent_address):
            return False, 403, "forbidden: super admin only", data
    elif not trust_agent.is_admin(agent_address):
        return False, 403, "forbidden: admin only", data

    return True, 200, None, data


async def handle_admin_routes(method, path, scope, receive, route_handlers, *, send_json, send_text, read_body):
    """Handle /admin/* and /superadmin/* HTTP routes. Returns True if handled, False otherwise."""

    # Read-only admin endpoints: signed admin identity, or a dedicated bearer.
    #
    # OPENONION_API_KEY pays for co/* models and travels through CI, .env files,
    # deploys and model calls. It must never authorize logs or sessions (#670).
    #
    # The signed path below is the one /admin/trust/* and /superadmin/* already
    # use, reused rather than reinvented: sign the request, be on admins.txt.
    # Non-interactive monitoring can retain the Bearer transport shape with a
    # separate per-deployment CONNECTONION_ADMIN_TOKEN. Explicitly reject reuse
    # of the billing key so a renamed environment variable cannot preserve the
    # original blast radius by accident.
    if path in ["/admin/logs", "/admin/sessions"]:
        headers_dict = dict(scope.get("headers", []))
        auth = headers_dict.get(b"authorization", b"").decode()
        admin_token = os.environ.get("CONNECTONION_ADMIN_TOKEN", "")
        billing_key = os.environ.get("OPENONION_API_KEY", "")
        distinct = not billing_key or not hmac.compare_digest(admin_token, billing_key)
        by_key = (
            bool(admin_token)
            and distinct
            and auth.startswith("Bearer ")
            and hmac.compare_digest(auth[7:], admin_token)
        )

        if not by_key:
            signed, status, error, _ = await _admin_signature(
                method, path, scope, receive, route_handlers, read_body=read_body
            )
            if not signed:
                await send_json({"error": error}, status)
                return True

        if method == "GET" and path == "/admin/logs":
            result = route_handlers["admin_logs"]()
            if "error" in result:
                await send_json(result, 404)
            else:
                await send_text(result["content"])
            return True

        if method == "GET" and path == "/admin/sessions":
            await send_json(route_handlers["admin_sessions"]())
            return True

    # Admin trust routes (signed request + admin check)
    if path.startswith("/admin/trust/") or path.startswith("/superadmin/"):
        ok, status, error, data = await _admin_signature(
            method, path, scope, receive, route_handlers, read_body=read_body,
            require_super=path.startswith("/superadmin/"),
        )
        if not ok:
            await send_json({"error": error}, status)
            return True

        payload = data.get("payload", {})
        client_id = payload.get("client_id")

        if method == "POST" and path == "/admin/trust/promote":
            if not client_id:
                await send_json({"error": "client_id required"}, 400)
                return True
            await send_json(route_handlers["admin_trust_promote"](client_id))
            return True

        if method == "POST" and path == "/admin/trust/demote":
            if not client_id:
                await send_json({"error": "client_id required"}, 400)
                return True
            await send_json(route_handlers["admin_trust_demote"](client_id))
            return True

        if method == "POST" and path == "/admin/trust/block":
            if not client_id:
                await send_json({"error": "client_id required"}, 400)
                return True
            reason = payload.get("reason", "")
            await send_json(route_handlers["admin_trust_block"](client_id, reason))
            return True

        if method == "POST" and path == "/admin/trust/unblock":
            if not client_id:
                await send_json({"error": "client_id required"}, 400)
                return True
            await send_json(route_handlers["admin_trust_unblock"](client_id))
            return True

        if method == "GET" and path.startswith("/admin/trust/level/"):
            client_id = path[len("/admin/trust/level/"):]
            await send_json(route_handlers["admin_trust_level"](client_id))
            return True

        if method == "POST" and path == "/superadmin/add":
            admin_id = payload.get("admin_id")
            if not admin_id:
                await send_json({"error": "admin_id required"}, 400)
                return True
            await send_json(route_handlers["admin_admins_add"](admin_id))
            return True

        if method == "POST" and path == "/superadmin/remove":
            admin_id = payload.get("admin_id")
            if not admin_id:
                await send_json({"error": "admin_id required"}, 400)
                return True
            await send_json(route_handlers["admin_admins_remove"](admin_id))
            return True

    await send_json({"error": "not found"}, 404)
    return True

"""HTTP admin and superadmin route handling.

Purpose: Authenticate and dispatch /admin/* and /superadmin/* HTTP requests for the hosted agent's trust controls (promote/demote/block/unblock, level lookup, super-admin add/remove, and legacy admin logs/sessions).
LLM-Note:
  Dependencies: imports from [hmac, json, os] | imported by [network/host/http_router.py (handle_admin_routes called for paths starting with /admin or /superadmin)] | tested by [no direct test file]
  Data flow: receives ASGI scope/receive + parsed method/path from http_router → /admin/logs and /admin/sessions accept EITHER Bearer OPENONION_API_KEY (hmac.compare_digest) or a signed admin request; /admin/trust/* and /superadmin/* require the signed one. Both go through _admin_signature — one implementation, so the check guarding the trust routes cannot drift from the check guarding the logs. GETs may sign via X-From/X-Signature/X-Timestamp headers (proxies often strip GET bodies). A route_handlers without "auth" or "trust_agent" has no signed path and answers 401 rather than raising → calls into route_handlers callbacks (admin_logs, admin_sessions, admin_trust_promote/demote/block/unblock/level, admin_admins_add/remove) → responds via send_json/send_text
  State/Effects: invokes route_handlers (which mutate trust agent state, file logs, sessions) | reads OPENONION_API_KEY from env for legacy auth | logs nothing directly
  Integration: exposes async handle_admin_routes(method, path, scope, receive, route_handlers, *, send_json, send_text, read_body) -> bool (always True after this function — it owns the response for /admin/* and /superadmin/*) | route_handlers dict must include "trust_agent", "auth", and the admin_* callbacks
  Errors: returns 401 unauthorized on bad bearer/signature or a route_handlers with no verifier wired, 403 forbidden when not admin/superadmin, 400 on missing client_id/admin_id or invalid X-Timestamp/JSON, 404 catch-all for unknown admin paths — never raises
  Security: ⚠️ bearer comparison uses hmac.compare_digest to avoid timing leaks | signature verification delegated to route_handlers["auth"] | the bearer key is the model billing credential, which is why signing is now an alternative (#670)
"""

import hmac
import json
import os


async def _admin_signature(method, scope, receive, route_handlers, *, read_body,
                           require_super=False):
    """Verify a signed admin request. -> (ok, status, error, data).

    `data` comes back because the body can only be read once: the caller needs
    the payload it carries (client_id, reason) and cannot go get it again.

    One implementation for both route families. /admin/trust/* and
    /superadmin/* have always used this; /admin/logs and /admin/sessions now
    accept it too, so reading an agent's activity no longer requires the key
    that spends its money (#670). A second copy of a signature check is the
    thing most likely to drift out of step with the one that guards more.

    GETs may carry the signature in X-From / X-Signature / X-Timestamp, because
    proxies strip GET bodies.
    """
    headers_dict = dict(scope.get("headers", []))
    header_from = headers_dict.get(b"x-from", b"").decode()
    header_sig = headers_dict.get(b"x-signature", b"").decode()
    header_ts = headers_dict.get(b"x-timestamp", b"").decode()

    if method == "GET" and header_from and header_sig and header_ts:
        try:
            data = {"payload": {"timestamp": float(header_ts)},
                    "from": header_from, "signature": header_sig}
        except ValueError:
            return False, 400, "Invalid X-Timestamp header", {}
    else:
        body = await read_body(receive)
        try:
            data = json.loads(body) if body else {}
        except json.JSONDecodeError:
            return False, 400, "Invalid JSON", {}

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
    # What this does not fix: the payload is {timestamp} alone, so a signature is
    # still not bound to the route it was made for. Binding it to method and path
    # — which auth.py's own signed-GET scheme does, over {method, path,
    # timestamp} with x-co-* headers — is a protocol change for any client
    # already signing admin calls, so it is filed rather than slipped in here.
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

    # Legacy admin endpoints: Bearer OPENONION_API_KEY, or a signed admin request.
    #
    # The Bearer key is what pays for co/* models — `co auth` obtains it, `co
    # create` writes it into the project's .env, and every model call sends it to
    # oo.openonion.ai. So letting someone read an agent's activity meant handing
    # over the credential that spends its money (#670).
    #
    # The signed path below is the one /admin/trust/* and /superadmin/* already
    # use, reused rather than reinvented: sign the request, be on admins.txt.
    # Bearer stays because 1.6.0 is long-term and the curl in the shipped
    # docs.html uses it; this widens what works, and a later major can drop it.
    if path in ["/admin/logs", "/admin/sessions"]:
        headers_dict = dict(scope.get("headers", []))
        auth = headers_dict.get(b"authorization", b"").decode()
        expected = os.environ.get("OPENONION_API_KEY", "")
        by_key = bool(expected) and auth.startswith("Bearer ") and hmac.compare_digest(auth[7:], expected)

        if not by_key:
            signed, status, error, _ = await _admin_signature(
                method, scope, receive, route_handlers, read_body=read_body
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
            method, scope, receive, route_handlers, read_body=read_body,
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

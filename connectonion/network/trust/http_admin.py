"""HTTP admin and superadmin route handling."""

import hmac
import json
import os


async def handle_admin_routes(method, path, scope, receive, route_handlers, *, send_json, send_text, read_body):
    """Handle /admin/* and /superadmin/* HTTP routes. Returns True if handled, False otherwise."""

    # Legacy admin endpoints (Bearer token auth)
    if path in ["/admin/logs", "/admin/sessions"]:
        headers_dict = dict(scope.get("headers", []))
        auth = headers_dict.get(b"authorization", b"").decode()
        expected = os.environ.get("OPENONION_API_KEY", "")
        if not expected or not auth.startswith("Bearer ") or not hmac.compare_digest(auth[7:], expected):
            await send_json({"error": "unauthorized"}, 401)
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
        trust_agent = route_handlers["trust_agent"]

        # For GET requests, allow auth via headers (bodies often stripped by proxies)
        headers_dict = dict(scope.get("headers", []))
        header_from = headers_dict.get(b"x-from", b"").decode()
        header_sig = headers_dict.get(b"x-signature", b"").decode()
        header_ts = headers_dict.get(b"x-timestamp", b"").decode()

        if method == "GET" and header_from and header_sig and header_ts:
            try:
                data = {
                    "payload": {"timestamp": float(header_ts)},
                    "from": header_from,
                    "signature": header_sig
                }
            except ValueError:
                await send_json({"error": "Invalid X-Timestamp header"}, 400)
                return True
        else:
            body = await read_body(receive)
            try:
                data = json.loads(body) if body else {}
            except json.JSONDecodeError:
                await send_json({"error": "Invalid JSON"}, 400)
                return True

        _, identity, sig_valid, err = route_handlers["auth"](data, "open")
        if err or not sig_valid:
            await send_json({"error": err or "unauthorized: invalid signature"}, 401)
            return True

        if path.startswith("/superadmin/"):
            if not trust_agent.is_super_admin(identity):
                await send_json({"error": "forbidden: super admin only"}, 403)
                return True
        else:
            if not trust_agent.is_admin(identity):
                await send_json({"error": "forbidden: admin only"}, 403)
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

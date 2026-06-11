"""WebSocket admin and onboard message handlers.

Purpose: Verify signed websocket frames for ONBOARD_SUBMIT and ADMIN_* actions, then mutate trust state (verify invite/payment, promote/demote/block/unblock, super-admin add/remove) and stream back ONBOARD_SUCCESS / ADMIN_RESULT / ERROR responses. handle_onboard_submit returns the verified identity so the session loop can finish the trust-gated CONNECT.
LLM-Note:
  Dependencies: imports from [rich.console] | imported by [network/host/ws_router/session.py (handle_admin_message, handle_onboard_submit), network/host/ws_router/connect.py (get_onboard_requirements during CONNECT)] | tested by [tests/network/test_ws_admin.py, tests/integration/test_onboard_flow.py]
  Data flow:
    • get_onboard_requirements(trust_agent) — read trust_agent.config.onboard → {methods: ["invite_code"|"payment"], payment_amount, payment_address (from trust_agent.get_self_address())} or None
    • handle_onboard_submit(data, send_msg, route_handlers) — auth via route_handlers["auth"](data, "open") → check trust_agent.is_blocked → verify_invite or verify_payment → reply ONBOARD_SUCCESS with new level or ERROR
    • handle_admin_message(data, send_msg, route_handlers) — auth + is_admin gate → ADMIN_PROMOTE/DEMOTE/BLOCK/UNBLOCK/GET_LEVEL routed to route_handlers admin_trust_* callbacks → ADMIN_ADD/REMOVE additionally gated on is_super_admin → reply ADMIN_RESULT
  State/Effects: mutates trust agent state via trust_agent.verify_invite/verify_payment and admin_trust_* / admin_admins_* callbacks | prints colored audit lines to stdout via rich.Console (✓/✗ with truncated identity) | sends frames to client via injected send_msg
  Integration: exposes get_onboard_requirements(trust_agent), async handle_onboard_submit(data, send_msg, route_handlers), async handle_admin_message(data, send_msg, route_handlers) | route_handlers dict must contain auth, trust_agent, admin_trust_promote/demote/block/unblock/level, admin_admins_add/remove
  Errors: returns ERROR frames (never raises) for: invalid signature, blocked identity, missing client_id/admin_id, bad invite code, insufficient payment, non-admin, non-super-admin, unknown admin action
  Security: ⚠️ all state-changing operations require valid signature + admin/super-admin level | invite/payment verification delegated to TrustAgent
"""

from rich.console import Console

console = Console()


def get_onboard_requirements(trust_agent) -> dict | None:
    """Extract onboard requirements from trust config."""
    config = trust_agent.config
    onboard = config.get("onboard", {})
    if not onboard:
        return None

    result = {"methods": []}
    if "invite_code" in onboard:
        result["methods"].append("invite_code")
    if "payment" in onboard:
        result["methods"].append("payment")
        result["payment_amount"] = onboard["payment"]
        payment_address = trust_agent.get_self_address()
        if payment_address:
            result["payment_address"] = payment_address

    return result if result["methods"] else None


async def handle_onboard_submit(data, send_msg, route_handlers):
    """Handle ONBOARD_SUBMIT message from client. Returns the verified identity on success."""
    trust_agent = route_handlers["trust_agent"]

    _, identity, sig_valid, err = route_handlers["auth"](data, "open")
    if err or not sig_valid:
        await send_msg({"type": "ERROR", "message": err or "invalid signature"})
        return

    if trust_agent.is_blocked(identity):
        await send_msg({"type": "ERROR", "message": "forbidden: blocked"})
        return

    payload = data.get("payload", {})
    invite_code = payload.get("invite_code")
    payment = payload.get("payment", 0)

    if invite_code:
        if trust_agent.verify_invite(identity, invite_code):
            actual_level = trust_agent.get_level(identity)
            console.print(f"[green]✓[/green] Verified [bold]{identity[:16]}...[/bold] with invite code [cyan]{invite_code}[/cyan] → {actual_level}")
            await send_msg({
                "type": "ONBOARD_SUCCESS",
                "identity": identity,
                "level": actual_level,
                "message": f"Invite code verified. You are now a {actual_level}."
            })
            return identity
        else:
            console.print(f"[red]✗[/red] Invalid invite code [cyan]{invite_code}[/cyan] from {identity[:16]}...")
            await send_msg({"type": "ERROR", "message": "Invalid invite code"})
            return

    if payment > 0:
        if trust_agent.verify_payment(identity, payment):
            actual_level = trust_agent.get_level(identity)
            console.print(f"[green]✓[/green] Verified [bold]{identity[:16]}...[/bold] with payment [cyan]${payment}[/cyan] → {actual_level}")
            await send_msg({
                "type": "ONBOARD_SUCCESS",
                "identity": identity,
                "level": actual_level,
                "message": f"Payment verified. You are now a {actual_level}."
            })
            return identity
        else:
            console.print(f"[red]✗[/red] Insufficient payment [cyan]${payment}[/cyan] from {identity[:16]}...")
            await send_msg({"type": "ERROR", "message": "Insufficient payment"})
            return

    await send_msg({"type": "ERROR", "message": "invite_code or payment required"})


async def handle_admin_message(data, send_msg, route_handlers):
    """Handle ADMIN_* messages from client."""
    trust_agent = route_handlers["trust_agent"]
    msg_type = data.get("type")

    _, identity, sig_valid, err = route_handlers["auth"](data, "open")
    if err or not sig_valid:
        await send_msg({"type": "ERROR", "message": err or "invalid signature"})
        return

    if not trust_agent.is_admin(identity):
        await send_msg({"type": "ERROR", "message": "forbidden: admin only"})
        return

    payload = data.get("payload", {})
    client_id = payload.get("client_id")

    if msg_type == "ADMIN_PROMOTE":
        if not client_id:
            await send_msg({"type": "ERROR", "message": "client_id required"})
            return
        result = route_handlers["admin_trust_promote"](client_id)
        await send_msg({"type": "ADMIN_RESULT", "action": "promote", **result})

    elif msg_type == "ADMIN_DEMOTE":
        if not client_id:
            await send_msg({"type": "ERROR", "message": "client_id required"})
            return
        result = route_handlers["admin_trust_demote"](client_id)
        await send_msg({"type": "ADMIN_RESULT", "action": "demote", **result})

    elif msg_type == "ADMIN_BLOCK":
        if not client_id:
            await send_msg({"type": "ERROR", "message": "client_id required"})
            return
        reason = payload.get("reason", "")
        result = route_handlers["admin_trust_block"](client_id, reason)
        await send_msg({"type": "ADMIN_RESULT", "action": "block", **result})

    elif msg_type == "ADMIN_UNBLOCK":
        if not client_id:
            await send_msg({"type": "ERROR", "message": "client_id required"})
            return
        result = route_handlers["admin_trust_unblock"](client_id)
        await send_msg({"type": "ADMIN_RESULT", "action": "unblock", **result})

    elif msg_type == "ADMIN_GET_LEVEL":
        if not client_id:
            await send_msg({"type": "ERROR", "message": "client_id required"})
            return
        result = route_handlers["admin_trust_level"](client_id)
        await send_msg({"type": "ADMIN_RESULT", "action": "get_level", **result})

    elif msg_type == "ADMIN_ADD":
        if not trust_agent.is_super_admin(identity):
            await send_msg({"type": "ERROR", "message": "forbidden: super admin only"})
            return
        admin_id = payload.get("admin_id")
        if not admin_id:
            await send_msg({"type": "ERROR", "message": "admin_id required"})
            return
        result = route_handlers["admin_admins_add"](admin_id)
        await send_msg({"type": "ADMIN_RESULT", "action": "add_admin", **result})

    elif msg_type == "ADMIN_REMOVE":
        if not trust_agent.is_super_admin(identity):
            await send_msg({"type": "ERROR", "message": "forbidden: super admin only"})
            return
        admin_id = payload.get("admin_id")
        if not admin_id:
            await send_msg({"type": "ERROR", "message": "admin_id required"})
            return
        result = route_handlers["admin_admins_remove"](admin_id)
        await send_msg({"type": "ADMIN_RESULT", "action": "remove_admin", **result})

    else:
        await send_msg({"type": "ERROR", "message": f"Unknown admin action: {msg_type}"})

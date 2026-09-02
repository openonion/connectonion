"""PROXY_ATTACH and PROXY_STREAM: a laptop lending its connection to this host."""

from datetime import datetime, timezone

from ...proxy import GrantError, verify
from ...proxy import stream as wire
from ..proxy_channel import ProxyChannel

ATTACH_REQUIRES = ("admin", "whitelist", "contact")


def _attach_claims(data, conn, route_handlers) -> dict:
    """The verified grant claims, or GrantError saying why not.

    Same trust bar as REMOTE_BROWSER: a contact or admin, on a direct socket.
    """
    if not conn["authenticated"] or not conn["signed_commands"]:
        raise GrantError("authenticate first (send a signed CONNECT)")
    if conn["transport"] != "direct":
        raise GrantError("a share attaches over a direct connection, not the relay")
    if route_handlers.get("proxy_channels") is None:
        raise GrantError("Remote Browser is not configured on this host")
    trust = route_handlers["trust_agent"]
    address = conn["agent_address"]
    level = "admin" if trust.is_admin(address) else trust.get_level(address)
    if level not in ATTACH_REQUIRES:
        raise GrantError(f"sharing a connection requires a contact or admin; the caller is {level}")
    grant = data.get("grant")
    if not isinstance(grant, dict):
        raise GrantError("PROXY_ATTACH carries no grant")
    # The laptop signed the grant for this host to use, so the host is the
    # presenter. And only the identity on this socket may lend its own exit:
    # the grantor has to be the address CONNECT authenticated.
    claims = verify(
        grant,
        None,
        presenter=route_handlers["agent_metadata"]["address"],
        now=datetime.now(timezone.utc),
    )
    if claims["grantor"] != address:
        raise GrantError("grantor is not the connected agent")
    return claims


async def attach_proxy(data, send_msg, conn, route_handlers):
    """Verify the grant, open the loopback gateway, register the channel.

    Returns the channel the session must detach in its finally, or None when
    the attach was refused and the ERROR frame has been sent.
    """
    try:
        claims = _attach_claims(data, conn, route_handlers)
    except GrantError as refused:
        await send_msg({"type": "ERROR", "message": f"proxy attach refused: {refused}"})
        return None
    channel = ProxyChannel(send_msg, claims)
    await channel.gateway.start()
    displaced = route_handlers["proxy_channels"].attach(channel)
    if displaced is not None:
        await displaced.close()
    await send_msg({
        "type": wire.ATTACHED,
        "expires_at": claims["expires_at"],
        "max_bytes": claims["max_bytes"],
    })
    return channel


async def detach_proxy(channel, route_handlers):
    """The session ended: no share is reachable through it any more."""
    route_handlers["proxy_channels"].detach(channel)
    await channel.close()

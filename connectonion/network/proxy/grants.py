"""
Purpose: Signed proxy grants and delegations — the authorisation objects that let one agent egress through another agent's network, decided in advance so nobody has to be online at 3am
LLM-Note:
  Dependencies: imports from [json, secrets, datetime, nacl.signing, ...address (sign)] | imported by [network/proxy/__init__.py] | tested by [tests/unit/test_proxy_grants.py]
  Data flow: P calls issue_grant(keys, holder=..., delegable_to=[...]) → signed grant dict | D calls issue_delegation(keys, grant, delegate=B) → signed delegation dict | B presents both to P → P calls verify(grant, delegation, presenter=<authenticated address>, now=...) → verified claims or GrantError
  State/Effects: pure functions over dicts — no files, no network, no clock reads (callers pass `now`)
  Integration: design record is issue #1036; the chain is P→D→B with a direct grant being the same object with holder == presenter and no delegation | signatures follow host/auth.py's canonicalisation (sorted-keys compact JSON) and address.sign()
  Errors: every verification failure raises GrantError naming exactly which check refused — an unauthorised proxy use must fail loudly, never fall through

The one check that carries the design (#1036): the delegate identity must equal
the *presenter* — the authenticated identity of whoever is USING the credential —
not whoever opened the TCP connection. In the reverse-tunnel topology the proxy
dials the browser, so "connecting endpoint" would make P verify itself and the
chain would protect nothing. Who dials is an accident of NAT; who authorises is
the design.
"""

import json
import secrets
from datetime import datetime, timezone

from ... import address as _address


class GrantError(ValueError):
    """A grant or delegation failed verification; the message names the check."""


def _canonical(payload: dict) -> bytes:
    """The bytes that get signed. Same shape as host/auth.py's."""
    unsigned = {key: value for key, value in payload.items() if key != "signature"}
    return json.dumps(unsigned, sort_keys=True, separators=(",", ":")).encode()


def _parse_time(value: str, field: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise GrantError(f"{field} must carry a timezone: {value!r}")
    return parsed


def _verify_signature(payload: dict, signer: str, kind: str) -> None:
    from nacl.exceptions import BadSignatureError
    from nacl.signing import VerifyKey

    try:
        VerifyKey(bytes.fromhex(signer[2:])).verify(
            _canonical(payload), bytes.fromhex(payload["signature"])
        )
    except (BadSignatureError, ValueError) as refused:
        raise GrantError(f"{kind} signature does not verify against {signer}") from refused


def issue_grant(
    keys: dict,
    *,
    holder: str,
    expires_at: str,
    delegable_to: list | None = None,
    scope: str = "public_internet",
    renewable_until: str | None = None,
    max_bytes: int | None = None,
) -> dict:
    """P's decision, signed by P: `holder` may use this egress.

    A direct grant to the machine that will connect is simply holder == that
    machine and no delegable_to — the chain of length one (#1036).
    """
    grant = {
        "type": "proxy_grant",
        "grant_id": "pxg_" + secrets.token_urlsafe(12),
        "grantor": keys["address"],
        "holder": holder,
        "delegable_to": list(delegable_to or []),
        "scope": scope,
        "expires_at": expires_at,
        "renewable_until": renewable_until,
        "max_bytes": max_bytes,
    }
    if renewable_until is not None and _parse_time(renewable_until, "renewable_until") < _parse_time(expires_at, "expires_at"):
        raise GrantError("renewable_until is earlier than expires_at")
    grant["signature"] = _address.sign(keys, _canonical(grant)).hex()
    return grant


def issue_delegation(keys: dict, grant: dict, *, delegate: str, expires_at: str | None = None) -> dict:
    """D naming the machine that will actually connect — signed in advance, so D
    can be offline when it is used."""
    delegation = {
        "type": "proxy_delegation",
        "grant_id": grant["grant_id"],
        "delegator": keys["address"],
        "delegate": delegate,
        "expires_at": expires_at or grant["expires_at"],
    }
    delegation["signature"] = _address.sign(keys, _canonical(delegation)).hex()
    return delegation


def renew_grant(keys: dict, grant: dict, *, expires_at: str) -> dict:
    """A fresh signature with a later expiry — allowed only inside the ceiling P
    pre-authorised. This is what keeps a 3am schedule alive without letting any
    party extend an authorisation on its own (#1036: renewal model)."""
    if keys["address"] != grant["grantor"]:
        raise GrantError("only the grantor renews a grant")
    ceiling = grant.get("renewable_until")
    if ceiling is None:
        raise GrantError("grant was issued without renewable_until; issue a new one")
    if _parse_time(expires_at, "expires_at") > _parse_time(ceiling, "renewable_until"):
        raise GrantError(f"renewal past renewable_until ({ceiling})")
    renewed = {**grant, "expires_at": expires_at}
    del renewed["signature"]
    renewed["signature"] = _address.sign(keys, _canonical(renewed)).hex()
    return renewed


def verify(grant: dict, delegation: dict | None, *, presenter: str, now: datetime) -> dict:
    """Accept or refuse a presented credential chain.

    `presenter` is the authenticated identity of the party USING the credential
    (the browser), never the party that happened to open the connection.

    Returns the verified claims a proxy needs: who egresses, under which grant,
    with which scope, until when, and within what byte budget.
    """
    if now.tzinfo is None:
        raise GrantError("now must be timezone-aware")
    if grant.get("type") != "proxy_grant":
        raise GrantError(f"not a proxy_grant: {grant.get('type')!r}")
    _verify_signature(grant, grant["grantor"], "grant")
    grant_expiry = _parse_time(grant["expires_at"], "grant expires_at")
    if now >= grant_expiry:
        raise GrantError(f"grant expired at {grant['expires_at']}")

    if delegation is None:
        if presenter != grant["holder"]:
            raise GrantError("presenter is not the grant holder and no delegation was presented")
        effective_expiry = grant_expiry
    else:
        if delegation.get("type") != "proxy_delegation":
            raise GrantError(f"not a proxy_delegation: {delegation.get('type')!r}")
        if delegation["grant_id"] != grant["grant_id"]:
            raise GrantError("delegation names a different grant")
        if delegation["delegator"] != grant["holder"]:
            raise GrantError("delegation is not signed by the grant holder")
        _verify_signature(delegation, delegation["delegator"], "delegation")
        if delegation["delegate"] not in grant["delegable_to"]:
            raise GrantError("delegate is not in the grant's delegable_to list")
        delegation_expiry = _parse_time(delegation["expires_at"], "delegation expires_at")
        if delegation_expiry > grant_expiry:
            raise GrantError("delegation outlives the grant")
        if now >= delegation_expiry:
            raise GrantError(f"delegation expired at {delegation['expires_at']}")
        # The check the whole design rests on: bind to who is USING the
        # credential, not who dialed. See the module docstring.
        if presenter != delegation["delegate"]:
            raise GrantError("presenter is not the delegate this chain authorises")
        effective_expiry = min(grant_expiry, delegation_expiry)

    return {
        "egress_for": presenter,
        "grant_id": grant["grant_id"],
        "grantor": grant["grantor"],
        "accountable": grant["holder"],
        "scope": grant["scope"],
        "expires_at": effective_expiry.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
        "max_bytes": grant.get("max_bytes"),
    }

"""The grant chain from #1036: P authorises in advance, nobody signs at 3am.

Three parties throughout, named as in the design record:

    P — proxy agent, owns the egress, signs grants
    D — developer's agent, holds a grant, signs delegations, then goes offline
    B — remote browser, presents the chain and egresses

The one test that carries the design is
test_presenter_binding_refuses_the_dialing_party: in the reverse-tunnel
topology P dials B, so binding to "whoever connected" would have P verify
itself. The chain binds to whoever PRESENTS the credential.
"""

from datetime import datetime, timedelta, timezone

import pytest

from connectonion import address
from connectonion.network.proxy import (
    GrantError,
    issue_delegation,
    issue_grant,
    renew_grant,
    verify,
)

NOW = datetime(2026, 8, 18, 3, 0, tzinfo=timezone.utc)  # 3am, the design's test hour
LATER = (NOW + timedelta(hours=24)).isoformat().replace("+00:00", "Z")
CEILING = (NOW + timedelta(days=30)).isoformat().replace("+00:00", "Z")


@pytest.fixture(scope="module")
def parties():
    return {"P": address.generate(), "D": address.generate(), "B": address.generate()}


def _direct(parties, **overrides):
    kwargs = {"holder": parties["B"]["address"], "expires_at": LATER, **overrides}
    return issue_grant(parties["P"], **kwargs)


def _chain(parties, **grant_overrides):
    grant = issue_grant(
        parties["P"],
        holder=parties["D"]["address"],
        delegable_to=[parties["B"]["address"]],
        expires_at=LATER,
        **grant_overrides,
    )
    delegation = issue_delegation(parties["D"], grant, delegate=parties["B"]["address"])
    return grant, delegation


# --- the direct grant: chain of length one -------------------------------------


def test_direct_grant_verifies_for_its_holder(parties):
    claims = verify(_direct(parties), None, presenter=parties["B"]["address"], now=NOW)
    assert claims["egress_for"] == parties["B"]["address"]
    assert claims["accountable"] == parties["B"]["address"]


def test_direct_grant_refuses_anyone_else(parties):
    with pytest.raises(GrantError, match="not the grant holder"):
        verify(_direct(parties), None, presenter=parties["D"]["address"], now=NOW)


def test_a_tampered_grant_does_not_verify(parties):
    grant = _direct(parties)
    grant["max_bytes"] = 10**12  # quota raised after signing
    with pytest.raises(GrantError, match="signature"):
        verify(grant, None, presenter=parties["B"]["address"], now=NOW)


def test_a_grant_signed_by_the_wrong_key_names_the_grantor(parties):
    forged = issue_grant(parties["D"], holder=parties["B"]["address"], expires_at=LATER)
    forged["grantor"] = parties["P"]["address"]  # claims to be P's network
    with pytest.raises(GrantError, match="signature"):
        verify(forged, None, presenter=parties["B"]["address"], now=NOW)


def test_an_expired_grant_is_refused(parties):
    grant = _direct(parties)
    with pytest.raises(GrantError, match="expired"):
        verify(grant, None, presenter=parties["B"]["address"], now=NOW + timedelta(days=2))


# --- the delegated chain: P → D → B --------------------------------------------


def test_the_full_chain_verifies_and_attributes_to_the_holder(parties):
    grant, delegation = _chain(parties)
    claims = verify(grant, delegation, presenter=parties["B"]["address"], now=NOW)
    assert claims["egress_for"] == parties["B"]["address"]
    # every byte attributes to D, the account — not to the worker machine
    assert claims["accountable"] == parties["D"]["address"]


def test_presenter_binding_refuses_the_dialing_party(parties):
    """P dials B in the reverse tunnel; P presenting the chain must still fail."""
    grant, delegation = _chain(parties)
    with pytest.raises(GrantError, match="presenter"):
        verify(grant, delegation, presenter=parties["P"]["address"], now=NOW)


def test_a_delegate_outside_the_pinned_list_is_refused(parties):
    grant = issue_grant(
        parties["P"], holder=parties["D"]["address"], delegable_to=[], expires_at=LATER
    )
    delegation = issue_delegation(parties["D"], grant, delegate=parties["B"]["address"])
    with pytest.raises(GrantError, match="delegable_to"):
        verify(grant, delegation, presenter=parties["B"]["address"], now=NOW)


def test_a_delegation_signed_by_a_non_holder_is_refused(parties):
    grant, _ = _chain(parties)
    stranger = address.generate()
    forged = issue_delegation(stranger, grant, delegate=parties["B"]["address"])
    forged["delegator"] = parties["D"]["address"]  # claims D signed it
    with pytest.raises(GrantError, match="signature"):
        verify(grant, forged, presenter=parties["B"]["address"], now=NOW)


def test_a_delegation_for_a_different_grant_is_refused(parties):
    grant, _ = _chain(parties)
    other_grant, other_delegation = _chain(parties)
    assert other_grant["grant_id"] != grant["grant_id"]
    with pytest.raises(GrantError, match="different grant"):
        verify(grant, other_delegation, presenter=parties["B"]["address"], now=NOW)


def test_a_delegation_cannot_outlive_its_grant(parties):
    grant, _ = _chain(parties)
    stretched = issue_delegation(
        parties["D"],
        grant,
        delegate=parties["B"]["address"],
        expires_at=(NOW + timedelta(days=365)).isoformat().replace("+00:00", "Z"),
    )
    with pytest.raises(GrantError, match="outlives"):
        verify(grant, stretched, presenter=parties["B"]["address"], now=NOW)


# --- renewal: the pre-authorised ceiling ---------------------------------------


def test_renewal_inside_the_ceiling_keeps_the_schedule_alive(parties):
    grant = _direct(parties, renewable_until=CEILING)
    renewed = renew_grant(
        parties["P"],
        grant,
        expires_at=(NOW + timedelta(days=2)).isoformat().replace("+00:00", "Z"),
    )
    later = NOW + timedelta(hours=30)  # past the original expiry
    claims = verify(renewed, None, presenter=parties["B"]["address"], now=later)
    assert claims["grant_id"] == grant["grant_id"]


def test_renewal_past_the_ceiling_is_refused(parties):
    grant = _direct(parties, renewable_until=CEILING)
    with pytest.raises(GrantError, match="renewable_until"):
        renew_grant(
            parties["P"],
            grant,
            expires_at=(NOW + timedelta(days=60)).isoformat().replace("+00:00", "Z"),
        )


def test_only_the_grantor_renews(parties):
    grant = _direct(parties, renewable_until=CEILING)
    with pytest.raises(GrantError, match="grantor"):
        renew_grant(parties["B"], grant, expires_at=LATER)


def test_a_grant_without_a_ceiling_cannot_be_renewed_at_all(parties):
    grant = _direct(parties)  # no renewable_until: an authorisation with a hard end
    with pytest.raises(GrantError, match="renewable_until"):
        renew_grant(parties["P"], grant, expires_at=LATER)

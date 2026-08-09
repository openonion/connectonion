"""Which browser binary `co browser` drives: the free one, or the one you paid for.

    free   patchright + the Chrome already on this machine
    pro    the onion browser, a patched Chromium

The split is decided by the server (`service.entitlement()` in oo-api, keyed on
cumulative credit) and carried in a signed attestation. This module does not
decide *whether* someone paid -- it only reads the answer and picks a binary.

One rule runs through all of it, and it is the reason the decision is a pure
function with no network in it:

**Nothing here may stop a browser from starting.**

A default install drives system Chrome through patchright today, with no licence
call anywhere on the path -- measured on a clean Ubuntu box, not assumed. So it
cannot currently be blocked by billing, an expired attestation, or an oo-api
outage, and adding tiering must not hand a free user a new way to fail. Every
branch below ends in an engine; the only thing that varies is which one, and
whether we say something about it.

The `note` exists because the interesting case is not an error either: an
account holding only the $5 signup grant is not broken, it is not yet enough.
That deserves one line saying what unlocks the other engine, not a traceback and
not silence.
"""

ONION = "onion"
PATCHRIGHT = "patchright"

# Kept in step with license_api.billing.PRO_MIN_CREDIT_USD in oo-api. Written
# here as a display string only -- the client never enforces the threshold, it
# just repeats it, because the account is the server's to judge.
PRO_MIN_CREDIT_USD = 10.00


def _tier_of(attestation):
    """The attested tier, or None if there isn't one we understand.

    A payload missing the fields we read is a server we do not understand, and
    the safe reading of "do not understand" is "no licence": guessing `pro`
    would try to launch a binary that may not be on disk, guessing `free` just
    works.
    """
    if not isinstance(attestation, dict):
        return None
    tier = attestation.get("tier")
    return tier if isinstance(tier, str) else None


def choose(attestation, onion_present):
    """Pick an engine. Returns `(engine, note)` and never raises.

    `attestation` is the decoded licence payload, or None when there isn't one
    — no account, no licence, or oo-api was unreachable. All three mean the
    same thing here, deliberately: they are all "we could not establish that
    this is a paying customer", and none of them is a reason to withhold a
    browser.

    `note` is a single line for the person, or None when there is nothing worth
    saying. It is not an error channel.
    """
    tier = _tier_of(attestation)

    if tier != "pro":
        if tier == "free":
            return PATCHRIGHT, (
                f"Using Chrome via patchright — the free engine. "
                f"The privacy browser unlocks at ${PRO_MIN_CREDIT_USD:.2f} of credit."
            )
        # No licence at all, or a shape we do not recognise. Say nothing: an
        # offline machine printing a sales line on every command is noise, and
        # we have not established there is anything to sell to.
        return PATCHRIGHT, None

    # Entitled to the paid engine. Two things can still send us back to
    # patchright, and neither is a failure the customer should see as one.
    if not attestation.get("active", False):
        # Entitled, but the session was refused — an empty balance. That is the
        # licence layer's business; it is not a reason to leave someone with no
        # browser at all.
        return PATCHRIGHT, (
            "Your balance is empty, so the privacy browser could not start a "
            "session. Running on Chrome via patchright until it is topped up."
        )

    if not onion_present:
        # `onionwright` is not a dependency of connectonion, so a fresh install
        # has no paid binary on disk. A pro customer with nothing to launch must
        # not end up worse off than a free one.
        return PATCHRIGHT, (
            "The privacy browser is not installed yet — running on Chrome via "
            "patchright for now."
        )

    return ONION, None

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


# The paid engine is not reachable from here yet, and this names exactly what
# is missing rather than leaving a stub that reads as finished.
#
# `onionwright.licence.license.load(path, server_key)` needs a cache path and
# the pinned server key; `onionwright.launcher.resolve_binary(token,
# server_key, pin)` needs an authenticated token and a Chromium revision.
# connectonion holds none of those three today. Supplying them is the open
# work in openonion/connectonion#511 — not something to fake here.
#
# Until then the defaults below raise, `resolve()` reads that as "no licence"
# the same way it reads an offline machine, and everyone gets the free engine.
# That is the right failure direction and the wrong end state, so
# test_the_paid_path_is_not_wired_up_yet asserts it out loud: when the wiring
# lands, that test fails and has to be deleted, which is the point of it.
PAID_WIRING_PENDING = (
    "onionwright is installed but connectonion has no licence configuration "
    "yet (cache path, pinned server key, Chromium revision) — see "
    "openonion/connectonion#511"
)


def _cached_attestation():
    """The licence this machine already holds, or None.

    The import is load-bearing. `onionwright` is not a dependency of
    connectonion, so on a default install this raises ImportError immediately
    and we are done -- no token read, no HTTP, no clock check. A free machine
    reaches the network exactly as often as it did before tiering existed,
    which is never.

    Reading the *cache* rather than refreshing is also deliberate: a browser
    command is not the right place to discover that oo-api is slow. The
    refresh belongs to the licence client's own schedule (it renews at the
    12-hour half-life of a 24-hour attestation), not to `co browser go_to`.
    """
    import onionwright.licence  # noqa: F401

    raise NotImplementedError(PAID_WIRING_PENDING)


def _onion_path():
    """Where the paid binary is, or None.

    Deliberately no `getattr(..., default)` probe. An earlier version guessed
    at `launcher.installed_path`, which does not exist, and the default made
    it answer "absent" on every machine including a paid one -- a silent
    permanent downgrade that the tests could not see because they inject this
    function. A name that is wrong should fail loudly enough to notice.
    """
    import onionwright.launcher  # noqa: F401

    raise NotImplementedError(PAID_WIRING_PENDING)


def resolve(load_attestation=_cached_attestation, onion_path=_onion_path,
            with_path=False):
    """Decide the engine against the real machine. Never raises.

    Returns `(engine, note)`, or `(engine, note, path)` when `with_path`.

    Both lookups are injected so the policy above stays testable without a
    paid install, and both are wrapped: an exception from either means "we
    could not establish a licence", which `choose()` already treats as free.
    Every failure mode of asking therefore lands on the branch that works.

    The path is only returned for the paid engine. patchright and system
    Chrome are already resolved by `installed_browser_path()`, and duplicating
    that here would give the machine two answers to one question.
    """
    try:
        attestation = load_attestation()
    except Exception:
        attestation = None

    try:
        path = onion_path()
    except Exception:
        path = None

    chosen, note = choose(attestation=attestation, onion_present=bool(path))

    if with_path:
        return chosen, note, (path if chosen == ONION else None)
    return chosen, note

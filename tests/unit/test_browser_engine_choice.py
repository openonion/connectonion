"""Which engine `co browser` drives, given what the account is entitled to.

The decision is a pure function on purpose. Everything around it -- fetching an
attestation, downloading a binary -- can fail, and the one thing that must not
acquire a new way to fail is the free path: a default install drives system
Chrome through patchright today with no licence call at all, and that is
measured, not assumed (see the e2e run on openonion/connectonion#511).

So the rule the tests below encode is: **there is no input for which a browser
refuses to start.** Every branch ends in an engine.
"""

import pytest

from connectonion.useful_tools.browser_tools import engine


def att(tier="pro", active=True):
    """The fields of an attestation this decision reads, and nothing else."""
    return {"tier": tier, "active": active}


# --- free is a product, not a refusal -------------------------------------


def test_no_attestation_at_all_still_browses():
    """No licence, no account, oo-api unreachable — all the same shape, and
    none of them may stop a free user from opening a browser. This is the
    behaviour a default install has today and must keep."""
    chosen, _ = engine.choose(attestation=None, onion_present=False)

    assert chosen == engine.PATCHRIGHT


def test_the_free_tier_is_told_what_unlocks_the_other_one():
    """The $5 signup grant is the common case: not broken, not yet enough."""
    chosen, note = engine.choose(attestation=att(tier="free"), onion_present=False)

    assert chosen == engine.PATCHRIGHT
    assert note is not None
    assert "10" in note, "the note has to name the number that unlocks it"


def test_the_note_is_absent_when_there_is_nothing_to_say():
    """A pro user driving the pro engine does not need a sales line on every
    command."""
    _, note = engine.choose(attestation=att(tier="pro"), onion_present=True)

    assert note is None


# --- paid gets what it paid for -------------------------------------------


def test_pro_with_the_binary_present_drives_it():
    chosen, _ = engine.choose(attestation=att(tier="pro"), onion_present=True)

    assert chosen == engine.ONION


def test_pro_without_the_binary_falls_back_rather_than_failing():
    """`onionwright` is not a dependency of connectonion — a fresh install has
    no paid binary on disk. A pro attestation with nothing to launch must not
    leave the customer worse off than a free one, so it falls back and says
    why."""
    chosen, note = engine.choose(attestation=att(tier="pro"), onion_present=False)

    assert chosen == engine.PATCHRIGHT
    assert note is not None


def test_an_inactive_pro_licence_still_browses():
    """Entitled to the engine, refused the session — an empty balance. The
    session refusal belongs to the licence layer; it is not a reason to leave
    someone without a browser."""
    chosen, _ = engine.choose(attestation=att(tier="pro", active=False),
                              onion_present=True)

    assert chosen == engine.PATCHRIGHT


# --- nothing gets through without an engine -------------------------------


@pytest.mark.parametrize("tier", ["free", "pro", "team", "mystery", None])
@pytest.mark.parametrize("active", [True, False])
@pytest.mark.parametrize("present", [True, False])
def test_every_combination_yields_an_engine(tier, active, present):
    """The property that matters more than any single branch: whatever the
    server says, whatever is on disk, a browser starts."""
    attestation = None if tier is None else att(tier=tier, active=active)

    chosen, _ = engine.choose(attestation=attestation, onion_present=present)

    assert chosen in (engine.ONION, engine.PATCHRIGHT)


def test_a_malformed_attestation_is_treated_as_no_licence():
    """A payload missing the fields we read is a server we do not understand.
    Guessing 'pro' would launch a binary we may not have; guessing 'free' just
    works."""
    chosen, _ = engine.choose(attestation={"unexpected": True}, onion_present=True)

    assert chosen == engine.PATCHRIGHT

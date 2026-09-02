"""The shipped oo skill must describe the protocol the 1.8 CLI actually has."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SKILL = ROOT / "connectonion" / "useful_skills" / "oo" / "SKILL.md"


def test_oo_is_a_single_file_skill_that_can_travel_through_co_announce():
    assert SKILL.is_file()
    assert sorted(path.name for path in SKILL.parent.iterdir()) == ["SKILL.md"]


def test_oo_names_only_the_current_publish_and_subscription_cli():
    body = SKILL.read_text(encoding="utf-8")

    for command in (
        "co setup --name <alias>",
        "co announce --dry-run",
        "co announce",
        "co sub sync <0xaddress>",
        "co sub list",
        "co sub remove <address-or-local-alias>",
    ):
        assert command in body

    for removed_surface in (
        "/api/relay/agents/",
        "/subscribe/accept",
        "subscriptions/pending",
        "from fanout import",
    ):
        assert removed_surface not in body


def test_oo_states_the_real_publication_and_trust_boundaries():
    body = SKILL.read_text(encoding="utf-8")

    assert "publish: false` does not make the metadata private" in body
    assert "Current distribution carries only `SKILL.md`" in body
    assert "There is no publisher accept/reject queue" in body
    assert "proves who published the bytes, not that the instructions" in body

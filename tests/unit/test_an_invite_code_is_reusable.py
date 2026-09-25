"""A project's CO_INVITE_CODE admits every identity that presents it, and the docs say so.

docs/concepts/onboarding.md said invite codes are made "in oo-frontend
dashboard" and verified "with oo-api (one-time use)". On 1.8.8b9 a re-tester
onboarded two identities with the one code `co create` wrote to .env: the code
is minted locally, checked by the agent itself, and reusable. An operator who
believes it is one-time hands it to one person and thinks the door has closed.
"""

from pathlib import Path

from connectonion.network.trust import tools
from connectonion.network.trust.trust_agent import TrustAgent

DOC = Path(__file__).resolve().parents[2] / "docs" / "concepts" / "onboarding.md"


def test_one_code_admits_two_identities(tmp_path, monkeypatch):
    co = tmp_path / ".co"
    co.mkdir()
    monkeypatch.setattr(tools, "_project_co_dir", lambda: co)
    monkeypatch.setenv("CO_INVITE_CODE", "ABCDE-FGHJK-LMNPQ")
    agent = TrustAgent("careful")

    first, second = "0x" + "1" * 64, "0x" + "2" * 64

    assert agent.verify_invite(first, "ABCDE-FGHJK-LMNPQ")
    assert agent.verify_invite(second, "ABCDE-FGHJK-LMNPQ")


def test_the_doc_describes_the_code_the_agent_actually_checks():
    text = DOC.read_text(encoding="utf-8")

    assert "one-time use" not in text
    assert "oo-frontend dashboard" not in text
    assert "CO_INVITE_CODE" in text and "reusable" in text

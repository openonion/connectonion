"""The private co rem travels only over an authenticated owner OIP session."""

import asyncio

from connectonion.network.host.ws_router.rem import handle_rem_read
from connectonion.rem.config import prepare
from connectonion.rem.files import Notebook


class Trust:
    def is_admin(self, address):
        return address == "owner"


def request(root, *, address="owner", authenticated=True):
    sent = []

    async def send(frame):
        sent.append(frame)

    conn = {"authenticated": authenticated, "signed_commands": True,
            "agent_address": address}
    routes = {"rem_root": root, "trust_agent": Trust()}
    asyncio.run(handle_rem_read({"request_id": "read-1"}, send, conn, routes))
    return sent[0]


def test_owner_reads_rem_html_but_other_peer_cannot(tmp_path):
    root = tmp_path / "rem"
    prepare(root)
    Notebook(root).write("projects/example.md", "# Example\n\nOwner-only note.")

    allowed = request(root)
    assert allowed["ok"] is True
    assert "Owner-only note." in allowed["html"]
    assert request(root, address="visitor")["ok"] is False
    assert request(root, authenticated=False)["ok"] is False


def test_missing_rem_is_not_created(tmp_path):
    root = tmp_path / "missing"
    assert request(root)["ok"] is False
    assert not root.exists()

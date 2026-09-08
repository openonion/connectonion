"""send_email carries the caller's chosen sender to the API (#1007).

The backend half (oo-api#150) verifies the address belongs to the caller and
answers 403 otherwise; the client's whole job is to put the choice in the
payload — and to leave the payload alone when no choice was made, so every
existing caller keeps the server-derived default.
"""

import sys
from unittest.mock import MagicMock, patch

import connectonion.useful_tools.send_email

_send_module = sys.modules["connectonion.useful_tools.send_email"]


def _sent_payload(monkeypatch, **kwargs):
    response = MagicMock(status_code=200)
    response.json.return_value = {"message_id": "m1", "from": "x@mail.openonion.ai"}
    monkeypatch.setenv("OPENONION_API_KEY", "tok")
    monkeypatch.setenv("AGENT_EMAIL", "x@mail.openonion.ai")
    with patch.object(_send_module.requests, "post", return_value=response) as post:
        result = _send_module.send_email("a@b.com", "s", "m", **kwargs)
    assert result["success"], result
    return post.call_args.kwargs["json"]


def test_a_chosen_from_address_reaches_the_api(monkeypatch):
    payload = _sent_payload(monkeypatch, from_address="rental@mail.openonion.ai")
    assert payload["from_address"] == "rental@mail.openonion.ai"


def test_no_choice_leaves_the_payload_unchanged(monkeypatch):
    """Omitted must mean absent — not null — so old servers see the old body."""
    payload = _sent_payload(monkeypatch)
    assert "from_address" not in payload

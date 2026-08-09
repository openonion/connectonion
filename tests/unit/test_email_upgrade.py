from unittest.mock import Mock

from typer.testing import CliRunner

from connectonion.cli.main import app


def test_keep_address_upgrade_sends_quota_only_request(monkeypatch):
    response = Mock()
    response.ok = True
    response.json.return_value = {
        "message": "Email upgraded to plus tier",
        "email_address": "rental@mail.openonion.ai",
        "emails_per_month": 10000,
        "balance": 0.0,
    }
    post = Mock(return_value=response)
    monkeypatch.setattr(
        "connectonion.cli.commands.email_commands.load_api_key",
        lambda: "test-token",
    )
    monkeypatch.setattr(
        "connectonion.cli.commands.email_commands.requests.post",
        post,
    )

    result = CliRunner().invoke(
        app,
        ["email", "upgrade", "plus", "--keep-address"],
    )

    assert result.exit_code == 0
    assert "rental@mail.openonion.ai" in result.stdout
    assert post.call_args.kwargs["json"] == {
        "tier": "plus",
        "keep_address": True,
    }

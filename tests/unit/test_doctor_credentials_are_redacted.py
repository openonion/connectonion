"""Credential diagnostics must be useful without becoming a secret leak."""

from types import SimpleNamespace

from connectonion.cli.commands.status_commands import _oauth_rows


def _oauth(rows, provider):
    return next(row for row in rows if row["provider"] == provider)


def test_oauth_reports_missing_connected_expired_and_refreshable(tmp_path):
    missing = _oauth_rows(project_dir=tmp_path, home=tmp_path, environ={}, now=100)
    assert _oauth(missing, "Google OAuth")["status"] == "missing"

    connected = _oauth_rows(
        project_dir=tmp_path,
        home=tmp_path,
        environ={
            "GOOGLE_ACCESS_TOKEN": "access-secret",
            "GOOGLE_TOKEN_EXPIRES_AT": "200",
            "GOOGLE_SCOPES": "gmail.send",
        },
        now=100,
    )
    assert _oauth(connected, "Google OAuth")["status"] == "connected"

    expired = _oauth_rows(
        project_dir=tmp_path,
        home=tmp_path,
        environ={
            "MICROSOFT_ACCESS_TOKEN": "expired-secret",
            "MICROSOFT_TOKEN_EXPIRES_AT": "50",
            "MICROSOFT_SCOPES": "Mail.Send",
        },
        now=100,
    )
    assert _oauth(expired, "Microsoft OAuth")["status"] == "expired"

    refreshable = _oauth_rows(
        project_dir=tmp_path,
        home=tmp_path,
        environ={
            "MICROSOFT_ACCESS_TOKEN": "expired-secret",
            "MICROSOFT_REFRESH_TOKEN": "refresh-secret",
            "MICROSOFT_TOKEN_EXPIRES_AT": "50",
            "MICROSOFT_SCOPES": "Mail.Send",
        },
        now=100,
    )
    assert _oauth(refreshable, "Microsoft OAuth")["status"] == "refresh available"

    incomplete = _oauth_rows(
        project_dir=tmp_path,
        home=tmp_path,
        environ={"GOOGLE_ACCESS_TOKEN": "access-without-scopes"},
        now=100,
    )
    assert _oauth(incomplete, "Google OAuth")["status"] == "incomplete (scopes missing)"

    invalid = _oauth_rows(
        project_dir=tmp_path,
        home=tmp_path,
        environ={
            "GOOGLE_ACCESS_TOKEN": "access-secret",
            "GOOGLE_SCOPES": "gmail.send",
            "GOOGLE_TOKEN_EXPIRES_AT": "not-a-date",
        },
        now=100,
    )
    assert _oauth(invalid, "Google OAuth")["status"] == "invalid expiry"


def test_oauth_reports_which_source_shadows_another_without_values(tmp_path):
    (tmp_path / ".env").write_text(
        "GOOGLE_ACCESS_TOKEN=project-secret\n"
        "GOOGLE_REFRESH_TOKEN=project-refresh\n",
        encoding="utf-8",
    )

    rows = _oauth_rows(
        project_dir=tmp_path,
        home=tmp_path / "home",
        environ={
            "GOOGLE_ACCESS_TOKEN": "process-secret",
            "GOOGLE_REFRESH_TOKEN": "process-refresh",
            "GOOGLE_SCOPES": "gmail.send",
        },
        now=100,
    )
    row = _oauth(rows, "Google OAuth")

    assert row["status"] == "conflict"
    assert "process environment (used)" in row["source"]
    assert "<project>/.env" in row["source"]
    rendered = repr(rows)
    for secret in ("process-secret", "process-refresh", "project-secret", "project-refresh"):
        assert secret not in rendered


def test_doctor_never_renders_an_api_key_preview(tmp_path, monkeypatch, capsys):
    from connectonion.cli.commands import doctor_commands
    from connectonion.useful_tools.browser_tools import browser as browser_module

    secret = "oo_live_abcdefghijklmnopqrstuvwxyz0123456789"
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("OPENONION_API_KEY", secret)
    monkeypatch.setattr(
        browser_module,
        "driver_stealth_status",
        lambda: ("missing", None, "patchright not installed"),
    )
    monkeypatch.setattr(
        doctor_commands.requests,
        "get",
        lambda *_args, **_kwargs: SimpleNamespace(status_code=200),
    )

    doctor_commands.handle_doctor()
    output = capsys.readouterr().out

    assert "OpenOnion" in output
    assert "configured" in output
    assert "Key Preview" not in output
    assert secret not in output
    assert secret[:20] not in output

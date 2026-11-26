"""Regression tests for Real-Data REM QA Audit backend fixes (#9, #26, #27, owner_record)."""

from __future__ import annotations

import json

import pytest

from connectonion.rem import keys, reader, translate, vault
from connectonion.rem.config import prepare, set_config
from connectonion.rem.files import Notebook, RemError, state_path, write_json
from connectonion.rem.page_review import validate
from connectonion.useful_tools import chrome_passwords, macos_keychain
from tests.unit.test_rem_keys import fake_vault  # noqa: F401
from tests.unit.test_rem_live_reader import call, host  # noqa: F401


def test_linux_keychain_import_returns_409_json_instead_of_500(host, monkeypatch):  # noqa: F811
    """[P0 Bug #9] POST /rem/keys/import {source: keychain} on Linux returns 409 JSON, never 500."""
    monkeypatch.setattr(vault.sys, "platform", "linux")
    cookie = f"co_rem={host.token}"
    status, headers, body = call(
        host.routes,
        "POST",
        "/rem/keys/import",
        cookie=cookie,
        body=json.dumps({"source": "keychain"}).encode(),
    )
    assert status == 409
    assert headers["content-type"].startswith("application/json")
    payload = json.loads(body)
    assert "not supported yet" in payload["error"] or "Mac" in payload["error"]


def test_macos_keychain_missing_security_binary_raises_keychain_error(monkeypatch):
    """[P0 Bug #9] macos_keychain catches missing security / non-darwin OS as KeychainError."""
    monkeypatch.setattr("sys.platform", "linux")
    with pytest.raises(macos_keychain.KeychainError, match="only available on a Mac"):
        macos_keychain.internet_passwords()

    def missing_binary(args, timeout):
        raise FileNotFoundError(2, "No such file or directory", "security")

    monkeypatch.setattr("sys.platform", "darwin")
    monkeypatch.setattr(macos_keychain, "run", missing_binary)
    with pytest.raises(macos_keychain.KeychainError, match="only available on a Mac"):
        macos_keychain.internet_passwords()
    with pytest.raises(macos_keychain.KeychainError, match="only available on a Mac"):
        macos_keychain.internet_password("mail.example.test", "me")


def test_linux_browser_password_import_explains_non_macos_instead_of_on_this_mac(host, monkeypatch):  # noqa: F811
    """[P0 Bug #9] Browser password import on Linux says why instead of 'on this Mac'."""
    monkeypatch.setattr("sys.platform", "linux")
    with pytest.raises(chrome_passwords.ChromeError) as exc_info:
        chrome_passwords.all_logins("chrome")
    assert "only available on a Mac" in str(exc_info.value)
    assert "on this Mac" not in str(exc_info.value)

    cookie = f"co_rem={host.token}"
    status, _, body = call(
        host.routes,
        "POST",
        "/rem/keys/import",
        cookie=cookie,
        body=json.dumps({"source": "chrome"}).encode(),
    )
    assert status == 409
    payload = json.loads(body)
    assert payload.get("reason") != "no_data"
    assert "on this Mac" not in payload["error"]
    assert "only available on a Mac" in payload["error"] or "not supported yet" in payload["error"]


def test_import_csv_on_unsupported_vault_refuses_even_when_zero_rows_have_passwords(host, monkeypatch):  # noqa: F811
    """[P1 Bug #26] Unsupported vault never returns 200 OK {filed: 0} on empty-password CSV rows."""
    monkeypatch.setattr(vault.sys, "platform", "linux")
    csv_no_passwords = "url,username,password\nhttps://example.test,me,\n"
    with pytest.raises(RemError, match="not supported yet"):
        keys.import_csv(host.root, csv_no_passwords)

    cookie = f"co_rem={host.token}"
    for csv_body in (csv_no_passwords, "name,username,password\n"):
        status, _, body = call(
            host.routes,
            "POST",
            "/rem/keys/import",
            cookie=cookie,
            body=json.dumps({"csv": csv_body}).encode(),
        )
        assert status == 409
        assert "not supported yet" in json.loads(body)["error"]


def test_import_csv_preserves_notes_under_notes_section_and_redacts_secret_shapes(tmp_path, fake_vault):  # noqa: F811
    """[P1 Bug #26] CSV notes column is wired into ## Notes while redacting secret-shaped tokens."""
    raw_api_key = "sk-" + "aB3dE5fG7hJ9kL1mN3pQ5rS7tU9vW1"
    raw_high_entropy = "Xk9#mQ2$vL7pR4wZ"
    export = (
        "url,username,password,extra,name\n"
        "https://billing.example.test,finance@example.test,Sup3r-Secr3t-1!,"
        "\"Shared with finance team; 2FA in authenticator app\",Billing Portal\n"
        "https://api.example.test,dev@example.test,Sup3r-Secr3t-2!,"
        f"\"Staging account; backup key {raw_api_key} and old pass {raw_high_entropy}\",API Console\n"
    )
    result = keys.import_csv(tmp_path, export)
    assert result == {"filed": 2, "skipped": 0}

    book = Notebook(tmp_path)
    billing_record = "keys/billing-portal-finance-example-test.md"
    billing_text = book.read(billing_record)
    assert "## Notes\nShared with finance team; 2FA in authenticator app" in billing_text
    assert "The secret is in this Mac's Keychain, not in this notebook." in billing_text
    assert keys.key_shape_errors(billing_record, billing_text) == []
    assert not [e for e in validate(billing_record, billing_text, "", []) if "vault" in e or "secret" in e]

    api_record = "keys/api-console-dev-example-test.md"
    api_text = book.read(api_record)
    assert "Staging account" in api_text
    assert raw_api_key not in api_text
    assert raw_high_entropy not in api_text
    assert "Sup3r-Secr3t" not in api_text
    assert keys.key_shape_errors(api_record, api_text) == []
    assert not [e for e in validate(api_record, api_text, "", []) if "vault" in e or "secret" in e]


def test_translate_readable_and_every_page_exclude_keys_and_unwritten_stubs_matching_reader(tmp_path, monkeypatch):
    """[P1 Bug #27] readable/every_page exclude keys/ and unwritten stubs so #lang-progress never jumps."""
    root = tmp_path / "rem"
    prepare(root)
    set_config(root, ["languages", "zh,en"])
    monkeypatch.setattr("connectonion.rem.service.mail_available", lambda kind: False)
    translate.IDLE_COUNTS.clear()
    translate.JOBS.clear()

    book = Notebook(root)
    # 2 written English/mixed prose pages + 1 written Chinese prose page = 3 written prose pages (2 untranslated)
    book.write(
        "people/mara-ostrowski.md",
        "# Mara Ostrowski\n\n## Facts\n- Role: partner at Fernhill [1]\n\n"
        "## Summary\nMara coordinates the Friday pilot numbers [1].\n\n"
        "## Sources\n- [1] gmail:m1 — intro\n",
    )
    book.write(
        "projects/fernhill-pilot.md",
        "# Fernhill pilot\n\n## Summary\n试点在三月启动 [1]。\n"
        "The second cohort still needs legal sign-off [1].\n\n"
        "## Sources\n- [1] codex:s1 — plan\n",
    )
    book.write(
        "people/lin-qiao.md",
        "# Lin Qiao\n\n## Facts\n- Role: 产品负责人 [1]\n\n"
        "## Summary\n跟进下周一的评审安排 [1]。\n\n"
        "## Sources\n- [1] gmail:m2 — thread\n",
    )

    # Unwritten mapped stubs (like the 1,230 mapped pages in real data)
    book.stub_person("people/stub-contact.md", "Stub Contact", ["stub@example.test"], email="stub@example.test")
    book.stub_org("orgs/stub-org.md", "Stub Org", ["stub.example.test"])
    book.stub_project("projects/stub-proj.md", "Stub Proj", ["/tmp/stub-proj"])
    book.stub_skill("skills/catalog/stub-skill.md", "stub-skill", "/tmp/SKILL.md", "Stub description")
    book.stub_topic("knowledge/stub-topic.md", "Stub Topic", ["stub"])

    # Bare 1-line title-only stubs (no prose body)
    book.write("people/bare-one-liner.md", "# Bare One Liner\n")
    book.write("knowledge/bare-topic.md", "# Bare Topic\n")

    # Vault metadata pages (keys/*.md — never prose for models)
    for idx in range(3):
        book.write(
            f"keys/site-{idx}.md",
            keys.page(f"site{idx}.example.test", f"u{idx}@example.test", purpose="login", key=f"site-{idx}"),
        )

    # Non-prose / activity categories excluded from #lang-progress
    book.write("sessions/s1.md", "# Session 1\n\n- Date: 2026-11-20\n\nReviewed tests.\n")
    book.write("logs/r1.md", "# Run log\n\nCompleted.\n")

    readable_pages = translate.readable(root)
    assert not [p for p in readable_pages if p.startswith("keys/")]
    every_pages = translate._every_page_records(root)
    assert not [p for p in every_pages if p.startswith("keys/")]
    assert "people/stub-contact.md" not in every_pages
    assert "orgs/stub-org.md" not in every_pages
    assert "projects/stub-proj.md" not in every_pages
    assert "skills/catalog/stub-skill.md" not in every_pages
    assert "knowledge/stub-topic.md" not in every_pages

    backlog_pages = translate.backlog(root, "zh")
    assert not [p for p in backlog_pages if p.startswith("keys/")]

    status = translate.every_page(root, "status", "zh")
    shell = reader.snapshot(root, local=True, today=True)
    full = reader.snapshot(root, local=True, today=False)

    assert status["total"] == 3
    assert status["done"] == 1
    assert status["total"] - status["done"] == 2
    assert shell["written_count"] == full["written_count"] == status["total"] == 3
    assert shell["untranslated_count"] == full["untranslated_count"] == status["total"] - status["done"] == 2


def test_owner_record_accepts_records_and_matches_cited_or_curly_apostrophe_owner_marker(tmp_path, monkeypatch):
    """Owner fallback resolves '- How we know them: This is the owner’s page [6]' with or without map.json."""
    root = tmp_path / "rem"
    prepare(root)
    monkeypatch.setattr("connectonion.rem.service.mail_available", lambda kind: False)
    write_json(state_path(root, "map.json"), {"owner": {}})

    book = Notebook(root)
    book.write(
        "people/alice-chen.md",
        "# Alice Chen\n\n## Facts\n- Email: alice@example.test\n- How we know them: Colleague [1]\n",
    )
    book.write(
        "people/changxing-owner.md",
        "# Changxing\n\n## Facts\n- Email: owner@example.test\n"
        "- How we know them: This is the owner’s page [6]\n\n"
        "## Sources\n- [6] codex:s1 — profile\n",
    )

    records = [
        {"path": "people/alice-chen.md", "category": "people", "text": book.read("people/alice-chen.md")},
        {"path": "people/changxing-owner.md", "category": "people", "text": book.read("people/changxing-owner.md")},
    ]
    assert reader.owner_record(root, records) == "people/changxing-owner.md"
    assert reader.owner_record(root) == "people/changxing-owner.md"
    assert reader.snapshot(root, local=True)["owner"] == "people/changxing-owner.md"

    # Also verify bolded label and multiple citations without touching disk again
    in_memory = [
        {
            "path": "people/self-page.md",
            "category": "people",
            "text": "# Casey\n\n## Facts\n- **How we know them**: This is the owner's page. [1][6]\n",
        }
    ]
    assert reader.owner_record(root, in_memory) == "people/self-page.md"

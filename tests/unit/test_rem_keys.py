"""Keys (#3137): a page says what a secret is; the OS vault keeps its value. Every test uses a fake vault."""
import json
import subprocess

import pytest

from connectonion.rem import keys, vault
from connectonion.rem.files import Notebook, RemError
from connectonion.rem.page_review import validate
from tests.unit.test_rem_live_reader import call, host  # noqa: F401

SECRET = "Tr0ub4dor&3-horse-Battery"


@pytest.fixture
def fake_vault(monkeypatch):
    """A Keychain in a dict, behind the one place vault starts a process; it records every command it saw."""
    store, seen = {}, []

    def run(args):
        seen.append(args)
        service = args[args.index("-s") + 1]
        if args[1] == "add-generic-password":
            store[service] = args[args.index("-w") + 1]
            return subprocess.CompletedProcess(args, 0, "", "")
        if args[1] == "find-generic-password":
            if service not in store:
                return subprocess.CompletedProcess(args, vault.NOT_FOUND, "", "not found")
            return subprocess.CompletedProcess(args, 0, store[service] + "\n" if "-w" in args else "", "")
        if args[1] == "delete-generic-password":
            return subprocess.CompletedProcess(args, 0 if store.pop(service, None) else vault.NOT_FOUND, "", "")
        raise AssertionError(args)

    monkeypatch.setattr(vault, "RUN", run)
    monkeypatch.setattr(vault.sys, "platform", "darwin")
    return store, seen


def test_adding_a_key_puts_the_value_in_the_vault_and_only_its_facts_in_the_page(tmp_path, fake_vault):
    store, _ = fake_vault
    record = keys.add(tmp_path, "OpenAI", "me@example.test", SECRET, purpose="REM translation", link="https://platform.example/keys?t=abc")
    assert record == "keys/openai-me-example-test.md"
    text = Notebook(tmp_path).read(record)
    assert SECRET not in text and "t=abc" not in text  # the value never, and no token from a URL's query
    assert "- Service: OpenAI" in text and "- Account: me@example.test" in text and "- Purpose: REM translation" in text
    assert "- Vault: macOS Keychain (co-rem:openai-me-example-test)" in text
    assert store == {"co-rem:openai-me-example-test": SECRET}
    assert keys.reveal(tmp_path, record) == SECRET


def test_a_reveal_is_refused_for_anything_but_an_existing_keys_page(tmp_path, fake_vault):
    for record in ("people/mara.md", "keys/../people/mara.md", "keys/missing.md", ""):
        with pytest.raises(RemError):
            keys.reveal(tmp_path, record)


def test_off_macos_the_vault_says_so_instead_of_writing_anywhere(tmp_path, monkeypatch):
    monkeypatch.setattr(vault.sys, "platform", "linux")
    monkeypatch.setattr(vault, "RUN", lambda args: pytest.fail("no process on an unsupported system"))
    with pytest.raises(RemError, match="not supported yet"):
        keys.add(tmp_path, "GitHub", "me", SECRET)
    assert not (tmp_path / "keys").exists()


def test_a_password_export_files_every_row_and_reports_counts_only(tmp_path, fake_vault):
    store, _ = fake_vault
    lastpass = ("url,username,password,totp,extra,name,grouping,fav\n"
                "https://github.com/login,me,ghp-like-Secret-1A,,,GitHub,,0\n"
                "https://bank.example/,me@bank,Bank-Pa55-word!,,,,,0\n"
                ",nobody,,,,Empty,,0\n")
    assert keys.import_csv(tmp_path, lastpass) == {"filed": 2, "skipped": 1}
    assert sorted(p.name for p in (tmp_path / "keys").iterdir()) == ["bank-example-me-bank.md", "github-me.md"]
    assert set(store.values()) == {"ghp-like-Secret-1A", "Bank-Pa55-word!"}
    for page in (tmp_path / "keys").iterdir():
        assert "Secret-1A" not in page.read_text() and "Pa55" not in page.read_text()
    with pytest.raises(RemError, match="password export"):
        keys.import_csv(tmp_path, "a,b\n1,2\n")


@pytest.mark.parametrize("line", ["- Notes: sk-" + "a" * 32, "- Account: AKIA" + "A" * 16,
                                  "-----BEGIN OPENSSH PRIVATE KEY-----", "- Password: Xk9#mQ2$vL7pR4wZ"])
def test_review_refuses_a_keys_page_that_carries_a_secret(line):
    candidate = keys.page("Service", "me", key="service-me").replace("## Notes", line + "\n\n## Notes")
    assert any("vault" in error for error in validate("keys/service-me.md", candidate, "", []))


def test_review_lets_a_plain_keys_page_through():
    candidate = keys.page("GitHub", "me@example.test", purpose="push to openonion", key="github-me-example-test")
    assert not [error for error in validate("keys/github-me-example-test.md", candidate, "", []) if "vault" in error or "secret" in error]


def test_the_host_files_and_reveals_keys_only_for_this_computer_with_the_page_cookie(host, fake_vault):  # noqa: F811
    cookie = f"co_rem={host.token}"
    add = json.dumps({"service": "Stripe", "account": "billing", "secret": SECRET, "purpose": "invoices"}).encode()
    assert call(host.routes, "POST", "/rem/keys/add", body=add)[0] == 401  # no cookie
    assert call(host.routes, "POST", "/rem/keys/add", cookie=cookie, body=add, client="10.0.0.9")[0] == 404  # not loopback
    status, _, body = call(host.routes, "POST", "/rem/keys/add", cookie=cookie, body=add)
    assert status == 200 and json.loads(body) == {"page": "keys/stripe-billing.md"}
    status, _, body = call(host.routes, "POST", "/rem/keys/reveal", cookie=cookie, body=json.dumps({"page": "keys/stripe-billing.md"}).encode())
    assert status == 200 and json.loads(body) == {"secret": SECRET}
    status, _, body = call(host.routes, "POST", "/rem/keys/reveal", cookie=cookie, body=json.dumps({"page": "people/alice-chen.md"}).encode())
    assert status == 409 and SECRET not in body
    status, _, body = call(host.routes, "POST", "/rem/keys/import", cookie=cookie,
                           body=json.dumps({"csv": "name,username,password\nNAS,admin,N4s-Adm1n-pass\n"}).encode())
    assert status == 200 and json.loads(body) == {"filed": 1, "skipped": 0}

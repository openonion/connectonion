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


# ---- #3305: import that says why it did not run, the macOS login keychain, and co's own keys.env names ----

def test_an_import_outside_the_owners_session_refuses_before_any_prompt(tmp_path, fake_vault, monkeypatch):
    from connectonion.rem import live_host
    from connectonion.useful_tools import chrome_passwords
    monkeypatch.setattr(live_host, "launch_session", lambda: "Background")
    monkeypatch.setattr(chrome_passwords, "all_logins", lambda browser: pytest.fail("read a vault it could not unlock"))
    with pytest.raises(keys.KeyImportError) as caught:
        keys.import_browser(tmp_path, "chrome")
    assert caught.value.code == "no_gui" and "co rem open" in str(caught.value)


def test_a_declined_keychain_prompt_says_declined_not_not_installed(tmp_path, fake_vault, monkeypatch):
    from connectonion.rem import live_host
    from connectonion.useful_tools import chrome_passwords, macos_keychain
    monkeypatch.setattr(live_host, "launch_session", lambda: "Aqua")
    monkeypatch.setattr(chrome_passwords, "login_data_paths", lambda browser: [tmp_path / "Login Data"])
    monkeypatch.setattr(macos_keychain, "run", lambda args, timeout: subprocess.CompletedProcess(
        args, 128, "", "security: SecKeychainItemCopyContent: User canceled the operation."))
    with pytest.raises(keys.KeyImportError) as caught:
        keys.import_browser(tmp_path, "chrome")
    assert caught.value.code == "denied"


def _keychain(monkeypatch, values):
    """A login keychain of two internet passwords; `values` answers each read in order (a str or a failure)."""
    from connectonion.useful_tools import macos_keychain
    from tests.unit.test_macos_keychain import DUMP
    answers = iter(values)

    def run(args, timeout):
        if args[1] == "dump-keychain":
            return subprocess.CompletedProcess(args, 0, DUMP, "")
        answer = next(answers)
        return (subprocess.CompletedProcess(args, 0, answer + "\n", "") if not isinstance(answer, tuple)
                else subprocess.CompletedProcess(args, answer[0], "", answer[1]))
    monkeypatch.setattr(macos_keychain, "run", run)


def test_the_macos_keychain_files_each_password_after_its_prompt_and_names_sites_only(tmp_path, fake_vault, monkeypatch):
    from connectonion.rem import live_host
    monkeypatch.setattr(live_host, "launch_session", lambda: "Aqua")
    store, _ = fake_vault
    _keychain(monkeypatch, ["Mail-pass-1", "Nas-pass-2"])
    result = keys.import_keychain(tmp_path)
    assert result == {"filed": 2, "skipped": 0, "sites": ["mail.example.test", "nas.example.test"]}
    assert sorted(store.values()) == ["Mail-pass-1", "Nas-pass-2"]
    assert all("pass" not in Notebook(tmp_path).read(r) for r in Notebook(tmp_path).list("keys"))


def test_a_declined_prompt_mid_way_keeps_what_was_filed_and_says_why_it_stopped(tmp_path, fake_vault, monkeypatch):
    from connectonion.rem import live_host
    monkeypatch.setattr(live_host, "launch_session", lambda: "Aqua")
    _keychain(monkeypatch, ["Mail-pass-1", (128, "User canceled the operation.")])
    result = keys.import_keychain(tmp_path)
    assert result == {"filed": 1, "skipped": 0, "sites": ["mail.example.test"], "stopped": "denied"}


def test_keys_env_names_are_listed_and_never_a_value(tmp_path):
    env = tmp_path / "keys.env"
    env.write_text("OPENAI_API_KEY=sk-not-a-real-key-123\nOPENONION_API_KEY='oo-also-fake'\n# a comment\nAGENT_CONFIG_PATH=/x\n")
    result = keys.env_names(env)
    assert result["names"] == ["OPENAI_API_KEY", "OPENONION_API_KEY"]
    assert "sk-not" not in json.dumps(result) and "oo-also" not in json.dumps(result)
    assert keys.env_names(tmp_path / "missing.env")["names"] == []


def test_a_broken_keys_env_says_which_line_without_its_value(tmp_path):
    env = tmp_path / "keys.env"
    env.write_text("GOOD=fine\nthis line is not a binding 'sk-oops\n")
    result = keys.env_names(env)
    assert result["names"] == [] and "line" in result["error"] and "sk-oops" not in result["error"]


def test_the_host_returns_the_reason_and_lists_keys_env_names(host, fake_vault, monkeypatch, tmp_path):  # noqa: F811
    from connectonion.rem import live_host
    cookie = f"co_rem={host.token}"
    monkeypatch.setattr(live_host, "launch_session", lambda: "Background")
    status, _, body = call(host.routes, "POST", "/rem/keys/import", cookie=cookie, body=json.dumps({"source": "chrome"}).encode())
    assert status == 409 and json.loads(body)["reason"] == "no_gui"
    status, _, body = call(host.routes, "POST", "/rem/keys/import", cookie=cookie, body=json.dumps({"source": "keychain"}).encode())
    assert status == 409 and json.loads(body)["reason"] == "no_gui"
    env = tmp_path / "keys.env"
    env.write_text("OPENAI_API_KEY=sk-not-a-real-key-123\n")
    monkeypatch.setattr("connectonion.environment.selected_env_file", lambda: env)
    assert call(host.routes, "POST", "/rem/keys/env", body=b"{}")[0] == 401  # the page's cookie, as for every key route
    status, _, body = call(host.routes, "POST", "/rem/keys/env", cookie=cookie, body=b"{}")
    assert status == 200 and json.loads(body)["names"] == ["OPENAI_API_KEY"] and "sk-not" not in body

"""A value saved with `co env set NAME value --secret` reaches the command that needs it.

`co env set --help` shows `co env set GITHUB_TOKEN ghp_... --secret`, and the
encrypted store worked: `co env get` opened it. Nothing else did. Every command
read os.environ, which holds the process and keys.env and never the store, so a
key saved exactly as the help shows was "not set" to the command it was for.
The first commands to say "save it with --secret" (co linear, co canny) each
grew a private copy of `co env get`'s lookup to work around that.
"""

import pytest

from connectonion import address, secret_store
from connectonion.environment import setting

PHRASE = "legal winner thank year wave sausage worth useful legal winner thank yellow"


@pytest.fixture
def co_dir(tmp_path, monkeypatch):
    keys = tmp_path / "keys"
    keys.mkdir()
    (keys / "agent.key").write_bytes(bytes(address.recover(PHRASE)["signing_key"]))
    monkeypatch.setenv("AGENT_CONFIG_PATH", str(tmp_path))
    monkeypatch.delenv("DEMO_API_KEY", raising=False)
    return tmp_path


def test_a_value_saved_with_secret_is_found(co_dir):
    secret_store.put(co_dir, "DEMO_API_KEY", "from-the-store")

    assert setting("DEMO_API_KEY") == "from-the-store"


def test_the_process_still_wins(co_dir, monkeypatch):
    secret_store.put(co_dir, "DEMO_API_KEY", "from-the-store")
    monkeypatch.setenv("DEMO_API_KEY", "from-the-shell")

    assert setting("DEMO_API_KEY") == "from-the-shell"


def test_a_name_saved_nowhere_is_none(co_dir):
    assert setting("DEMO_API_KEY") is None


def test_a_stored_value_that_will_not_open_says_so(co_dir):
    secret_store.put(co_dir, "DEMO_API_KEY", "from-the-store")
    (co_dir / "keys" / "agent.key").write_bytes(bytes(address.recover(
        "letter advice cage absurd amount doctor acoustic avoid letter advice cage above")["signing_key"]))

    with pytest.raises(secret_store.Undecryptable):
        setting("DEMO_API_KEY")

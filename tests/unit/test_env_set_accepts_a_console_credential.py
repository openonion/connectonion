"""`co env set` has a door for the one legitimate hand-typed app credential.

Until now the two commands pointed at each other with nothing in between:

    co auth lark            → the tenant's launcher drops the code, so the scan
                              can never complete (#1537)
    co env set LARK_APP_SECRET → "is written by co auth lark … Next: co auth lark"

The refusal was right while `co auth` always worked — there is no API that hands
out an app secret, so a typed one had no checkable source. It is wrong when
`co auth` *cannot* work for a tenant, because then the Developer Console is the
only source there is, and refusing it leaves no way through at all.

So the door is named rather than removed: `--from-console` says where the value
came from. Two properties matter as much as the door itself —

  * the default is unchanged, so a value pasted from the wrong place is still
    caught for everyone whose `co auth` works;
  * the flag opens exactly the app credentials. A flag that silently does
    nothing on other keys teaches people it is a general override, and the next
    person tries it on the account fields, which are one record and must never
    be set a field at a time.
"""

import pytest
import typer

from connectonion.cli.commands import env_commands


class Rig:
    """The env file plus whatever the command said about it.

    `_fail` routes through `print_tip`, so a fixture that stubbed print_tip to a
    no-op would hide the very messages these tests assert on. It records.
    """

    def __init__(self, path, said):
        self.path = path
        self.said = said

    def read_text(self):
        return self.path.read_text()

    @property
    def told(self):
        return "\n".join(self.said)


@pytest.fixture
def env_file(tmp_path, monkeypatch):
    path = tmp_path / "keys.env"
    path.write_text("EXISTING=keep-me\n")
    monkeypatch.setattr(env_commands, "selected_env_file", lambda: path)
    monkeypatch.setattr(env_commands, "_writable_file", lambda: path)
    monkeypatch.setattr(env_commands, "process_environment", dict)
    said = []
    monkeypatch.setattr(
        env_commands, "print_tip", lambda msg="", *a, **k: said.append(str(msg))
    )
    return Rig(path, said)


@pytest.mark.parametrize(
    "key", ["LARK_APP_SECRET", "LARK_APP_ID", "FEISHU_APP_SECRET", "FEISHU_APP_ID"]
)
def test_an_app_credential_is_still_refused_by_default(env_file, key):
    with pytest.raises(typer.Exit):
        env_commands.handle_env_set(key, "value-from-somewhere")

    assert "keep-me" in env_file.read_text()
    assert key not in env_file.read_text()


def test_the_refusal_names_the_door_as_well_as_the_main_road(env_file):
    """It used to end at `Next: co auth lark` with no way through at all.

    It must still name `--from-console`, because someone who already keeps an
    application in the Developer Console has a real credential and nowhere to
    put it.
    """
    with pytest.raises(typer.Exit):
        env_commands.handle_env_set("LARK_APP_SECRET", "x")

    out = env_file.told
    assert "--from-console" in out
    assert "Developer Console" in out
    assert "co auth lark" in out, "the main road is still the main road"


def test_the_refusal_does_not_imply_co_auth_is_broken(env_file):
    """1.8.5b9 justified this door with "if co auth cannot create an application
    for your tenant — the scan page says 'Link expired' on a code that is still
    alive".

    That was the wrong cause and it is fixed (#1537). Leaving the sentence would
    tell every reader that the command they are being sent to may not work.
    """
    with pytest.raises(typer.Exit):
        env_commands.handle_env_set("LARK_APP_SECRET", "x")

    out = env_file.told
    assert "Link expired" not in out
    assert "cannot create an application" not in out
    assert "data-residency" not in out


@pytest.mark.parametrize("key", ["LARK_APP_SECRET", "FEISHU_APP_ID"])
def test_from_console_writes_the_credential(env_file, key):
    env_commands.handle_env_set(key, "from-the-console", from_console=True)

    body = env_file.read_text()
    assert f"{key}=from-the-console" in body
    assert "EXISTING=keep-me" in body, "the rest of the file is untouched"


def test_from_console_is_refused_on_anything_else(env_file):
    """Not a general override. The account fields in particular stay shut."""
    with pytest.raises(typer.Exit):
        env_commands.handle_env_set("OPENAI_API_KEY", "sk-x", from_console=True)

    out = env_file.told
    assert "--from-console is for" in out
    assert "OPENAI_API_KEY=" not in env_file.read_text()


def test_the_error_for_a_wrong_key_lists_the_right_ones(env_file):
    with pytest.raises(typer.Exit):
        env_commands.handle_env_set("SOMETHING_ELSE", "v", from_console=True)

    out = env_file.told
    assert "LARK_APP_SECRET" in out and "FEISHU_APP_ID" in out


def test_an_ordinary_setting_is_unaffected(env_file):
    env_commands.handle_env_set("OPENAI_API_KEY", "sk-ordinary")

    assert "OPENAI_API_KEY=sk-ordinary" in env_file.read_text()

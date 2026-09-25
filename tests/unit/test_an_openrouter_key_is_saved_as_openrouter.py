"""An OpenRouter key given with --key ends up under OPENROUTER_API_KEY (#1341).

OpenRouter keys start `sk-or-`, which also starts `sk-`, so the generic OpenAI
check used to claim them and the key was written as OPENAI_API_KEY. Detection
was fixed in 09032ff3 and `co init --key` has had a test since. `co create
--key` had none, and the gap it hid was worse than a wrong name: once
~/.co/keys.env had anything in it — which it does after the first `co auth` —
create copied that file and dropped the key the user had just typed.
"""

from pathlib import Path

from dotenv import dotenv_values

KEY = "sk-or-v1-test-key"


def _seed_keys_env():
    home = Path.home()  # conftest points HOME at a tmp dir
    (home / ".co").mkdir(parents=True, exist_ok=True)
    # OPENONION_API_KEY present means create does not try to authenticate.
    (home / ".co" / "keys.env").write_text(
        "OPENONION_API_KEY=token\nAGENT_ADDRESS=0xabc\n"
    )


def test_create_writes_the_key_it_was_given(tmp_path, monkeypatch):
    _seed_keys_env()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "connectonion.cli.commands.create.check_environment_for_api_keys",
        lambda: None,
    )
    from connectonion.cli.commands.create import handle_create

    handle_create(name="router", ai=False, key=KEY, template="co-ai",
                  description=None, yes=True, parent_dir=tmp_path)

    env = dotenv_values(tmp_path / "router" / ".env")
    assert env.get("OPENROUTER_API_KEY") == KEY, env
    assert "OPENAI_API_KEY" not in env
    # What keys.env already carried is still inherited.
    assert env["OPENONION_API_KEY"] == "token"


def test_init_writes_the_key_it_was_given(tmp_path, monkeypatch):
    _seed_keys_env()
    project = tmp_path / "project"
    project.mkdir()
    monkeypatch.chdir(project)
    monkeypatch.setattr(
        "connectonion.cli.commands.init.check_environment_for_api_keys",
        lambda: None,
    )
    from connectonion.cli.commands.init import handle_init

    handle_init(ai=False, key=KEY, template="none", description=None,
                yes=True, force=True)

    env = dotenv_values(project / ".env")
    assert env.get("OPENROUTER_API_KEY") == KEY, env
    assert "OPENAI_API_KEY" not in env

"""What a new project inherits from the machine that made it.

`co init` appended every entry of ~/.co/keys.env to the new project's .env:

    for key, line in global_keys.items():
        if key not in existing_keys:
            keys_to_add.append(line)

That file accumulates. On a machine where `co gmail auth` and `co outlook auth`
have run it holds live OAuth *refresh* tokens for both. Observed from a clean
install of the wheel, in an empty directory:

    GOOGLE_ACCESS_TOKEN      MICROSOFT_ACCESS_TOKEN
    GOOGLE_REFRESH_TOKEN     MICROSOFT_REFRESH_TOKEN
    GOOGLE_EMAIL             MICROSOFT_EMAIL

A .gitignore is written only when the directory is already a git repo, so
`co init` followed by `git init` leaves them untracked-but-not-ignored, one
`git add .` from publication. `co deploy` also delivers .env to the server,
which puts a personal Gmail refresh token on a box built for an unrelated agent.

The identity keys are a different case and are left alone: AGENT_ADDRESS,
OPENONION_API_KEY, AGENT_EMAIL and IS_EMAIL_ACTIVE are propagated on purpose —
the code says so, "co reset must propagate" — and that is a design decision, not
an oversight.

`co create` built the same file by a different route and had the same hole. Both
now ask the same question.
"""

import pytest

from connectonion.cli.commands.env_inheritance import is_personal_account_credential


class TestSomeonesOwnAccountsStayBehind:

    @pytest.mark.parametrize("key", [
        "GOOGLE_ACCESS_TOKEN", "GOOGLE_REFRESH_TOKEN", "GOOGLE_EMAIL",
        "GOOGLE_SCOPES", "GOOGLE_TOKEN_EXPIRES_AT",
        "MICROSOFT_ACCESS_TOKEN", "MICROSOFT_REFRESH_TOKEN",
        "MICROSOFT_EMAIL", "MICROSOFT_SCOPES", "MICROSOFT_TOKEN_EXPIRES_AT",
    ])
    def test_it_is_recognised(self, key):
        assert is_personal_account_credential(key), (
            f"{key} would be written into every new project on this machine"
        )

    def test_a_field_added_next_to_them_later_is_covered(self):
        """A prefix rule, so nobody has to remember to extend a list."""
        assert is_personal_account_credential("GOOGLE_ID_TOKEN")
        assert is_personal_account_credential("MICROSOFT_TENANT_ID")


class TestWhatANewProjectStillGets:

    @pytest.mark.parametrize("key", [
        "OPENONION_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY",
        "ANTHROPIC_API_KEY", "GROQ_API_KEY",
    ])
    def test_provider_keys_are_inherited(self, key):
        assert not is_personal_account_credential(key)

    @pytest.mark.parametrize("key", ["AGENT_ADDRESS", "AGENT_EMAIL",
                                     "IS_EMAIL_ACTIVE"])
    def test_identity_keys_are_left_alone(self, key):
        """Propagated on purpose — see IDENTITY_KEYS in init.py. Not this
        change's business to reverse."""
        assert not is_personal_account_credential(key)

    def test_the_invite_code_is_not_swept_up(self):
        assert not is_personal_account_credential("CO_INVITE_CODE")


class TestBothCommandsAskTheSameQuestion:
    """`co init` and `co create` build this file by different routes. Only one
    of them was fixed on the first attempt, and the real CLI showed it — the
    unit tests were green while a real `co init` still wrote the tokens."""

    @pytest.mark.parametrize("module", [
        "connectonion.cli.commands.init",
        "connectonion.cli.commands.create",
    ])
    def test_it_consults_the_shared_rule(self, module):
        import importlib
        import inspect

        source = inspect.getsource(importlib.import_module(module))
        assert "is_personal_account_credential" in source, (
            f"{module} builds a project .env without asking"
        )

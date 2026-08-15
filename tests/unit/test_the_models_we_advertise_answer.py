"""What a new user is told to spend their free tokens on must work.

After `co auth` verifies a GitHub star, the CLI grants 100k tokens and prints the
managed models to spend them on. Two of the four did not work:

    co/gemini-3.6-flash        ok
    co/gemini-3-pro-preview    404  This model is no longer available
    co/gpt-5                   403  paid_account_required
    co/claude-sonnet-4         403  paid_account_required

Google has retired the second. The other two are real and reachable, but the
backend refuses them without purchased credits:

    "Your free $5 credits work with Google-routed models. Purchase credits to
    unlock all models"

Free credits are precisely what the surrounding message is handing out, so the
list has to be what a free account can call. It now is, with the paid ones named
on a separate line rather than dropped, since they are real.

The list was also written out twice, in two branches of the same auth flow, with
both copies naming the retired model — the shape that has caused most of this
release's bugs. It is now one tuple, and this asserts against that tuple rather
than against a copy of it.
"""

import pytest

from connectonion.cli.commands.project_cmd_lib import MANAGED_MODELS, PAID_MODELS


RETIRED = ("gemini-3-pro-preview", "gemini-2.0-flash-exp", "gemini-2.0-flash-thinking-exp")


class TestNothingRetiredIsAdvertised:

    @pytest.mark.parametrize("dead", RETIRED)
    def test_it_is_not_on_the_list(self, dead):
        assert f"co/{dead}" not in MANAGED_MODELS


class TestTheListIsUsable:

    def test_it_is_not_empty(self):
        assert len(MANAGED_MODELS) >= 3

    def test_every_entry_is_a_managed_name(self):
        assert all(m.startswith("co/") for m in MANAGED_MODELS)

    def test_the_default_model_is_offered(self):
        # The default is what a new project is created with, so it has to be
        # one of the names the same flow tells the user about.
        from connectonion.core.usage import DEFAULT_MODEL

        assert DEFAULT_MODEL in MANAGED_MODELS

    def test_there_is_only_one_copy_of_the_list(self):
        """Both call sites must render the tuple, not their own literal."""
        import inspect

        from connectonion.cli.commands import project_cmd_lib

        source = inspect.getsource(project_cmd_lib)
        # The only place a bare "  • co/..." string may be built is the helper.
        assert source.count('console.print(f"  • {model}")') == 1
        assert 'console.print("  • co/' not in source


@pytest.mark.network
class TestEveryAdvertisedModelAnswers:
    """One real managed call per advertised name, as a new user.

    The identity is freshly generated on purpose. Running this against the
    machine's own account is what hid half the problem: that account has a
    funded balance, so co/gpt-5 answered for me and 403'd for everyone this
    message is written for.
    """

    @pytest.fixture(scope="class")
    def free_account_token(self):
        import time

        import requests
        from nacl.encoding import HexEncoder
        from nacl.signing import SigningKey

        signing_key = SigningKey.generate()
        public_key = "0x" + signing_key.verify_key.encode(encoder=HexEncoder).decode()
        message = f"ConnectOnion-Auth-{public_key}-{int(time.time())}"
        response = requests.post(
            "https://oo.openonion.ai/api/v1/auth",
            json={
                "public_key": public_key,
                "message": message,
                "signature": signing_key.sign(message.encode()).signature.hex(),
            },
            timeout=15,
        )
        if response.status_code != 200:
            pytest.skip(f"could not open a fresh account: {response.status_code}")
        return response.json()["token"]

    @pytest.mark.parametrize("model", MANAGED_MODELS)
    def test_a_free_account_can_call_it(self, model, free_account_token):
        from connectonion.core.llm import OpenOnionLLM

        response = OpenOnionLLM(api_key=free_account_token, model=model).complete(
            [{"role": "user", "content": "Reply with the single word: ok"}]
        )

        assert response.content.strip()

    @pytest.mark.parametrize("model", PAID_MODELS)
    def test_a_paid_model_is_refused_for_the_stated_reason(
        self, model, free_account_token
    ):
        """If these start working on free credits, they belong on the main list.

        Asserts the type, not the backend's wording. This first checked for
        "paid_account_required" in the message, which passed only because the
        raw JSON was reaching the user — the thing PaidModelRequiredError was
        then added to stop. The two assertions contradicted each other and this
        is the one that was measuring the symptom.
        """
        from connectonion.core.exceptions import PaidModelRequiredError
        from connectonion.core.llm import OpenOnionLLM

        with pytest.raises(PaidModelRequiredError) as excinfo:
            OpenOnionLLM(api_key=free_account_token, model=model).complete(
                [{"role": "user", "content": "ok"}]
            )

        assert excinfo.value.model_requested == model.removeprefix("co/")

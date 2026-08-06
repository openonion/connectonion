"""What a new user is told to spend their free tokens on must work.

After `co auth` verifies a GitHub star, the CLI grants 100k tokens and prints the
managed models to spend them on. Two of the four did not work:

    co/gemini-3.6-flash        ok
    co/gemini-3-pro-preview    404  This model is no longer available
    co/gpt-5                   ok
    co/claude-sonnet-4         401  Anthropic API error (upstream credential)

so half of a brand-new user's first list is a dead end. The Claude 401 comes
from the managed backend's own upstream key and cannot be fixed here; it is
filed against oo-api. The retired Gemini model is ours to stop offering.

The list was also written out twice, in two branches of the same auth flow, with
both copies naming the retired model — the shape that has caused most of this
release's bugs. It is now one tuple, and this asserts against that tuple rather
than against a copy of it.
"""

import pytest

from connectonion.cli.commands.project_cmd_lib import MANAGED_MODELS


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
        # co/gemini-3.6-flash is what a new project is created with, so it has
        # to be one of the names the same flow tells the user about.
        assert "co/gemini-3.6-flash" in MANAGED_MODELS

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
    """One real managed call per advertised name."""

    @pytest.mark.parametrize("model", MANAGED_MODELS)
    def test_it_completes_a_call(self, model):
        from connectonion.core.llm import create_llm

        response = create_llm(model=model).complete(
            [{"role": "user", "content": "Reply with the single word: ok"}]
        )

        assert response.content.strip()

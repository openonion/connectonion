"""A model name in the docs has to be one a reader can actually call (#726).

The docs recommended `gemini-3-pro-preview` in six files after Google retired
it. Both routes answer 404, so every copy-pasteable example naming it failed:

    gemini-3-pro-preview      404  "This model is no longer available"
    co/gemini-3-pro-preview   404  same, through the managed backend

`docs/concepts/agent.md` also had `Agent("bot", model="gemini-2.0-flash-exp")`,
retired as well, and `docs/api.md` listed `co/gemini-2.0-flash` and
`co/gemini-2.5-flash-lite` — one retired, one never in the registry.

Third docs-vs-code gap this release (#717, #724, this) and the worst of them,
because these lines are meant to be pasted and they fail at runtime rather than
merely misinform.

## Why this only checks for retired names

The first version asserted that every model name in the docs is one the package
routes or prices. It failed on correct documentation: `gpt-4o`,
`claude-3-5-sonnet` and friends were dropped from the price table in #603 with
routing deliberately left alone, so a doc naming them is right — the cost just
shows with a `~`. `claude-haiku-4-5` and `gpt-5-nano` route by prefix without
being curated at all, and the regex also picked up the words "claude" and
"gemini" out of prose.

A check that flags correct docs is worse than no check, so what is left is the
narrow thing that is actually true: a name known to be retired must not appear.
That is what would have caught #726, and it starts failing the moment a model
leaves MODEL_REGISTRY.

The names now in the docs were each verified with a real call on the route the
doc shows — direct for `gemini-*`, managed for `co/gemini-*`.
"""

from pathlib import Path

import pytest

from connectonion.core.llm import MODEL_REGISTRY


DOCS = Path(__file__).resolve().parents[2] / "docs"

RETIRED = ("gemini-3-pro-preview", "gemini-2.0-flash-exp",
           "gemini-2.0-flash-thinking-exp")


def _doc_files():
    return sorted(DOCS.rglob("*.md"))


class TestNoDocNamesARetiredModel:

    @pytest.mark.parametrize("retired", RETIRED)
    def test_it_is_gone_from_every_doc(self, retired):
        offenders = [
            str(f.relative_to(DOCS))
            for f in _doc_files()
            if retired in f.read_text(encoding="utf-8", errors="replace")
        ]

        assert offenders == [], f"{retired} answers 404; still named in {offenders}"


class TestTheRegistryIsStillTheSourceOfTruth:
    """If a model leaves the registry, the docs test above starts failing —
    which is the point, and is what did not happen last time."""

    def test_the_retired_ones_are_not_in_the_registry(self):
        assert not set(RETIRED) & set(MODEL_REGISTRY)

    def test_the_replacements_are(self):
        assert {"gemini-2.5-pro", "gemini-2.5-flash"} <= set(MODEL_REGISTRY)

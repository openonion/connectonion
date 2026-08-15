"""Which models this release still claims to support.

Anything released before 2025 is dropped: the price tables, the context
limits, the defaults built into the provider classes, and the names shown in
docs and templates. A version meant to be supported long-term should not carry
a price for a model nobody can call any more, and a default that names one is
worse than no default at all.

The tables are the enforceable part — a name in them is a claim that using it
will be costed correctly.
"""

import re

import pytest

from connectonion.core.usage import MODEL_CONTEXT_LIMITS, MODEL_PRICING

# Families the world shipped before 2025. Kept as prefixes rather than exact
# names because the dated variants are the ones that end up pinned in code.
BEFORE_2025 = (
    "gpt-4", "gpt-3.5",
    "o1-",
    "claude-3-5-", "claude-3-opus", "claude-3-sonnet", "claude-3-haiku",
    "gemini-1.5",
)


def _stale(names) -> list:
    return sorted(n for n in names
                  if any(n.startswith(p) for p in BEFORE_2025))


class TestTheTablesCarryNothingRetired:

    def test_pricing_has_no_pre_2025_model(self):
        assert _stale(MODEL_PRICING) == []

    def test_context_limits_have_no_pre_2025_model(self):
        assert _stale(MODEL_CONTEXT_LIMITS) == []

    def test_the_two_tables_still_agree(self):
        """A model priced but not sized, or the reverse, is a gap either way."""
        assert set(MODEL_PRICING) == set(MODEL_CONTEXT_LIMITS)


class TestNoDefaultNamesARetiredModel:
    """A default that names an unsupported model is worse than none: it is
    chosen for people who did not choose."""

    def _defaults_in(self, module_path: str) -> list:
        import inspect, importlib

        source = inspect.getsource(importlib.import_module(module_path))
        return re.findall(r'model:\s*str\s*=\s*"([^"]+)"', source)

    @pytest.mark.parametrize("module", [
        "connectonion.core.llm",
        "connectonion.network.trust.trust_agent",
    ])
    def test_no_constructor_defaults_to_one(self, module):
        stale = _stale(self._defaults_in(module))

        assert stale == [], f"{module} defaults to {stale}"


class TestWhatIsLeftIsStillUsable:

    def test_the_tables_are_not_empty(self):
        assert len(MODEL_PRICING) >= 8

    def test_the_project_default_is_priced(self):
        from connectonion.core.usage import is_estimated_price

        assert not is_estimated_price("co/gemini-3.7-flash")

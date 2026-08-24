"""Every provider client carries explicit network bounds (#1116).

A scheduled run froze mid-iteration with the upstream socket in CLOSE_WAIT —
the server had closed its side and the client sat in a read nothing bounded.
No error, no exit, killed by hand after 15 minutes.

The property these tests protect is not a number, it is visibility: no
provider client may be constructed on implicit SDK defaults. The connect
value doubles as the tripwire — the openai SDK's implicit default is 5s, so
an accidentally-unbounded client fails the assertion by value, not just by
style. (Confirmed red on the pre-patch code for every provider except
OpenOnionLLM, which had the bounds since the relay-blip fix.)
"""

import pytest

from connectonion.core import llm as llm_module
from connectonion.core.llm import (
    LLM_CONNECT_TIMEOUT_SECONDS,
    LLM_MAX_RETRIES,
    LLM_READ_TIMEOUT_SECONDS,
    LLMConnectionError,
    _network_bounds,
)

DUMMY_KEY = "sk-test-not-a-real-key"


def _provider_clients():
    """(name, constructed client, expected retries) for every provider."""
    return [
        ("OpenAILLM", llm_module.OpenAILLM(api_key=DUMMY_KEY).client, LLM_MAX_RETRIES),
        ("AnthropicLLM", llm_module.AnthropicLLM(api_key=DUMMY_KEY).client, LLM_MAX_RETRIES),
        ("GeminiLLM", llm_module.GeminiLLM(api_key=DUMMY_KEY).client, LLM_MAX_RETRIES),
        ("GroqLLM", llm_module.GroqLLM(api_key=DUMMY_KEY).client, LLM_MAX_RETRIES),
        ("GrokLLM", llm_module.GrokLLM(api_key=DUMMY_KEY).client, LLM_MAX_RETRIES),
        ("MistralLLM", llm_module.MistralLLM(api_key=DUMMY_KEY).client, LLM_MAX_RETRIES),
        ("OpenRouterLLM", llm_module.OpenRouterLLM(api_key=DUMMY_KEY).client, LLM_MAX_RETRIES),
        # Deliberately 5: transient relay blips used to kill whole agent runs.
        ("OpenOnionLLM", llm_module.OpenOnionLLM(api_key=DUMMY_KEY).client, 5),
    ]


def test_every_provider_client_has_the_explicit_bounds():
    """The whole point of #1116 in one loop.

    One loop rather than parametrize so a new provider that forgets the
    bounds fails here the moment someone adds it to the list — and the
    list itself is checked against the module below, so it cannot silently
    go stale either.
    """
    for name, client, expected_retries in _provider_clients():
        timeout = client.timeout
        assert timeout.connect == LLM_CONNECT_TIMEOUT_SECONDS, (
            f"{name}: connect timeout is {timeout.connect!r} — the implicit "
            f"SDK default, exactly what let the CLOSE_WAIT hang happen"
        )
        assert timeout.read == LLM_READ_TIMEOUT_SECONDS, name
        assert client.max_retries == expected_retries, name


def test_the_inventory_covers_every_provider_class():
    """A provider class this file does not construct is an unchecked client."""
    import inspect

    covered = {name for name, _, _ in _provider_clients()}
    all_providers = {
        name
        for name, obj in vars(llm_module).items()
        if inspect.isclass(obj)
        and issubclass(obj, llm_module.LLM)
        and obj is not llm_module.LLM
    }
    assert covered == all_providers, (
        f"providers without a bounds check: {sorted(all_providers - covered)}"
    )


def test_a_stalled_read_becomes_the_typed_connection_error():
    """The user-facing half: a timeout ends in LLMConnectionError, not a hang
    and not a raw SDK type the caller has to know per-provider."""
    import openai

    provider = llm_module.OpenAILLM(api_key=DUMMY_KEY)

    def stalled_send():
        raise openai.APITimeoutError(request=None)

    with pytest.raises(LLMConnectionError):
        provider._call_provider(stalled_send)


def test_the_bounds_are_finite_and_positive():
    """The documented upper bound — (1 + retries) x read — must be computable."""
    bounds = _network_bounds()
    assert 0 < LLM_CONNECT_TIMEOUT_SECONDS < LLM_READ_TIMEOUT_SECONDS
    assert bounds["max_retries"] >= 0
    worst_case = (1 + bounds["max_retries"]) * LLM_READ_TIMEOUT_SECONDS
    assert worst_case <= 3600, "a stall must resolve within an hour, documented"

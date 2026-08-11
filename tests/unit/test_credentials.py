"""Ambient OpenOnion credentials fail closed at billed and mailbox boundaries."""

from __future__ import annotations

import base64
import json

import pytest

from connectonion import credentials
from connectonion.credentials import (
    AmbientAPIKeyAccountMismatch,
    MissingAmbientAPIKey,
    account_in_token,
    api_key_account_mismatch,
    require_ambient_api_key,
)


PROJECT = "0x" + "12" * 32
GLOBAL = "0x" + "34" * 32
FOREIGN = "0x" + "56" * 32


def token_with_payload(payload_value) -> str:
    payload = base64.urlsafe_b64encode(
        json.dumps(payload_value).encode()
    ).decode().rstrip("=")
    return f"header.{payload}.signature"


def token_for(address: str) -> str:
    return token_with_payload({"public_key": address})


@pytest.fixture
def project(monkeypatch):
    monkeypatch.setattr(
        credentials,
        "project_identity",
        lambda: {"address": PROJECT},
    )
    monkeypatch.delenv("OPENONION_API_KEY", raising=False)


def test_project_token_is_the_canonical_ambient_credential(project, monkeypatch):
    token = token_for(PROJECT)
    monkeypatch.setenv("OPENONION_API_KEY", token)

    assert require_ambient_api_key() == token


def test_global_fallback_identity_is_accepted(monkeypatch):
    token = token_for(GLOBAL)
    monkeypatch.setenv("OPENONION_API_KEY", token)
    monkeypatch.setattr(
        credentials,
        "project_identity",
        lambda: {"address": GLOBAL},
    )

    assert require_ambient_api_key() == token


def test_account_comparison_is_case_insensitive(project, monkeypatch):
    token = token_for(PROJECT.upper())
    monkeypatch.setenv("OPENONION_API_KEY", token)

    assert require_ambient_api_key() == token


def test_mismatch_raises_without_exposing_the_token(project, monkeypatch):
    token = token_for(FOREIGN)
    monkeypatch.setenv("OPENONION_API_KEY", token)

    with pytest.raises(AmbientAPIKeyAccountMismatch) as caught:
        require_ambient_api_key()

    assert caught.value.claimed == FOREIGN
    assert caught.value.expected == PROJECT
    assert token not in str(caught.value)


def test_diagnostics_share_the_runtime_account_comparison():
    token = token_for(FOREIGN)

    assert api_key_account_mismatch(token, {"address": PROJECT}) == (
        FOREIGN,
        PROJECT,
    )
    assert api_key_account_mismatch(token_for(PROJECT.upper()), {"address": PROJECT}) is None
    assert api_key_account_mismatch("opaque-token", {"address": PROJECT}) is None
    assert api_key_account_mismatch(token, None) is None


def test_missing_token_has_one_actionable_typed_error(project):
    with pytest.raises(MissingAmbientAPIKey, match="OPENONION_API_KEY not found"):
        require_ambient_api_key()


@pytest.mark.parametrize(
    "payload",
    [[], "text", 7, None, {}, {"public_key": []}, {"public_key": 7}],
)
def test_uninspectable_claims_do_not_duplicate_server_authentication(
    project, monkeypatch, payload
):
    token = token_with_payload(payload)
    monkeypatch.setenv("OPENONION_API_KEY", token)

    assert account_in_token(token) is None
    assert require_ambient_api_key() == token


def test_no_local_identity_leaves_server_authentication_authoritative(monkeypatch):
    token = token_for(FOREIGN)
    monkeypatch.setenv("OPENONION_API_KEY", token)
    monkeypatch.setattr(credentials, "project_identity", lambda: None)

    assert require_ambient_api_key() == token


@pytest.mark.parametrize(
    ("function_name", "args"),
    [
        ("get_emails", ()),
        ("get_sent", ()),
        ("mark_read", ("message-id",)),
        ("mark_unread", ("message-id",)),
    ],
)
def test_mailbox_mismatch_stops_before_the_http_request(
    project, monkeypatch, function_name, args
):
    from importlib import import_module

    get_emails_module = import_module("connectonion.useful_tools.get_emails")
    monkeypatch.setenv("OPENONION_API_KEY", token_for(FOREIGN))

    def fail(*args, **kwargs):
        pytest.fail("mail request used foreign token")

    monkeypatch.setattr(get_emails_module.requests, "get", fail)
    monkeypatch.setattr(get_emails_module.requests, "post", fail)

    with pytest.raises(AmbientAPIKeyAccountMismatch):
        getattr(get_emails_module, function_name)(*args)


def test_transcribe_mismatch_stops_before_a_billed_request(project, monkeypatch):
    from connectonion.transcribe import _get_api_key

    monkeypatch.setenv("OPENONION_API_KEY", token_for(FOREIGN))

    with pytest.raises(AmbientAPIKeyAccountMismatch):
        _get_api_key("co/gemini-3.6-flash")


def test_image_upload_mismatch_stops_before_http(project, monkeypatch):
    from importlib import import_module

    formatter = import_module(
        "connectonion.useful_plugins.image_result_formatter"
    )
    monkeypatch.setenv("OPENONION_API_KEY", token_for(FOREIGN))
    monkeypatch.setattr(
        formatter.requests,
        "post",
        lambda *args, **kwargs: pytest.fail("image request used foreign token"),
    )

    with pytest.raises(AmbientAPIKeyAccountMismatch):
        formatter._upload_to_oo_api("eA==", "image/png")


def test_llm_environment_mismatch_stops_before_client_creation(
    project, monkeypatch
):
    import openai
    from connectonion.core.llm import OpenOnionLLM

    monkeypatch.setenv("OPENONION_API_KEY", token_for(FOREIGN))
    monkeypatch.setattr(
        openai,
        "OpenAI",
        lambda *args, **kwargs: pytest.fail("LLM client used foreign token"),
    )

    with pytest.raises(AmbientAPIKeyAccountMismatch):
        OpenOnionLLM(model="co/gemini-3.6-flash")


def test_explicit_llm_key_remains_caller_owned(project, monkeypatch):
    import openai
    from connectonion.core.llm import OpenOnionLLM

    captured = {}

    def client(**kwargs):
        captured.update(kwargs)
        return object()

    monkeypatch.setattr(openai, "OpenAI", client)
    monkeypatch.setenv("OPENONION_API_KEY", token_for(FOREIGN))

    llm = OpenOnionLLM(api_key="explicit-key", model="co/gemini-3.6-flash")

    assert llm.auth_token == "explicit-key"
    assert captured["api_key"] == "explicit-key"

import pytest

from connectonion.core.acp_wire import (
    ACP_SCHEMA_VERSION,
    acp_set_mode_error_frame,
    acp_set_mode_request,
    acp_set_mode_request_id,
    acp_set_mode_response_frame,
    acp_session_mode_state,
)


SESSION_ID = "session-mode-883"
REQUEST_ID = "request-mode-883"


def request(*, session_id=SESSION_ID, mode_id="accept_edits", **message_fields):
    return {
        "type": "ACP_REQUEST",
        "acpSchema": ACP_SCHEMA_VERSION,
        "message": {
            "jsonrpc": "2.0",
            "id": REQUEST_ID,
            "method": "session/set_mode",
            "params": {"sessionId": session_id, "modeId": mode_id},
            **message_fields,
        },
    }


def test_exact_official_session_mode_state_uses_persisted_ids():
    assert acp_session_mode_state(
        "accept_edits", ["safe", "accept_edits", "ulw"]
    ) == {
        "currentModeId": "accept_edits",
        "availableModes": [
            {
                "id": "safe",
                "name": "Safe",
                "description": "Ask before side effects.",
            },
            {
                "id": "accept_edits",
                "name": "Auto",
                "description": "Apply edits without asking; other tools still require approval.",
            },
            {
                "id": "ulw",
                "name": "ULW",
                "description": "Run without tool approvals within the Host launch ceiling.",
            },
        ],
    }


def test_mode_state_rejects_plan_unknown_duplicates_and_unadvertised_current():
    with pytest.raises(ValueError, match="Unsupported ACP session mode"):
        acp_session_mode_state("plan", ["safe"])
    with pytest.raises(ValueError, match="Unsupported ACP session mode"):
        acp_session_mode_state("safe", ["safe", "future"])
    with pytest.raises(ValueError, match="duplicate"):
        acp_session_mode_state("safe", ["safe", "safe"])
    with pytest.raises(ValueError, match="not advertised"):
        acp_session_mode_state("accept_edits", ["safe"])


def test_exact_set_mode_request_parses_through_official_model():
    assert acp_set_mode_request(
        request(), expected_session_id=SESSION_ID
    ) == (REQUEST_ID, "accept_edits")
    assert acp_set_mode_request_id(request()) == REQUEST_ID


@pytest.mark.parametrize(
    "frame, message",
    [
        (request(session_id="another-session"), "another session"),
        (request(mode_id="plan"), "Unsupported ACP session mode"),
        (request(extra=True), "exact JSON-RPC request"),
        ({**request(), "acpSchema": "future"}, "carrier schema"),
        ({**request(), "type": "ACP_RESPONSE"}, "request carrier"),
    ],
)
def test_set_mode_request_fails_closed(frame, message):
    with pytest.raises(ValueError, match=message):
        acp_set_mode_request(frame, expected_session_id=SESSION_ID)


def test_set_mode_request_allows_meta_but_never_reads_authority_from_it():
    frame = request(mode_id="safe")
    frame["message"]["params"]["_meta"] = {
        "turns": 999999,
        "modeId": "ulw",
    }

    assert acp_set_mode_request(
        frame, expected_session_id=SESSION_ID
    ) == (REQUEST_ID, "safe")


def test_exact_success_and_error_response_carriers():
    assert acp_set_mode_response_frame(REQUEST_ID, SESSION_ID) == {
        "type": "ACP_RESPONSE",
        "acpSchema": ACP_SCHEMA_VERSION,
        "sessionId": SESSION_ID,
        "message": {
            "jsonrpc": "2.0",
            "id": REQUEST_ID,
            "result": {},
        },
    }
    assert acp_set_mode_error_frame(
        REQUEST_ID,
        SESSION_ID,
        -32000,
        "Session is busy",
        {"retryable": True},
    ) == {
        "type": "ACP_RESPONSE",
        "acpSchema": ACP_SCHEMA_VERSION,
        "sessionId": SESSION_ID,
        "message": {
            "jsonrpc": "2.0",
            "id": REQUEST_ID,
            "error": {
                "code": -32000,
                "message": "Session is busy",
                "data": {"retryable": True},
            },
        },
    }

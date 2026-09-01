"""The bounded OIP compatibility window advertised by every Host surface."""

OIP_NAME = "oip"
OIP_VERSION = "0.1"
OIP_MIN_VERSION = "0.1"
OIP_MAX_VERSION = "0.1"
_TRANSPORTS = {"direct", "relay"}
SESSION_SYNC_EXTENSION = "session-sync"
SESSION_SYNC_VERSION = "0.1"


def oip_descriptor(*, session_sync: bool = False):
    """Return a fresh public descriptor so callers cannot mutate shared state."""
    value = {
        "name": OIP_NAME,
        "version": OIP_VERSION,
        "min_version": OIP_MIN_VERSION,
        "max_version": OIP_MAX_VERSION,
        "websocket_path": "/ws",
    }
    if session_sync:
        value["extensions"] = {SESSION_SYNC_EXTENSION: SESSION_SYNC_VERSION}
    return value


def requests_session_sync(data) -> bool:
    """Whether the signed CONNECT requested the experimental extension."""
    payload = data.get("payload") if isinstance(data, dict) else None
    extensions = payload.get("extensions") if isinstance(payload, dict) else None
    versions = (
        extensions.get(SESSION_SYNC_EXTENSION)
        if isinstance(extensions, dict)
        else None
    )
    return isinstance(versions, list) and SESSION_SYNC_VERSION in versions


def requests_session_sync_only(data) -> bool:
    """Whether CONNECT asks for an authenticated index socket without a chat."""
    payload = data.get("payload") if isinstance(data, dict) else None
    return requests_session_sync(data) and isinstance(payload, dict) and (
        payload.get("session_sync_only") == 1
    )


def supports_oip(value):
    """Missing means the legacy 0.1 reader; advertised values must match."""
    if value is None:
        return True
    return (
        isinstance(value, dict)
        and value.get("name") == OIP_NAME
        and value.get("version") == OIP_VERSION
    )


def oip_compatibility_record(value, transport):
    """Classify one CONNECT without copying peer-controlled strings to logs."""
    if value is None:
        peer = "legacy"
    elif supports_oip(value):
        peer = f"{OIP_NAME}/{OIP_VERSION}"
    else:
        peer = "unsupported"
    return {
        "transport": transport if transport in _TRANSPORTS else "unknown",
        "peer": peer,
        "outcome": "accepted" if peer != "unsupported" else "rejected",
    }

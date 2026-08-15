"""The bounded OIP compatibility window advertised by every Host surface."""

OIP_NAME = "oip"
OIP_VERSION = "0.1"
OIP_MIN_VERSION = "0.1"
OIP_MAX_VERSION = "0.1"


def oip_descriptor():
    """Return a fresh public descriptor so callers cannot mutate shared state."""
    return {
        "name": OIP_NAME,
        "version": OIP_VERSION,
        "min_version": OIP_MIN_VERSION,
        "max_version": OIP_MAX_VERSION,
        "websocket_path": "/ws",
    }


def supports_oip(value):
    """Missing means the legacy 0.1 reader; advertised values must match."""
    if value is None:
        return True
    return (
        isinstance(value, dict)
        and value.get("name") == OIP_NAME
        and value.get("version") == OIP_VERSION
    )

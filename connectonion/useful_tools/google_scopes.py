"""Read normalized scopes from the selected Google account record."""
from ..provider_credentials import resolve_provider_credentials


def granted_scopes() -> set[str]:
    return resolve_provider_credentials("google").scopes

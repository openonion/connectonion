"""Whole-account Google/Microsoft credentials and stateless broker refresh."""

from __future__ import annotations

from contextlib import nullcontext
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
import re

import httpx

from .environment import (explicit_env_file, process_environment, provider_keys,
                          publish_values, publish_authorization, read_env_file, selected_env_file)
from .env_file import env_lock, write_env_unlocked


class ProviderCredentialError(ValueError):
    """Sanitized classification and recovery, safe for both CLI and SDK callers."""

    def __init__(self, code: str, message: str, next_command: str):
        self.code = code
        self.next_command = next_command
        super().__init__(f"{message}\nNext: {next_command}")


@dataclass
class ProviderCredentials:
    provider: str
    values: dict[str, str] = field(repr=False)
    path: Path | None = None

    def get(self, name: str) -> str | None:
        return self.values.get(f"{self.provider.upper()}_{name}")

    @property
    def scopes(self) -> set[str]:
        return {scope.removeprefix("https://www.googleapis.com/auth/")
                for scope in re.split(r"[,\s]+", self.get("SCOPES") or "") if scope}

    @property
    def source(self) -> str:
        return str(self.path) if self.path else "process environment"

    @property
    def auth_command(self) -> str:
        import shlex
        selector = f" --env-file {shlex.quote(str(self.path))}" if self.path and explicit_env_file() else ""
        return f"co{selector} auth {self.provider}"

    def require_configured(self) -> None:
        if not (self.get("ACCESS_TOKEN") or self.get("REFRESH_TOKEN")):
            raise ProviderCredentialError("not_configured", f"{self.provider.title()} account not connected.", self.auth_command)


def resolve_provider_credentials(provider: str) -> ProviderCredentials:
    """Process record > explicitly selected file > default global file; no merging."""
    keys = provider_keys(provider)
    inherited = process_environment()
    if any(key in inherited for key in keys):
        return ProviderCredentials(provider, {key: inherited[key] for key in keys if key in inherited})
    path = selected_env_file()
    values = read_env_file(path, required=explicit_env_file() is not None)
    return ProviderCredentials(provider, {key: values[key] for key in keys if key in values}, path)


def token_expiry(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        expiry = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return expiry.replace(tzinfo=timezone.utc) if expiry.tzinfo is None else expiry.astimezone(timezone.utc)


def _fresh(record: ProviderCredentials) -> bool:
    expiry = token_expiry(record.get("TOKEN_EXPIRES_AT"))
    return bool(record.get("ACCESS_TOKEN") and expiry and expiry > datetime.now(timezone.utc) + timedelta(minutes=5))


def _latest(record: ProviderCredentials) -> ProviderCredentials:
    if record.path is None:
        return record
    values = read_env_file(record.path, required=True)
    current = ProviderCredentials(record.provider, {key: values[key] for key in provider_keys(record.provider) if key in values}, record.path)
    if current.values == record.values:
        return current
    old_email, new_email = record.get("EMAIL"), current.get("EMAIL")
    same_account = (old_email and new_email and old_email.casefold() == new_email.casefold())
    same_grant = record.get("REFRESH_TOKEN") and record.get("REFRESH_TOKEN") == current.get("REFRESH_TOKEN")
    if (old_email and new_email and not same_account) or not (same_account or same_grant):
        raise ProviderCredentialError("record_changed", "The selected credential record changed during this operation.", "co status")
    return current


def _validated_values(record: ProviderCredentials, data: dict) -> dict[str, str]:
    try:
        access, expires = data["access_token"], data["expires_at"]
        expiry = token_expiry(expires)
        if not isinstance(access, str) or not access or not expiry or expiry <= datetime.now(timezone.utc):
            raise ValueError
        values = dict(record.values)
        mapping = {"access_token": "ACCESS_TOKEN", "refresh_token": "REFRESH_TOKEN",
                   "expires_at": "TOKEN_EXPIRES_AT", "scopes": "SCOPES",
                   f"{record.provider}_email": "EMAIL"}
        for field_name, suffix in mapping.items():
            value = data.get(field_name)
            if value is None:
                continue
            if not isinstance(value, str) or (suffix in ("ACCESS_TOKEN", "REFRESH_TOKEN", "EMAIL") and not value):
                raise ValueError
            if suffix == "EMAIL" and record.get("EMAIL") and value.casefold() != record.get("EMAIL").casefold():
                raise ValueError
            values[f"{record.provider.upper()}_{suffix}"] = value
        return values
    except (KeyError, TypeError, ValueError, AttributeError):
        raise ProviderCredentialError("invalid_response", "Authorization service returned invalid credentials; saved record kept.", "co status") from None


def _refresh_error(record: ProviderCredentials, response) -> None:
    try:
        payload = response.json()
        detail = payload.get("detail") if isinstance(payload, dict) else None
    except (TypeError, ValueError):
        detail = None
    if response.status_code == 401 and isinstance(detail, dict) and detail.get("error") == "reauth_required":
        raise ProviderCredentialError("reauth_required", f"{record.provider.title()} authorization expired or was revoked.", record.auth_command)
    if response.status_code == 401:
        raise ProviderCredentialError("broker_auth_failed", "OpenOnion authentication failed while refreshing provider access.", "co auth")
    raise ProviderCredentialError("provider_unavailable", f"Authorization service could not refresh credentials (HTTP {response.status_code}).", "co status")


def refresh_credentials(record: ProviderCredentials, *, backend: str, api_key: str,
                        post=None) -> str:
    """Serialize the network refresh and atomic save; process overrides stay in memory."""
    post = post or httpx.post
    with env_lock(record.path) if record.path is not None else nullcontext():
        latest = _latest(record)
        # Another CLI already refreshed this same account while we waited.
        if latest.values != record.values and _fresh(latest):
            record.values = latest.values
        else:
            refresh_token = latest.get("REFRESH_TOKEN")
            if not refresh_token:
                raise ProviderCredentialError("incomplete_record", f"Local {record.provider.title()} refresh token missing.", record.auth_command)
            try:
                response = post(f"{backend}/api/v1/oauth/{record.provider}/refresh",
                                headers={"Authorization": f"Bearer {api_key}"},
                                json={"refresh_token": refresh_token}, timeout=15.0)
            except httpx.HTTPError:
                raise ProviderCredentialError("network_error", "Cannot reach the authorization service; saved credentials kept.", "co status") from None
            if response.status_code != 200:
                _refresh_error(record, response)
            try:
                data = response.json()
            except ValueError:
                data = None
            values = _validated_values(latest, data)
            if record.path:
                write_env_unlocked(record.path, values)
            record.values = values
        publish_values(record.values, managed=record.path is not None)
        return record.get("ACCESS_TOKEN")


def save_authorization(provider: str, path: Path, credentials: dict) -> None:
    """An explicit consent replaces the provider record, never another env file."""
    record = ProviderCredentials(provider, {}, Path(path).resolve())
    values = _validated_values(record, credentials)
    with env_lock(record.path):
        write_env_unlocked(record.path, values, strip_prefix=f"{provider.upper()}_")
    publish_authorization(provider, values)

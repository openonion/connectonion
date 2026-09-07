"""YouTube uses the same saved Google login and OAuth broker as Gmail."""

import os
import re
from datetime import datetime, timezone
from pathlib import Path

import httpx
from google.oauth2.credentials import Credentials

from ..backend import backend_url
from ..credentials import require_ambient_api_key
from ..provider_credentials import (resolve_provider_credentials, refresh_credentials,
                                    token_expiry, ProviderCredentialError)
from .creator_plan import CreatorError

AUTH_COMMAND = "co auth google"
SCOPES = {
    "read": {"youtube", "youtube.force-ssl", "youtube.readonly"},
    "upload": {"youtube", "youtube.upload"},
    "update": {"youtube", "youtube.force-ssl"},
}


class YouTubeGoogleAuth:
    """Refresh through oo-api; Google client secrets stay on the backend."""

    def __init__(self):
        self._credentials = resolve_provider_credentials("google")
        try:
            self._credentials.require_configured()
        except ProviderCredentialError as error:
            raise CreatorError(error.code, str(error)) from None

    def require_scope(self, operation: str) -> None:
        granted = self._credentials.scopes
        # Missing metadata does not prove a denied grant. The API decides.
        if granted and not granted.intersection(SCOPES[operation]):
            raise CreatorError("auth_required", f"Google needs YouTube {operation} permission. Run: {self._credentials.auth_command}")

    def refresh(self, request=None, scopes=None):
        try:
            token = refresh_credentials(self._credentials, backend=backend_url(),
                                        api_key=require_ambient_api_key(), post=httpx.post)
        except ProviderCredentialError as error:
            raise CreatorError(error.code, str(error)) from None
        expiry = token_expiry(self._credentials.get("TOKEN_EXPIRES_AT"))
        return token, expiry.replace(tzinfo=None) if expiry else None

    def credentials(self) -> Credentials:
        self.require_scope("read")
        token = self._credentials.get("ACCESS_TOKEN")
        expiry = token_expiry(self._credentials.get("TOKEN_EXPIRES_AT"))
        if self._credentials.get("REFRESH_TOKEN") or not token or (expiry and expiry <= datetime.now(timezone.utc)):
            token, expiry = self.refresh()
        elif expiry:
            expiry = expiry.replace(tzinfo=None)
        self.require_scope("read")
        return Credentials(token=token, expiry=expiry, refresh_handler=self.refresh)

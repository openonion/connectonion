"""YouTube uses the same saved Google login and OAuth broker as Gmail."""

import os
import re
from datetime import datetime, timezone
from pathlib import Path

import httpx
from dotenv import load_dotenv
from google.oauth2.credentials import Credentials

from ..backend import backend_url
from ..credentials import require_ambient_api_key
from ..project import project_root
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
        load_dotenv(project_root() / ".env")
        load_dotenv(Path(os.getenv("AGENT_CONFIG_PATH", str(Path.home() / ".co"))) / "keys.env")
        if not os.getenv("GOOGLE_ACCESS_TOKEN"):
            raise CreatorError("auth_required", f"Connect Google with YouTube access: {AUTH_COMMAND}")

    def require_scope(self, operation: str) -> None:
        granted = {scope.removeprefix("https://www.googleapis.com/auth/")
                   for scope in re.split(r"[,\s]+", os.getenv("GOOGLE_SCOPES", ""))}
        if not granted.intersection(SCOPES[operation]):
            raise CreatorError("auth_required", f"Google needs YouTube {operation} permission. Run: {AUTH_COMMAND}")

    def refresh(self, request=None, scopes=None):
        """google-auth callback, also used before constructing the first service."""
        # Resolve the same account-bound broker key as Gmail before any request.
        api_key = require_ambient_api_key()
        refresh_token = os.getenv("GOOGLE_REFRESH_TOKEN")
        if not refresh_token:
            raise CreatorError("auth_required", f"Local Google refresh token missing. Run: {AUTH_COMMAND}")
        try:
            response = httpx.post(
                f"{backend_url()}/api/v1/oauth/google/refresh",
                headers={"Authorization": f"Bearer {api_key}"}, timeout=15.0,
                json={"refresh_token": refresh_token},
            )
        except httpx.HTTPError:
            raise CreatorError("auth_unavailable", "Cannot reach the Google authorization service. Try again later.") from None
        if response.status_code in {401, 404}:
            raise CreatorError("auth_required", f"Google authorization expired or was revoked. Run: {AUTH_COMMAND}")
        if response.status_code != 200:
            raise CreatorError("auth_unavailable", "The Google authorization service could not refresh this login.")
        try:
            data = response.json()
            token, expires_at = data["access_token"], data["expires_at"]
            expiry = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
            if expiry.tzinfo:
                expiry = expiry.astimezone(timezone.utc).replace(tzinfo=None)
            if not isinstance(token, str) or not token or expiry <= datetime.now(timezone.utc).replace(tzinfo=None):
                raise ValueError
            values = {"GOOGLE_ACCESS_TOKEN": token, "GOOGLE_TOKEN_EXPIRES_AT": expires_at}
            for field, variable in [("refresh_token", "GOOGLE_REFRESH_TOKEN"), ("scopes", "GOOGLE_SCOPES")]:
                if field in data:
                    if not isinstance(data[field], str):
                        raise ValueError
                    values[variable] = data[field]
        except (ValueError, TypeError, KeyError, AttributeError):
            raise CreatorError("auth_unavailable", "The Google authorization service returned invalid credentials.") from None

        from ..cli.commands.project_cmd_lib import upsert_env
        env_file = Path(os.getenv("AGENT_CONFIG_PATH", str(Path.home() / ".co"))) / "keys.env"
        env_file.parent.mkdir(parents=True, exist_ok=True)
        upsert_env(env_file, values)
        env_file.chmod(0o600)
        os.environ.update(values)
        return token, expiry

    def credentials(self) -> Credentials:
        self.require_scope("read")
        token, expiry = self.refresh()
        self.require_scope("read")
        return Credentials(token=token, expiry=expiry, refresh_handler=self.refresh)

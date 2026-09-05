"""Drive the real CLI with synthetic provider/browser responses for pipe tests.

Run with PYTHONPATH=. for the checkout, or with the installed wheel interpreter
and no PYTHONPATH to verify packaging. No credential source or network is used.
"""

import os
os.environ["PYTHON_DOTENV_DISABLED"] = "1"

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from connectonion.cli.main import app
from connectonion.cli.commands import auth_commands, tiktok_browser_commands, youtube_commands
from connectonion.useful_tools.creator_plan import CreatorError
from connectonion.useful_tools.youtube import YouTube

CHANNEL = "UC" + "a" * 22
VIDEO = "Abcdefgh_01"
api = MagicMock()
api.channels().list().execute.return_value = {"items": [{"id": CHANNEL, "snippet": {"title": "Fixture Channel"},
    "contentDetails": {"relatedPlaylists": {"uploads": "UU" + "a" * 22}}}]}
api.playlistItems().list().execute.return_value = {"items": [{"contentDetails": {"videoId": VIDEO}}]}
api.videos().list().execute.return_value = {"items": [{"id": VIDEO, "etag": '"fixture1"',
    "snippet": {"channelId": CHANNEL, "title": "Fixture video", "description": "Fixture description", "categoryId": "22"},
    "statistics": {"viewCount": "0"}, "status": {"privacyStatus": "private"}}]}
api.videos().insert.side_effect = AssertionError("The pipe fixture cannot upload")
api.videos().update.side_effect = AssertionError("The pipe fixture cannot update")


def inspect(tab):
    return {"ok": False, "mode": "read", "reason": "login_required", "verified": True, "items": []}


def client(*args, **kwargs):
    if os.getenv("CREATOR_CLI_FIXTURE_MODE") == "missing_google":
        raise CreatorError("auth_required", "Connect Google with YouTube access: co auth google --youtube")
    return YouTube(service=api)


with (
    tempfile.TemporaryDirectory(prefix="creator-pipe-") as directory,
    patch.object(Path, "home", return_value=Path(directory)),
    patch.object(youtube_commands, "_client", side_effect=client),
    patch.object(auth_commands, "load_api_key", return_value=None),
    patch.object(tiktok_browser_commands, "inspect_page", side_effect=inspect),
):
    app(prog_name="co")

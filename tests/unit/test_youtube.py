"""YouTube requests are intercepted; every write uses a synthetic service."""

import copy
import json
from unittest.mock import MagicMock

import pytest

from connectonion.useful_tools.creator_plan import CreatorError
from connectonion.useful_tools.youtube import YouTube, channel_target, video_id, prepare_upload


CHANNEL = "UC" + "a" * 22
VIDEO = "Abcdefgh_01"


@pytest.fixture
def service():
    api = MagicMock()
    api.channels().list().execute.return_value = {"items": [{
        "id": CHANNEL, "snippet": {"title": "Test channel"},
        "contentDetails": {"relatedPlaylists": {"uploads": "UU" + "a" * 22}},
    }]}
    api.videos().list().execute.return_value = {"items": [{
        "id": VIDEO, "etag": '"version1"',
        "snippet": {"channelId": CHANNEL, "title": "Before", "description": "Keep me",
                    "categoryId": "22", "tags": ["original"], "defaultLanguage": "en"},
        "status": {"privacyStatus": "private"}, "statistics": {"viewCount": "0"},
    }]}
    return api


def test_url_normalization_and_lookalike_host_refusal():
    for value in [VIDEO, f"https://youtu.be/{VIDEO}", f"https://www.youtube.com/watch?v={VIDEO}&t=10",
                  f"https://youtube.com/shorts/{VIDEO}"]:
        assert video_id(value) == VIDEO
    assert channel_target("https://www.youtube.com/@YouTube/videos") == {"forHandle": "@YouTube"}
    for value in [f"https://youtube.com.evil/watch?v={VIDEO}", f"https://evil/youtu.be/{VIDEO}", "12"]:
        with pytest.raises(CreatorError):
            video_id(value)


def test_list_uses_uploads_playlist_and_preserves_order(service):
    service.playlistItems().list().execute.side_effect = [
        {"items": [{"contentDetails": {"videoId": VIDEO}}], "nextPageToken": "page2"},
        {"items": [{"contentDetails": {"videoId": "Abcdefgh_02"}}]},
    ]
    result = YouTube(service=service).list_videos(last=2)
    assert [item["id"] for item in result] == [VIDEO, "Abcdefgh_02"]
    assert result[0]["views"] == 0
    assert result[0]["likes"] is None
    assert result[1]["availability"] == "not returned"
    service.search.assert_not_called()


def test_update_preview_preserves_snippet_and_sends_no_write(service):
    client = YouTube(service=service)
    plan = client.update(VIDEO, title="After")
    assert plan["body"]["snippet"]["description"] == "Keep me"
    assert plan["body"]["snippet"]["tags"] == ["original"]
    assert "status" not in plan["body"]
    assert plan["etag"] == '"version1"'
    service.videos().update.assert_not_called()


def test_update_requires_exact_current_plan_and_owner(service):
    client = YouTube(service=service)
    plan = client.update(VIDEO, title="After")
    service.videos().list().execute.return_value["items"][0]["etag"] = '"version2"'
    with pytest.raises(CreatorError, match="confirmation"):
        client.update(VIDEO, title="After", confirmation=plan["confirmation"])
    service.videos().update.assert_not_called()
    service.channels().list().execute.return_value["items"][0]["id"] = "UC" + "b" * 22
    with pytest.raises(CreatorError, match="channel"):
        client.update(VIDEO, title="After")


def test_confirmed_update_has_conditional_header_and_no_retry(service):
    client = YouTube(service=service)
    plan = client.update(VIDEO, title="After")
    response = copy.deepcopy(service.videos().list().execute.return_value["items"][0])
    response["snippet"]["title"] = "After"
    service.videos().update().execute.return_value = response
    service.videos().update.reset_mock()
    result = client.update(VIDEO, title="After", confirmation=plan["confirmation"])
    assert result["id"] == VIDEO
    request = service.videos().update.return_value
    request.headers.__setitem__.assert_called_with("If-Match", '"version1"')
    request.execute.assert_called_once_with(num_retries=0)
    with pytest.raises(CreatorError, match="already"):
        client.update(VIDEO, title="After", confirmation=plan["confirmation"])


def test_upload_preview_needs_no_client_and_bad_confirmation_never_opens_request(tmp_path, service):
    path = tmp_path / "clip.mp4"
    path.write_bytes(b"synthetic")
    plan = prepare_upload(str(path), "Demo", CHANNEL)
    with pytest.raises(CreatorError, match="confirmation"):
        YouTube(service=service).upload(str(path), "Demo", CHANNEL, confirmation="wrong")
    service.videos().insert.assert_not_called()
    service.videos().insert().next_chunk.side_effect = [(MagicMock(), None), (None, {"id": VIDEO})]
    service.videos().insert.reset_mock()
    result = YouTube(service=service).upload(str(path), "Demo", CHANNEL, confirmation=plan["confirmation"])
    assert result["id"] == VIDEO
    assert service.videos().insert.call_count == 1
    assert service.videos().insert.call_args.kwargs["notifySubscribers"] is False
    assert service.videos().insert().next_chunk.call_args.kwargs == {"num_retries": 0}


@pytest.mark.parametrize("status,reason,code", [
    (401, "authError", "auth_required"), (403, "insufficientPermissions", "auth_required"),
    (403, "quotaExceeded", "quota"), (429, "anything", "quota"), (403, "forbidden", "forbidden"),
    (404, "videoNotFound", "unavailable"), (412, "conditionNotMet", "stale_video"),
    (500, "backendError", "provider_error"),
])
def test_http_errors_are_classified_without_leaking_secrets(service, status, reason, code):
    from googleapiclient.errors import HttpError
    from httplib2 import Response
    body = {"error": {"message": "SECRET token and private URL", "errors": [{"reason": reason}]}}
    service.videos().list().execute.side_effect = HttpError(Response({"status": status}), json.dumps(body).encode(), uri="SECRET")
    with pytest.raises(CreatorError) as raised:
        YouTube(service=service).video(VIDEO)
    assert raised.value.code == code
    assert "SECRET" not in str(raised.value)
    assert raised.value.__suppress_context__


def test_repeated_playlist_cursor_fails_instead_of_returning_partial_success(service):
    service.playlistItems().list().execute.return_value = {"items": [], "nextPageToken": "repeated"}
    with pytest.raises(CreatorError, match="repeated"):
        YouTube(service=service).list_videos(last=3)
    assert service.playlistItems().list().execute.call_count == 2


def test_upload_failure_is_not_retried_and_blocks_the_same_plan(tmp_path, service):
    path = tmp_path / "clip.mp4"
    path.write_bytes(b"synthetic")
    plan = prepare_upload(str(path), "Demo", CHANNEL)
    service.videos().insert().next_chunk.side_effect = TimeoutError("SECRET session URL")
    service.videos().insert.reset_mock()
    client = YouTube(service=service)
    with pytest.raises(CreatorError):
        client.upload(str(path), "Demo", CHANNEL, confirmation=plan["confirmation"])
    service.videos().insert.return_value.next_chunk.assert_called_once_with(num_retries=0)
    with pytest.raises(CreatorError, match="already"):
        client.upload(str(path), "Demo", CHANNEL, confirmation=plan["confirmation"])
    assert service.videos().insert.call_count == 1


def test_changed_media_snapshot_is_rejected_before_insert(tmp_path, service, monkeypatch):
    from contextlib import contextmanager
    from connectonion.useful_tools import youtube as module
    path = tmp_path / "clip.mp4"
    path.write_bytes(b"synthetic")
    plan = prepare_upload(str(path), "Demo", CHANNEL)
    @contextmanager
    def changed(path):
        yield None, {**plan["file"], "sha256": "changed after preview"}
    monkeypatch.setattr(module, "media_snapshot", changed)
    with pytest.raises(CreatorError, match="confirmation"):
        YouTube(service=service).upload(str(path), "Demo", CHANNEL, confirmation=plan["confirmation"])
    service.videos().insert.assert_not_called()


def test_real_discovery_document_accepts_read_and_conditional_update_shapes(monkeypatch):
    """Static discovery validates request construction without any HTTP calls."""
    from google.oauth2.credentials import Credentials
    from connectonion.useful_tools.youtube_auth import YouTubeGoogleAuth
    monkeypatch.setenv("GOOGLE_ACCESS_TOKEN", "synthetic-never-sent")
    monkeypatch.setattr(YouTubeGoogleAuth, "credentials", lambda _: Credentials(token="synthetic-never-sent"))
    client = YouTube()
    api = client._api()
    read = api.channels().list(part="snippet,contentDetails,statistics", mine=True, maxResults=1)
    assert "mine=true" in read.uri
    update = api.videos().update(part="snippet", body={"id": VIDEO, "snippet": {"title": "New", "categoryId": "22"}})
    update.headers["If-Match"] = '"version1"'
    assert update.method == "PUT"
    assert update.headers["If-Match"] == '"version1"'

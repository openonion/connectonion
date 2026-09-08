"""YouTube Data API reads and preview-first, explicitly confirmed writes.

Uses the Google login saved by co auth google, with backend token refresh.
"""

import copy
import json
import re
from typing import Callable
from urllib.parse import parse_qs, unquote, urlsplit

from .creator_plan import (
    CreatorError, claim_operation, confirm_plan, media_file, media_snapshot, seal_plan,
)

CHANNEL_ID = re.compile(r"UC[A-Za-z0-9_-]{22}")
VIDEO_ID = re.compile(r"[A-Za-z0-9_-]{11}")
HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be", "www.youtu.be"}
VIDEO_PARTS = "snippet,contentDetails,statistics,status"
SNIPPET_FIELDS = ("title", "description", "categoryId", "tags", "defaultLanguage", "defaultAudioLanguage")


def _url(value: str):
    try:
        parsed = urlsplit(value)
        valid = parsed.scheme == "https" and parsed.hostname in HOSTS and not parsed.username and not parsed.password and not parsed.port
    except ValueError:
        valid = False
    if not valid:
        raise CreatorError("invalid_target", "Use a full YouTube ID or a canonical https YouTube URL.")
    return parsed


def video_id(value: str) -> str:
    """Normalize watch, Shorts and youtu.be links without following redirects."""
    if VIDEO_ID.fullmatch(value):
        return value
    parsed = _url(value)
    segments = parsed.path.strip("/").split("/")
    if parsed.hostname in {"youtu.be", "www.youtu.be"} and len(segments) == 1:
        candidate = segments[0]
    elif parsed.path == "/watch":
        candidates = parse_qs(parsed.query).get("v", [])
        candidate = candidates[0] if len(candidates) == 1 else ""
    elif len(segments) == 2 and segments[0] in {"shorts", "live"}:
        candidate = segments[1]
    else:
        candidate = ""
    if not VIDEO_ID.fullmatch(candidate):
        raise CreatorError("invalid_target", "Use an 11-character video ID or a watch, Shorts, or youtu.be URL.")
    return candidate


def channel_target(value: str | None) -> dict:
    """Choose exactly one documented channels.list filter."""
    if value is None:
        return {"mine": True}
    if value.startswith("https://"):
        parsed = _url(value)
        if parsed.hostname in {"youtu.be", "www.youtu.be"}:
            raise CreatorError("invalid_target", "Use a channel ID or @handle, not a video link.")
        parts = unquote(parsed.path).strip("/").split("/")
        if parts[0] == "channel" and len(parts) in {2, 3}:
            value = parts[1]
        elif parts[0].startswith("@") and len(parts) in {1, 2}:
            value = parts[0]
        else:
            raise CreatorError("invalid_target", "Use a /channel/ID or /@handle channel URL.")
    if CHANNEL_ID.fullmatch(value):
        return {"id": value}
    if value.startswith("@") and 1 < len(value) <= 101 and not re.search(r"[\s/?#]", value):
        return {"forHandle": value}
    raise CreatorError("invalid_target", "Use a UC channel ID, @handle, or canonical channel URL.")


def _metadata(title: str, description: str) -> None:
    if not title.strip() or len(title) > 100 or "<" in title or ">" in title:
        raise CreatorError("invalid_metadata", "Use a nonempty title of at most 100 characters without < or >.")
    if len(description.encode("utf-8")) > 5000 or "<" in description or ">" in description:
        raise CreatorError("invalid_metadata", "Use a description of at most 5000 UTF-8 bytes without < or >.")


def prepare_upload(path: str, title: str, channel_id: str, description: str = "",
                   privacy: str = "private", category: str = "22") -> dict:
    """Preview offline; no quota or account checks can be made without an API call."""
    _metadata(title, description)
    if not CHANNEL_ID.fullmatch(channel_id):
        raise CreatorError("invalid_target", "Supply the intended UC channel ID before preparing an upload.")
    if privacy not in {"private", "unlisted", "public"} or not re.fullmatch(r"[1-9][0-9]*", category):
        raise CreatorError("invalid_metadata", "Choose private, unlisted, or public visibility and a numeric category.")
    return seal_plan({
        "schema_version": 1, "operation": "youtube.upload", "channel_id": channel_id,
        "file": media_file(path), "notify_subscribers": False,
        "body": {"snippet": {"title": title, "description": description, "categoryId": category},
                 "status": {"privacyStatus": privacy}},
    })


def _provider_call(call: Callable):
    """Never propagate raw HTTP bodies, request URLs, or SDK token locals."""
    try:
        return call()
    except CreatorError:
        raise
    except Exception as error:
        status = getattr(getattr(error, "resp", None), "status", None)
        reason = ""
        try:
            body = json.loads(getattr(error, "content", b"{}"))
            reason = body.get("error", {}).get("errors", [{}])[0].get("reason", "")
        except (ValueError, TypeError, AttributeError, IndexError):
            reason = ""
        if not isinstance(reason, str):
            reason = ""
        if status == 401 or reason in {"authError", "insufficientPermissions"}:
            code, message = "auth_required", "The YouTube token is expired, revoked, or lacks the required scope."
        elif status == 429 or reason in {"quotaExceeded", "dailyLimitExceeded", "rateLimitExceeded", "uploadLimitExceeded"}:
            code, message = "quota", "YouTube quota or rate limit reached. Wait for the provider limit to reset."
        elif status == 412:
            code, message = "stale_video", "The video changed after preview; inspect it and prepare a new plan."
        elif status == 404:
            code, message = "unavailable", "YouTube did not return that resource."
        elif status == 403:
            code, message = "forbidden", "YouTube rejected this operation. Check ownership, API enablement, and granted scopes."
        else:
            code, message = "provider_error", "YouTube request failed. Raw provider details were withheld."
        raise CreatorError(code, message) from None


def _count(value):
    return int(value) if isinstance(value, (str, int)) and str(value).isascii() and str(value).isdigit() else None


def _video(item: dict) -> dict:
    snippet, stats = item.get("snippet", {}), item.get("statistics", {})
    return {"id": item["id"], "title": snippet.get("title"), "description": snippet.get("description"),
            "channel_id": snippet.get("channelId"), "published_at": snippet.get("publishedAt"),
            "duration": item.get("contentDetails", {}).get("duration"),
            "visibility": item.get("status", {}).get("privacyStatus", "not returned"),
            "views": _count(stats.get("viewCount")), "likes": _count(stats.get("likeCount")),
            "comments": _count(stats.get("commentCount")), "availability": "returned"}


class YouTube:
    """Google-authenticated client. Writes require the exact digest of a preview."""

    def __init__(self, *, service=None, progress: Callable | None = None):
        self._service = service
        self._auth = None
        self._progress = progress

    def _api(self):
        if self._service is None:
            from googleapiclient.discovery import build
            from .youtube_auth import YouTubeGoogleAuth
            self._auth = YouTubeGoogleAuth()
            credentials = self._auth.credentials()
            self._service = _provider_call(lambda: build(
                "youtube", "v3", credentials=credentials,
                cache_discovery=False, static_discovery=True,
            ))
        return self._service

    def _write_scope(self, operation: str) -> None:
        self._api()
        if self._auth is not None:
            self._auth.require_scope(operation)

    def _read(self, resource: str, **params) -> dict:
        return _provider_call(lambda: getattr(self._api(), resource)().list(**params).execute(num_retries=0))

    def channel(self, target: str | None = None) -> dict:
        """Read one public channel or the channel selected by the supplied grant."""
        data = self._read("channels", part="snippet,contentDetails,statistics", maxResults=1, **channel_target(target))
        items = data.get("items", [])
        if not items:
            raise CreatorError("no_channel", "YouTube did not return a channel for this request.")
        item = items[0]
        return {"id": item["id"], "title": item.get("snippet", {}).get("title"),
                "uploads_playlist": item.get("contentDetails", {}).get("relatedPlaylists", {}).get("uploads"),
                "subscribers": _count(item.get("statistics", {}).get("subscriberCount")),
                "subscriber_count_note": "API value; may be rounded or not returned"}

    def list_videos(self, target: str | None = None, last: int = 20) -> list[dict]:
        """Traverse the uploads playlist in order, with at most ten pages."""
        if not 1 <= last <= 200:
            raise CreatorError("invalid_limit", "Request between 1 and 200 videos.")
        playlist = self.channel(target).get("uploads_playlist")
        if not playlist:
            return []
        ids, seen_tokens, page_token = [], set(), None
        for _ in range(10):
            params = {"part": "contentDetails", "playlistId": playlist, "maxResults": min(50, last - len(ids))}
            if page_token:
                params["pageToken"] = page_token
            data = self._read("playlistItems", **params)
            for item in data.get("items", []):
                identity = item.get("contentDetails", {}).get("videoId")
                if isinstance(identity, str) and VIDEO_ID.fullmatch(identity) and identity not in ids:
                    ids.append(identity)
            page_token = data.get("nextPageToken")
            if len(ids) >= last or not page_token:
                break
            if page_token in seen_tokens:
                raise CreatorError("pagination", "YouTube repeated a page token; the listing was stopped.")
            seen_tokens.add(page_token)
        else:
            raise CreatorError("pagination", "YouTube exceeded the ten-page listing limit.")
        videos = {}
        for offset in range(0, len(ids[:last]), 50):
            for item in self._read("videos", part=VIDEO_PARTS, id=",".join(ids[:last][offset:offset + 50])).get("items", []):
                videos[item["id"]] = _video(item)
        return [videos.get(identity, {"id": identity, "availability": "not returned", "visibility": "not returned"})
                for identity in ids[:last]]

    def _raw_video(self, item: str) -> dict:
        identity = video_id(item)
        items = self._read("videos", part=VIDEO_PARTS, id=identity).get("items", [])
        if not items or items[0].get("id") != identity:
            raise CreatorError("unavailable", "YouTube did not return that video; its private or deleted state is unknown.")
        return items[0]

    def video(self, item: str) -> dict:
        """Read a video's metadata and returned counters, never download media."""
        return _video(self._raw_video(item))

    def _owner(self, expected: str) -> None:
        if self.channel()["id"] != expected:
            raise CreatorError("wrong_channel", "The authorized channel does not match the plan's channel.")

    def upload(self, path: str, title: str, channel_id: str, description: str = "", privacy: str = "private",
               category: str = "22", confirmation: str | None = None) -> dict:
        """Preview, or upload confirmed bytes once. Never retry an uncertain upload."""
        plan = prepare_upload(path, title, channel_id, description, privacy, category)
        if confirmation is None:
            return plan
        confirm_plan(plan, confirmation)
        self._owner(channel_id)
        self._write_scope("upload")
        from googleapiclient.http import MediaIoBaseUpload
        with media_snapshot(path) as (stream, info):
            confirm_plan({**plan, "file": info}, confirmation)
            media = MediaIoBaseUpload(stream, mimetype=info["mime_type"], chunksize=8 * 1024**2, resumable=True)
            claim_operation(confirmation)
            request = _provider_call(lambda: self._api().videos().insert(
                part="snippet,status", body=plan["body"], media_body=media, notifySubscribers=False))
            response = None
            # Bounded continuation of ONE resumable request, with SDK retries off.
            for _ in range(info["size"] // (8 * 1024**2) + 3):
                status, response = _provider_call(lambda: request.next_chunk(num_retries=0))
                if status and self._progress:
                    self._progress(status.progress())
                if response is not None:
                    break
            if not isinstance(response, dict) or not VIDEO_ID.fullmatch(response.get("id", "")):
                raise CreatorError("uncertain_write", "Upload outcome is uncertain. Inspect the channel; do not repeat the upload.")
            return {"id": response["id"], "status": "uploaded", "processing": "not verified",
                    "visibility": response.get("status", {}).get("privacyStatus", "not returned")}

    def update(self, item: str, title: str | None = None, description: str | None = None,
               confirmation: str | None = None) -> dict:
        """Preview a metadata patch; preserve the rest of snippet and all status fields."""
        if title is None and description is None:
            raise CreatorError("invalid_metadata", "Specify --title or --description for the metadata preview.")
        current = self._raw_video(item)
        snippet = current.get("snippet", {})
        channel = snippet.get("channelId", "")
        self._owner(channel)
        updated = {key: copy.deepcopy(snippet[key]) for key in SNIPPET_FIELDS if key in snippet}
        if title is not None:
            updated["title"] = title
        if description is not None:
            updated["description"] = description
        _metadata(updated.get("title", ""), updated.get("description", ""))
        if not current.get("etag") or not updated.get("categoryId"):
            raise CreatorError("incomplete_video", "The video lacks the ETag or category required for a safe metadata update.")
        plan = seal_plan({"schema_version": 1, "operation": "youtube.update", "channel_id": channel,
                          "etag": current["etag"], "before": {key: snippet[key] for key in SNIPPET_FIELDS if key in snippet},
                          "body": {"id": current["id"], "snippet": updated}})
        if confirmation is None:
            return plan
        confirm_plan(plan, confirmation)
        self._write_scope("update")
        claim_operation(confirmation)
        request = _provider_call(lambda: self._api().videos().update(part="snippet", body=plan["body"]))
        request.headers["If-Match"] = plan["etag"]
        result = _provider_call(lambda: request.execute(num_retries=0))
        if result.get("id") != current["id"] or any(result.get("snippet", {}).get(key) != value for key, value in updated.items()):
            raise CreatorError("uncertain_write", "Metadata update outcome is uncertain. Inspect the video before a new write.")
        return {"id": result["id"], "status": "updated", "snippet": result["snippet"]}

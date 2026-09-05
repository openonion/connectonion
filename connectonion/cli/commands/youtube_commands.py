"""Thin YouTube handlers; Google login matches Gmail and writes default to preview."""

import shlex

from .creator_commands import cache_listing, resolve_video, run
from ...useful_tools.creator_plan import CreatorError, confirm_plan
from ...useful_tools.youtube import YouTube, prepare_upload


def _client(progress=None) -> YouTube:
    return YouTube(progress=progress)


def handle_youtube_list(target: str | None = None, last: int = 20,
                        json_output: bool = False) -> None:
    def action():
        items = _client().list_videos(target, last)
        cache_listing(items)
        command = "co youtube video 1" if items else "co youtube channel"
        return {"mode": "read", "source": "youtube-data-api", "items": items}, command, f"Inspect one: {command}" if items else f"See your channel: {command}"
    run("youtube", action, json_output)


def handle_youtube_channel(target: str | None = None, json_output: bool = False) -> None:
    def action():
        item = _client().channel(target)
        command = f"co youtube list {item['id']}"
        return {"mode": "read", "channel": item}, command, f"List this channel: {command}"
    run("youtube", action, json_output)


def handle_youtube_video(item: str, json_output: bool = False) -> None:
    def action():
        identity = resolve_video(item)
        video = _client().video(identity)
        channel = video.get("channel_id")
        command = f"co youtube channel {channel}" if channel else "co youtube channel"
        return {"mode": "read", "video": video}, command, f"See its channel: {command}"
    run("youtube", action, json_output)


def handle_youtube_put(path: str, title: str, channel: str, description: str = "", privacy: str = "private",
                       category: str = "22", dry_run: bool = False, confirm: str | None = None,
                       json_output: bool = False) -> None:
    def action():
        if dry_run and confirm is not None:
            raise CreatorError("conflicting_mode", "--dry-run and --confirm cannot be combined.")
        if confirm is None:
            plan = prepare_upload(path, title, channel, description, privacy, category)
            command = shlex.join([
                "co", "youtube", "put", plan["file"]["path"], "--title", title,
                "--channel", channel, "--description", description, "--privacy", privacy,
                "--category", category, "--confirm", plan["confirmation"],
            ])
            return {"mode": "preview", "plan": plan, "quota_remaining": None,
                    "note": "Local preview only. Account, quota, media validity and API approval are not verified."}, command, f"After the user approves this plan, upload with: {command}"
        import sys
        confirm_plan(prepare_upload(path, title, channel, description, privacy, category), confirm)
        client = _client(progress=lambda value: print(f"Upload: {value:.0%}", file=sys.stderr))
        result = client.upload(path, title, channel, description, privacy, category, confirmation=confirm)
        command = f"co youtube video {result['id']}"
        return {"mode": "write", "result": result}, command, f"Inspect the upload: {command}"
    run("youtube", action, json_output, recovery="co youtube list")


def handle_youtube_update(item: str, title: str | None = None, description: str | None = None,
                          dry_run: bool = False, confirm: str | None = None,
                          json_output: bool = False) -> None:
    def action():
        if dry_run and confirm is not None:
            raise CreatorError("conflicting_mode", "--dry-run and --confirm cannot be combined.")
        identity = resolve_video(item)
        result = _client().update(identity, title, description, confirmation=confirm)
        if confirm:
            command = f"co youtube video {identity}"
            tip = f"Inspect the update: {command}"
        else:
            arguments = ["co", "youtube", "update", identity]
            if title is not None:
                arguments.extend(["--title", title])
            if description is not None:
                arguments.extend(["--description", description])
            command = shlex.join([*arguments, "--confirm", result["confirmation"]])
            tip = f"After the user approves this plan, update with: {command}"
        return {"mode": "write" if confirm else "preview", "result" if confirm else "plan": result}, command, tip
    run("youtube", action, json_output, recovery="co youtube list")

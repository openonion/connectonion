# YouTube

`YouTube` uses the official Data API with the Google login saved by
`co auth google --youtube`. Credentials refresh through the same broker as Gmail.

```python
from connectonion import YouTube

youtube = YouTube()
channel = youtube.channel()
videos = youtube.list_videos(last=20)
video = youtube.video("https://youtu.be/Abcdefgh_01")

# Reads metadata and returns a plan; no update request is made.
plan = youtube.update(video["id"], title="A reviewed title")
```

`upload(path, title, channel_id, ...)` and `update(item, title=None,
description=None, ...)` return a plan by default. Calling them with
`confirmation=<current digest>` performs an external write, with the same
ownership, file-snapshot, ETag and single-attempt receipt guards as the CLI.
The application must obtain the user's concrete approval before supplying a
confirmation; a digest alone is not evidence that a human approved an action.

For a completely offline upload preview, use
`connectonion.useful_tools.youtube.prepare_upload(path, title, channel_id)`
without constructing a client. `CreatorError` exposes a fixed `code` and a
sanitized message; provider bodies and SDK credential locals are suppressed.
No delete, comment, download, search or analytics methods are exposed.

An application can pass `progress=callback` to the constructor to receive
resumable upload fractions. The CLI writes progress only to stderr. See
[CLI authentication, output and confirmation details](../cli/youtube.md).

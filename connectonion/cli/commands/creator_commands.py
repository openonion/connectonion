"""Shared rendering and minimal last-list numbering."""

import json
import os
import re
import tempfile
from pathlib import Path
from typing import Callable

import typer
from rich.console import Console
from rich.table import Table
from rich.text import Text

from ...useful_tools.creator_plan import CreatorError

console = Console()


def _cache() -> Path:
    return Path.home() / ".co" / "youtube_last_list.json"


def cache_listing(items: list[dict]) -> None:
    if not items:
        return
    path = _cache()
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor, temporary = tempfile.mkstemp(dir=path.parent, prefix=".youtube-list-")
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump({str(i): item["id"] for i, item in enumerate(items, 1)}, stream)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def resolve_video(value: str) -> str:
    from ...useful_tools.youtube import video_id
    number = value.removeprefix("#")
    if number.isascii() and number.isdigit() and len(number) < 5:
        try:
            data = json.loads(_cache().read_text(encoding="utf-8"))
            resolved = data.get(number) if isinstance(data, dict) else None
            if not isinstance(resolved, str):
                raise ValueError
            return video_id(resolved)
        except (OSError, ValueError):
            raise CreatorError("stale_number", "That number is absent from the last listing; list videos again.") from None
    return video_id(value)


def _text(value) -> str:
    value = "not returned" if value is None else str(value)
    return re.sub(r"[\x00-\x1f\x7f-\x9f]", " ", value)


def render(result: dict, json_output: bool) -> None:
    """JSON is one object; terminal and pipe output always end with one tip."""
    if json_output:
        print(json.dumps(result, ensure_ascii=True))
        return
    items = result.get("items")
    if items is not None:
        if console.is_terminal:
            table = Table("#", "Video ID", "Title", "Visibility", "Views")
            for i, item in enumerate(items, 1):
                table.add_row(*(Text(_text(value)) for value in [i, item["id"], item.get("title"),
                                                               item.get("visibility"), item.get("views")]))
            console.print(table)
        else:
            for i, item in enumerate(items, 1):
                print("\t".join(_text(value) for value in [i, item["id"], item.get("title"),
                                                          item.get("visibility"), item.get("views")]))
        if not items:
            print("No videos returned.")
    for key, value in result.items():
        if key not in {"items", "next_command", "next_tip"}:
            rendered = json.dumps(value, ensure_ascii=True) if isinstance(value, (dict, list)) else _text(value)
            if console.is_terminal:
                console.print(f"{key}: {rendered}", markup=False, highlight=False)
            else:
                print(f"{key}\t{rendered}")
    print(result["next_tip"])


def run(provider: str, action: Callable[[], tuple[dict, str, str]], json_output: bool = False,
        recovery: str | None = None) -> None:
    """Fixed error vocabulary prevents SDK bodies and tracebacks reaching stdout."""
    try:
        result, command, tip = action()
    except (CreatorError, OSError) as error:
        code = error.code if isinstance(error, CreatorError) else "local_io"
        message = str(error) if isinstance(error, CreatorError) else "Cannot access local evidence, cache, or operation receipt."
        command = recovery or f"co {provider} --help"
        if code == "auth_required":
            command = "co auth google"
        elif code in {"invalid_metadata", "invalid_file", "invalid_target"}:
            command = f"co {provider} --help"
        elif code == "stale_number":
            command = "co youtube list"
        result, tip = {"ok": False, "code": code, "message": message}, f"Next: {command}"
    except Exception:
        # An unexpected provider/browser response can contain secrets in the
        # exception text. Do not expose it or reinterpret it as an empty result.
        command = recovery or f"co {provider} --help"
        result, tip = {"ok": False, "code": "unexpected_response", "message": "Unexpected response; details withheld. No automatic retry was made."}, f"Next: {command}"
    result = {"ok": True, **result, "next_command": command, "next_tip": tip}
    render(result, json_output)
    if not result["ok"]:
        raise typer.Exit(1)

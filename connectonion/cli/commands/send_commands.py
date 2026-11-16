"""`co send` and `co receive`: files between agents, over network/file_send.py.

`co send <address> <path>...` sends files, and folders as the files inside
them, to another agent's running Host. `co receive` lists what this agent's
Host has received and verified.
"""

import asyncio
import json
import sys
from pathlib import Path


def _human(size: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.1f} {unit}" if unit != "B" else f"{size} B"
        size /= 1024


def _files(paths: list[str]) -> list[tuple[Path, str]]:
    """(file, name it lands under) for each file; a folder keeps its own name on top."""
    found = []
    for raw in paths:
        path = Path(raw).expanduser()
        if path.is_file():
            found.append((path, path.name))
        elif path.is_dir():
            base = path.resolve().parent
            found += [(f, f.resolve().relative_to(base).as_posix())
                      for f in sorted(path.rglob("*")) if f.is_file() and not f.is_symlink()]
        else:
            raise SystemExit(f"co send: {raw}: no such file or folder")
    return found


def _progress(label: str):
    last = [0.0]

    def show(phase, done, total):
        import time
        now = time.monotonic()
        if now - last[0] < 0.5 and done < total:
            return
        last[0] = now
        percent = f"{done * 100 // total}%" if total else "100%"
        print(f"\r{label}: {phase} {_human(done)} / {_human(total)} ({percent})   ",
              end="", file=sys.stderr, flush=True)
    return show


def handle_send(address: str, paths: list[str], relay_url: str | None) -> int:
    from connectonion import connect
    from connectonion.network.connect import _this_callers_identity
    from connectonion.network.file_send import SendRefused, send_file

    files = _files(paths)
    kwargs = {"keys": _this_callers_identity()}
    if relay_url:
        kwargs["relay_url"] = relay_url
    remote = connect(address, **kwargs)
    for path, name in files:
        try:
            stored = asyncio.run(send_file(remote, path, name, _progress(name)))
        except SendRefused as refused:
            print(f"\nco send: {name}: {refused}", file=sys.stderr)
            return 1
        except KeyboardInterrupt:
            print(f"\nco send: stopped. The receiver keeps what arrived; run the same "
                  "command again to continue from there.", file=sys.stderr)
            return 130
        print(file=sys.stderr)
        print(f"{name}  {_human(stored['size'])}  sha256 {stored['sha256'][:12]}…  "
              f"stored as {stored['path']}")
    return 0


def handle_receive(as_json: bool) -> int:
    from connectonion.network.host.file_inbox import files_dir, received
    from connectonion.project import project_co_dir

    co_dir = project_co_dir()
    entries = received(co_dir)
    if as_json:
        print(json.dumps(entries))
        return 0
    if not entries:
        print(f"Nothing received yet. Files other agents send land in {files_dir(co_dir)}/")
        return 0
    for entry in entries:
        print(f"{entry['path']}  {_human(entry['size'])}  from {entry['from'][:10]}…  "
              f"sha256 {entry['sha256'][:12]}… verified")
    print(f"\nin {files_dir(co_dir)}/")
    return 0

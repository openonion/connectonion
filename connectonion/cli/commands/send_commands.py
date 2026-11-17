"""`co send` and `co receive`: files between agents, over network/file_send.py.

`co send <address> <path>...` sends files, and folders as the files inside
them, to another agent's running Host. When that Host cannot be reached
directly, a file of up to 10 MB waits on the backend for a week instead
(network/file_stash.py). `co receive` takes what is waiting, then lists what
this agent has received and verified.
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
    from connectonion.network.file_send import NotDirect, SendRefused, send_file

    files = _files(paths)
    keys = _this_callers_identity()
    kwargs = {"keys": keys}
    if relay_url:
        kwargs["relay_url"] = relay_url
    remote = connect(address, **kwargs)
    direct = True
    for path, name in files:
        try:
            if direct:
                stored = asyncio.run(send_file(remote, path, name, _progress(name)))
                print(file=sys.stderr)
                print(f"{name}  {_human(stored['size'])}  sha256 {stored['sha256'][:12]}…  "
                      f"stored as {stored['path']}")
                continue
        except NotDirect as not_direct:
            print(f"\nco send: {not_direct}", file=sys.stderr)
            direct = False
        except SendRefused as refused:
            print(f"\nco send: {name}: {refused}", file=sys.stderr)
            return 1
        except KeyboardInterrupt:
            print(f"\nco send: stopped. The receiver keeps what arrived; run the same "
                  "command again to continue from there.", file=sys.stderr)
            return 130
        if not _leave(keys, remote.address, path, name):
            return 1
    return 0


def _leave(keys, to_address: str, path: Path, name: str) -> bool:
    """Leave one file waiting on the backend; False when it cannot."""
    from connectonion.network.file_send import SendRefused
    from connectonion.network.file_stash import KEPT_DAYS, STASH_BYTES, leave

    size = path.stat().st_size
    if size > STASH_BYTES:
        print(f"co send: {name} is {_human(size)}; only files up to {_human(STASH_BYTES)} can wait "
              "for the receiver. Send it when its Host is reachable: same network, or a public address.",
              file=sys.stderr)
        return False
    try:
        left = leave(keys, to_address, path, name)
    except SendRefused as refused:
        print(f"co send: {name}: {refused}", file=sys.stderr)
        return False
    print(f"{name}  {_human(size)}  sha256 {left['sha256'][:12]}…  waiting for the receiver, "
          f"encrypted to it, for {KEPT_DAYS} days; `co receive` there takes it, "
          "and it is deleted once taken or when the days are up")
    return True


def handle_receive(as_json: bool) -> int:
    from connectonion.network.connect import _this_callers_identity
    from connectonion.network.file_stash import collect
    from connectonion.network.host.file_inbox import files_dir, received
    from connectonion.project import project_co_dir

    co_dir = project_co_dir()
    taken = collect(_this_callers_identity(), co_dir)
    entries = received(co_dir)
    if as_json:
        print(json.dumps({"files": entries, **taken}))
        return 0
    _say_collected(taken)
    if not entries:
        print(f"Nothing received yet. Files other agents send land in {files_dir(co_dir)}/")
        return 0
    for entry in entries:
        print(f"{entry['path']}  {_human(entry['size'])}  from {entry['from'][:10]}…  "
              f"sha256 {entry['sha256'][:12]}… verified")
    print(f"\nin {files_dir(co_dir)}/")
    return 0


def _say_collected(taken: dict) -> None:
    for entry in taken["landed"]:
        print(f"took {entry['path']} from {entry['from'][:10]}…, which was waiting on the backend", file=sys.stderr)
    for entry in taken["refused"]:
        print(f"refused a file from {entry['from'][:10]}…: {entry['reason']}", file=sys.stderr)
    for entry in taken["waiting"]:
        print(f"a file ({_human(entry['size'])}) from {entry['from'][:10]}… is waiting, but that sender is not "
              f"a contact; `co trust add {entry['from']}` and run co receive again to take it "
              f"(it is deleted on {entry['expires_at'][:10]})", file=sys.stderr)

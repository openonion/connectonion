"""Disposable HTML view of the notebook. Markdown stays the store; this is a snapshot.

A page opened from file:// cannot read the Markdown next to it (browsers block
fetch from file URLs), so the notebook is embedded into one self-contained HTML
file at render time. The template is a plain client of that embedded object; a
served site later would hand it the same object over HTTP instead.
"""

import hashlib
import json
import os
import re
import sys
import tempfile
import webbrowser
from datetime import datetime, timezone
from pathlib import Path

from .files import CATEGORIES, Notebook
from .service import run_logs, status, subscriptions

TEMPLATE = Path(__file__).with_name("reader.html")
PLACEHOLDER = "/*__WIKI_DATA__*/null"


def _title(record: str, text: str) -> str:
    for line in text.splitlines():
        if line.startswith("#"):
            return line.lstrip("#").strip() or record
    return Path(record).stem.replace("-", " ")


def snapshot(root: Path) -> dict:
    """Everything the page shows, read once; no model, no writes into the notebook."""
    from .reviews import listing
    notebook = Notebook(root)
    records = []
    for record in notebook.list():
        text = notebook.read(record)
        updated = datetime.fromtimestamp(notebook.path(record).stat().st_mtime, timezone.utc)
        records.append({"path": record, "category": record.split("/")[0],
                        "title": _title(record, text) + (" (automated candidate)" if "- Correspondent classification: automated candidate;" in text else ""), "text": text,
                        "updated": updated.isoformat(timespec="seconds")})
    groups = {}
    for record in records:
        if record["path"].startswith("skills/catalog/") and record["path"] != "skills/catalog/index.md":
            source = re.search(r"^- File: (.+)$", record["text"], re.MULTILINE)
            if source:
                record["installation"] = source.group(1)
                groups.setdefault(record["title"].casefold(), []).append(record)
    for group in groups.values():
        first = group[0]
        first["installations"] = [{"path": r["path"], "source": r["installation"]} for r in group]
        for other in group[1:]:
            other["catalog_parent"] = first["path"]
    return {"as_of": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "root": str(root), "categories": list(CATEGORIES), "records": records,
            "status": status(root), "subscriptions": subscriptions(root),
            "logs": run_logs(root)[:20], "reviews": listing(root)}


def render(root: Path) -> str:
    data = json.dumps(snapshot(root), ensure_ascii=False)
    # Inside a script block only "</script" and the U+2028/9 terminators can break
    # out. Escaping "<" as \u003c keeps the JSON valid and makes note text inert.
    data = data.replace("<", "\\u003c").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")
    template = TEMPLATE.read_text(encoding="utf-8")
    if PLACEHOLDER not in template:
        raise RuntimeError("reader.html has lost its data placeholder")
    return template.replace(PLACEHOLDER, data, 1)


def reader_path(root: Path) -> Path:
    """Outside the notebook, so nothing under root changes and no collector meets it."""
    digest = hashlib.sha256(str(Path(root).resolve()).encode()).hexdigest()[:12]
    return Path(tempfile.gettempdir()) / f"co-wiki-{digest}.html"


def _open_windows_snapshot(path: Path) -> int:
    """Open the snapshot itself, never the target of a reparse point."""
    import ctypes
    import errno
    import msvcrt
    from ctypes import wintypes

    class FileInformation(ctypes.Structure):
        _fields_ = [("dwFileAttributes", wintypes.DWORD), ("ftCreationTime", wintypes.FILETIME),
                    ("ftLastAccessTime", wintypes.FILETIME), ("ftLastWriteTime", wintypes.FILETIME),
                    ("dwVolumeSerialNumber", wintypes.DWORD), ("nFileSizeHigh", wintypes.DWORD),
                    ("nFileSizeLow", wintypes.DWORD), ("nNumberOfLinks", wintypes.DWORD),
                    ("nFileIndexHigh", wintypes.DWORD), ("nFileIndexLow", wintypes.DWORD)]

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    create = kernel32.CreateFileW
    create.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID,
                       wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    create.restype = wintypes.HANDLE
    information = kernel32.GetFileInformationByHandle
    information.argtypes = [wintypes.HANDLE, ctypes.POINTER(FileInformation)]
    information.restype = wintypes.BOOL
    rewind = kernel32.SetFilePointerEx
    rewind.argtypes = [wintypes.HANDLE, ctypes.c_longlong, wintypes.LPVOID, wintypes.DWORD]
    rewind.restype = wintypes.BOOL
    truncate = kernel32.SetEndOfFile
    truncate.argtypes = [wintypes.HANDLE]
    truncate.restype = wintypes.BOOL
    close = kernel32.CloseHandle
    close.argtypes = [wintypes.HANDLE]
    close.restype = wintypes.BOOL

    generic_write, open_always, file_attribute_normal = 0x40000000, 4, 0x80
    file_flag_open_reparse_point, file_attribute_reparse_point = 0x00200000, 0x400
    invalid_handle = ctypes.c_void_p(-1).value
    handle = create(str(path), generic_write, 0, None, open_always,
                    file_attribute_normal | file_flag_open_reparse_point, None)
    if handle == invalid_handle:
        raise OSError(ctypes.get_last_error(), "CreateFileW failed", path)
    try:
        details = FileInformation()
        if not information(handle, ctypes.byref(details)):
            raise OSError(ctypes.get_last_error(), "GetFileInformationByHandle failed", path)
        if details.dwFileAttributes & file_attribute_reparse_point:
            raise OSError(errno.ELOOP, "refusing to write through a reparse point", path)
        if not rewind(handle, 0, None, 0) or not truncate(handle):
            raise OSError(ctypes.get_last_error(), "could not truncate snapshot", path)
        fd = msvcrt.open_osfhandle(handle, os.O_WRONLY | os.O_BINARY)
        handle = None  # ownership moved to the CRT file descriptor
        return fd
    finally:
        if handle is not None:
            close(handle)


def write_reader(root: Path) -> Path:
    page = render(root)
    path = reader_path(root)
    # The name is predictable; refuse to write through a link someone planted there.
    if sys.platform == "win32":
        fd = _open_windows_snapshot(path)
    else:
        flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW
        fd = os.open(path, flags, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as output:
        output.write(page)
    # Windows ACLs, not POSIX file modes, protect this temporary snapshot.
    if sys.platform != "win32":
        os.chmod(path, 0o600)
    return path


def open_reader(root: Path, *, launch: bool = True) -> Path:
    path = write_reader(root)
    if launch:
        webbrowser.open(path.as_uri())
    return path


# The live view: O Chat reads the default notebook from the owner's `co ai` Host
# over OIP (`WIKI_READ`, #1637). The route and whether it exists live here only.
LIVE_WIKI_URL = "https://chat.openonion.ai/{address}/wiki"

# Does O Chat serve LIVE_WIKI_URL? Yes since openonion/oo-chat#246 was deployed
# (2026-09-27); before that /<address>/wiki was read as a chat session named
# "wiki", which is how `co wiki open` came to open a page that never loads (#1828).
LIVE_WIKI_SERVED = True

# Is the live view what a bare `co wiki open` opens? No, by the owner's decision
# (2026-09-27, #1828): opening locally is the default and works offline; the
# live view through the Host is a feature asked for with --live.
LIVE_IS_DEFAULT = False

LIVE_HINT = "co wiki open --live   (the live view in O Chat; needs your co ai Host online)"


def host_online(address: str, timeout: float = 3.0) -> bool:
    """Is the Host for this address answering right now? No model, no login.

    Online is what a client can connect to: the relay holds the Host's announce
    socket (how O Chat reaches a Host behind NAT or on another machine), or,
    failing that, an announced endpoint answers /info as that address -- the
    same two routes connect() takes. The whole check is bounded by `timeout`;
    no answer in time reads as offline and costs a snapshot, never a dead page.
    """
    import asyncio
    import importlib
    from ..backend import backend_ws_url
    # By import_module: connectonion.network re-exports a connect() that shadows the module.
    connect = importlib.import_module("connectonion.network.connect")
    relay = backend_ws_url()

    async def check() -> bool:
        if await connect.relay_presence(address, relay, timeout):
            return True
        return await connect.resolve_endpoint(address, relay, timeout) is not None

    async def bounded() -> bool:
        try:
            return await asyncio.wait_for(check(), timeout)
        except asyncio.TimeoutError:
            return False
    return asyncio.run(bounded())


def open_snapshot(root: Path, *, launch: bool, **notes) -> dict:
    path = open_reader(root, launch=launch)
    return {"page": str(path), "link": path.as_uri(), "launched": launch,
            "note": "local snapshot; run again after the next maintenance pass", **notes}


def live_or_snapshot(root: Path, address, *, live: bool, launch: bool) -> dict:
    """What `co wiki open` shows: the live view only when it is wanted, belongs to
    this notebook, and its Host answers; otherwise the snapshot, saying why."""
    if not live:
        return open_snapshot(root, launch=launch, **({"live_view": LIVE_HINT} if address else {}))
    if not address:
        return open_snapshot(root, launch=launch, live=(
            "only the default notebook (~/.co/wiki) with a co ai identity has a live view"))
    if not host_online(address):
        return open_snapshot(root, launch=launch, live=(
            f"your Host {address[:10]}... is not online, so the live view would not load. "
            "Start it with `co ai`, then run `co wiki open --live` again"))
    url = LIVE_WIKI_URL.format(address=address)
    if launch:
        webbrowser.open(url)
    result = {"page": url, "link": url, "launched": launch}
    if not LIVE_WIKI_SERVED:
        result["warning"] = ("O Chat does not serve this route yet (openonion/oo-chat#246); "
                             "until it is deployed the page opens as an empty chat")
    return result

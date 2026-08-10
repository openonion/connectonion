"""Small cross-platform primitives for attachment file authorization."""

import os
from pathlib import Path


def path_of_open_file(handle) -> Path:
    """Return the OS-reported final path for an already-open file handle."""
    import sys

    descriptor = handle.fileno()
    if os.name == "nt":
        import ctypes
        import msvcrt

        buffer = ctypes.create_unicode_buffer(32768)
        length = ctypes.windll.kernel32.GetFinalPathNameByHandleW(
            ctypes.c_void_p(msvcrt.get_osfhandle(descriptor)), buffer, len(buffer), 0
        )
        if not length or length >= len(buffer):
            raise OSError("Windows could not resolve the open attachment handle")
        path = buffer.value
        if path.startswith("\\\\?\\UNC\\"):
            path = "\\\\" + path[8:]
        elif path.startswith("\\\\?\\"):
            path = path[4:]
        return Path(path)

    if sys.platform == "darwin":
        import fcntl

        raw = fcntl.fcntl(descriptor, fcntl.F_GETPATH, bytes(1024))
        return Path(raw.split(bytes(1), 1)[0].decode())

    proc_path = Path(f"/proc/self/fd/{descriptor}")
    if proc_path.exists():
        return Path(os.readlink(proc_path))
    raise OSError("This platform cannot resolve an open attachment handle")

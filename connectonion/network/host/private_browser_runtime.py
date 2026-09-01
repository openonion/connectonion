"""Host-private BrowserDaemon target and fail-closed launch-policy factory."""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import tempfile
from dataclasses import dataclass
from pathlib import Path

from ...cli.browser_agent import transport
from ...useful_tools.browser_tools.browser_config import (
    CHROME_DEFAULT_ARGS,
    IGNORE_DEFAULT_ARGS,
)
from ...useful_tools.browser_tools.launch_policy import (
    BrowserLaunchPolicy,
    BrowserProxySettings,
)
from ..proxy_egress import ShareEndpoint
from .egress_gateway import ProxyEndpoint

# Every entry here is a switch the launched binary actually defines. A switch
# Chromium does not recognise is ignored in silence, which makes a misspelling
# indistinguishable from a working control: `--force-webrtc-ip-handling-policy`
# appears nowhere in Chrome 151 and left non-proxied UDP fully available, so a
# page could still open direct UDP sockets past this gateway. The spelling below
# is the one present in the binary, and BrowserLaunchPolicy now refuses a
# policy that omits any of REQUIRED_EGRESS_ARGS.
REMOTE_BROWSER_CHROME_ARGS = (
    *CHROME_DEFAULT_ARGS,
    "--proxy-bypass-list=<-loopback>",
    "--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE 127.0.0.1",
    "--disable-quic",
    "--webrtc-ip-handling-policy=disable_non_proxied_udp",
    "--disable-extensions",
)
PROXY_AUTH_FILENAME = "proxy-auth.json"
SHARED_PROXY_FILENAME = "shared-proxy.json"
PROXY_AUTH_REALM = "ConnectOnion Remote Browser"
PROXY_AUTH_USERNAME = "connectonion"
_PROXY_AUTH_PASSWORD = re.compile(r"[A-Za-z0-9_-]{43}\Z")


@dataclass(frozen=True)
class PrivateBrowserTarget:
    """Non-secret paths and mode passed from the Host to its daemon client."""

    address: str
    profile_dir: Path
    log_path: Path
    authkey_path: Path
    proxy_auth_path: Path | None = None
    shared_proxy_path: Path | None = None
    remote_egress: bool = True

    @classmethod
    def from_state_path(cls, state_path: Path) -> "PrivateBrowserTarget":
        state_path = Path(state_path).expanduser().resolve()
        namespace = hashlib.sha256(str(state_path).encode("utf-8")).hexdigest()[:20]
        root = state_path.parent / "remote-browser-runtime" / namespace
        root.mkdir(parents=True, exist_ok=True)
        if os.name != "nt":
            os.chmod(root, 0o700)
        return cls(
            address=transport.namespaced_address(f"remote-{namespace}"),
            profile_dir=root / "profile",
            log_path=root / "browser.log",
            authkey_path=root / "authkey",
            proxy_auth_path=root / PROXY_AUTH_FILENAME,
            shared_proxy_path=root / SHARED_PROXY_FILENAME,
        )


def _canonical_share_endpoint(value: dict) -> ShareEndpoint:
    """Validate one Laptop Proxy endpoint before it can affect a WTF runtime."""
    if not isinstance(value, dict):
        raise ValueError("shared proxy endpoint must be an object")
    try:
        host = value["host"]
        port = value["port"]
        username = value["username"]
        password = value["password"]
    except KeyError as exc:
        raise ValueError("shared proxy endpoint is incomplete") from exc
    if (
        not isinstance(host, str)
        or not host
        or len(host) > 253
        or any(ord(char) < 0x21 or ord(char) > 0x7E for char in host)
        or isinstance(port, bool)
        or not isinstance(port, int)
        or not 1 <= port <= 65535
        or not isinstance(username, str)
        or not username
        or len(username) > 256
        or ":" in username
        or not isinstance(password, str)
        or not password
        or len(password) > 256
        or any(ord(char) < 0x21 or ord(char) > 0x7E for char in username + password)
    ):
        raise ValueError("shared proxy endpoint is invalid")
    return ShareEndpoint(host, port, username, password)


def write_shared_proxy_file(path: Path, endpoint: ShareEndpoint) -> Path:
    """Atomically bind a private Remote Browser runtime to one Laptop exit."""
    path = Path(path).expanduser()
    payload = {
        "host": endpoint.host,
        "password": endpoint.password,
        "port": endpoint.port,
        "username": endpoint.username,
        "v": 1,
    }
    # Reuse the validation path for both callers and later daemon reads.
    _canonical_share_endpoint(payload)
    if not path.is_absolute() or not path.parent.is_dir() or path.parent.is_symlink():
        raise ValueError("shared proxy path must be absolute in a private runtime")
    if os.name != "nt":
        parent_stat = path.parent.stat()
        if stat.S_IMODE(parent_stat.st_mode) & 0o077 or parent_stat.st_uid != os.getuid():
            raise ValueError("shared proxy root must be private and owned by this user")
    body = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("ascii")
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb", dir=path.parent, prefix=f".{path.name}.", delete=False
        ) as stream:
            temporary = Path(stream.name)
            if os.name != "nt":
                os.chmod(temporary, 0o600)
            stream.write(body)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        temporary = None
        return path
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def load_shared_proxy_file(path: Path) -> ShareEndpoint:
    """Load the Laptop exit selected by the Remote Browser authority process."""
    path = Path(path).expanduser()
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
        with os.fdopen(descriptor, "rb") as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_size > 4096:
                raise ValueError("shared proxy file is not a bounded regular file")
            if os.name != "nt" and (
                stat.S_IMODE(info.st_mode) & 0o077 or info.st_uid != os.getuid()
            ):
                raise ValueError("shared proxy file must be private and owned")
            body = stream.read(4097)
        if len(body) > 4096:
            raise ValueError("shared proxy file is not a bounded regular file")
        value = json.loads(body.decode("ascii"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("shared proxy file is unreadable") from exc
    if value.get("v") != 1 or set(value) != {"host", "password", "port", "username", "v"}:
        raise ValueError("shared proxy file has an unknown format")
    return _canonical_share_endpoint(value)


def canonical_proxy_auth(endpoint: ProxyEndpoint) -> bytes:
    """Return the exact credential document accepted by the closed browser."""
    if (
        endpoint.host != "127.0.0.1"
        or isinstance(endpoint.port, bool)
        or not isinstance(endpoint.port, int)
        or not 1 <= endpoint.port <= 65535
        or endpoint.username != PROXY_AUTH_USERNAME
        or not isinstance(endpoint.password, str)
        or not _PROXY_AUTH_PASSWORD.fullmatch(endpoint.password)
    ):
        raise ValueError("native proxy credentials are not canonical")
    body = {
        "challenger": f"127.0.0.1:{endpoint.port}",
        "password": endpoint.password,
        "realm": PROXY_AUTH_REALM,
        "scheme": "basic",
        "username": PROXY_AUTH_USERNAME,
        "v": 1,
    }
    return json.dumps(body, sort_keys=True, separators=(",", ":")).encode("ascii")


def proxy_auth_path_for_profile(profile_dir: Path) -> Path:
    """Keep the credential beside, never inside, the persistent profile."""
    profile = Path(profile_dir).expanduser().resolve()
    return profile.parent / PROXY_AUTH_FILENAME


def write_proxy_auth_file(path: Path, endpoint: ProxyEndpoint) -> Path:
    """Atomically create a mode-0600 credential in an existing private root."""
    path = Path(path).expanduser()
    if not path.is_absolute() or not path.parent.is_dir() or path.parent.is_symlink():
        raise ValueError("proxy auth path must be absolute in an existing private root")
    if os.name != "nt":
        parent_stat = path.parent.stat()
        if (
            stat.S_IMODE(parent_stat.st_mode) & 0o077
            or parent_stat.st_uid != os.getuid()
        ):
            raise ValueError("proxy auth root must be private and owned by this user")
    payload = canonical_proxy_auth(endpoint)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=path.parent,
            prefix=f".{path.name}.",
            delete=False,
        ) as stream:
            temporary = Path(stream.name)
            if os.name != "nt":
                os.chmod(temporary, 0o600)
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        temporary = None
        return path
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def remove_proxy_auth_file(path: Path | None) -> None:
    """Remove the private credential without following a replacement symlink."""
    if path is not None:
        Path(path).unlink(missing_ok=True)


def remote_browser_launch_policy(
    profile_dir: Path,
    endpoint: ProxyEndpoint,
    proxy_auth_path: Path,
) -> BrowserLaunchPolicy:
    """Bind one gateway endpoint to the exact requested private launch contract."""
    canonical_proxy_auth(endpoint)
    proxy_auth_path = Path(proxy_auth_path).expanduser()
    proxy_auth_switch = f"--connectonion-proxy-auth-file={proxy_auth_path}"
    return BrowserLaunchPolicy(
        profile_dir=profile_dir,
        proxy=BrowserProxySettings(server=f"http://{endpoint.host}:{endpoint.port}"),
        proxy_auth_file=proxy_auth_path,
        args=(*REMOTE_BROWSER_CHROME_ARGS, proxy_auth_switch),
        ignore_default_args=tuple(IGNORE_DEFAULT_ARGS) + ("--use-mock-keychain",),
        service_workers="block",
        accept_downloads=True,
        native_preflight="remote-egress-v1",
    )

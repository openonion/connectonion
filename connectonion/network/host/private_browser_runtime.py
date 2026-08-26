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
from .egress_gateway import ProxyEndpoint

REMOTE_BROWSER_CHROME_ARGS = (
    *CHROME_DEFAULT_ARGS,
    "--proxy-bypass-list=<-loopback>",
    "--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE 127.0.0.1",
    "--disable-quic",
    "--force-webrtc-ip-handling-policy=disable_non_proxied_udp",
    "--disable-extensions",
)
PROXY_AUTH_FILENAME = "proxy-auth.json"
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
        )


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

"""Host-private BrowserDaemon target and fail-closed launch-policy factory."""

from __future__ import annotations

import hashlib
import os
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


@dataclass(frozen=True)
class PrivateBrowserTarget:
    """Non-secret paths and mode passed from the Host to its daemon client."""

    address: str
    profile_dir: Path
    log_path: Path
    authkey_path: Path
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
        )


def remote_browser_launch_policy(profile_dir: Path, endpoint: ProxyEndpoint) -> BrowserLaunchPolicy:
    """Bind one gateway endpoint to the exact requested private launch contract."""
    return BrowserLaunchPolicy(
        profile_dir=profile_dir,
        proxy=BrowserProxySettings(
            server=f"http://{endpoint.host}:{endpoint.port}",
            username=endpoint.username,
            password=endpoint.password,
        ),
        args=REMOTE_BROWSER_CHROME_ARGS,
        ignore_default_args=tuple(IGNORE_DEFAULT_ARGS) + ("--use-mock-keychain",),
        service_workers="block",
        accept_downloads=True,
        native_preflight="remote-egress-v1",
    )

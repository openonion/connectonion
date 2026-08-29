"""Explicit, immutable browser launch inputs for policy-owned runtimes.

The ordinary local browser keeps its environment-compatible launch path.  A
Host-private runtime instead receives one of these values directly so proxy and
profile authority cannot drift through process environment variables.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit


@dataclass(frozen=True)
class BrowserProxySettings:
    """Playwright proxy settings whose credential is safe to repr or log."""

    server: str
    username: str
    password: str = field(repr=False)

    def __post_init__(self) -> None:
        try:
            parsed = urlsplit(self.server)
            port = parsed.port
        except (TypeError, ValueError):
            parsed, port = None, None
        if not (
            parsed is not None
            and parsed.scheme == "http"
            and parsed.hostname == "127.0.0.1"
            and parsed.username is None
            and parsed.password is None
            and parsed.path == ""
            and parsed.query == ""
            and parsed.fragment == ""
            and port is not None
            and parsed.netloc == f"127.0.0.1:{port}"
            and isinstance(self.username, str)
            and isinstance(self.password, str)
            and self.username
            and self.password
        ):
            raise ValueError("browser proxy must be one authenticated loopback server")

    def playwright_value(self) -> dict[str, str]:
        return {
            "server": self.server,
            "username": self.username,
            "password": self.password,
        }


# The switches that make a private policy fail closed. Held here rather than
# only in the caller's constant, because a policy that pins a proxy while
# leaving the browser free to bypass it, resolve names itself, or open QUIC and
# WebRTC UDP sockets is not a boundary — and it validated fine when the only
# check was "the constant equals itself".
REQUIRED_EGRESS_ARGS = (
    "--proxy-bypass-list=<-loopback>",
    "--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE 127.0.0.1",
    "--disable-quic",
    "--webrtc-ip-handling-policy=disable_non_proxied_udp",
)


@dataclass(frozen=True)
class BrowserLaunchPolicy:
    """Complete non-environment launch inputs for one private browser context."""

    profile_dir: Path
    proxy: BrowserProxySettings
    args: tuple[str, ...]
    ignore_default_args: tuple[str, ...] = ()
    service_workers: Literal["allow", "block"] = "block"
    accept_downloads: bool = True

    def __post_init__(self) -> None:
        profile = Path(self.profile_dir).expanduser().resolve()
        object.__setattr__(self, "profile_dir", profile)
        if not self.args or len(set(self.args)) != len(self.args):
            raise ValueError("browser launch arguments must be nonempty and unique")
        if self.service_workers != "block":
            raise ValueError("private browser launch policy must block Service Workers")
        missing = [arg for arg in REQUIRED_EGRESS_ARGS if arg not in self.args]
        if missing:
            raise ValueError(
                f"private browser launch policy is missing egress arguments: {missing}"
            )
        if any(arg == "--proxy-server" or arg.startswith("--proxy-server=") for arg in self.args):
            raise ValueError("proxy authority belongs to `proxy`, not to a bare argument")

    def playwright_options(self) -> dict:
        """Return a fresh mapping so a driver cannot mutate the frozen policy."""
        return {
            "args": list(self.args),
            "ignore_default_args": list(self.ignore_default_args),
            "proxy": self.proxy.playwright_value(),
            "service_workers": self.service_workers,
            "accept_downloads": self.accept_downloads,
        }

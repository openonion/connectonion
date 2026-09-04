"""Install the private Onionwright client from OpenOnion's signed release feed.

The command is deliberately explicit: importing ConnectOnion or selecting the
system browser must never mutate a Python environment.  A caller who runs
``co browser install-onion`` authenticates, verifies the pinned Ed25519 release
manifest, downloads the exact wheel, verifies its SHA-256, and only then hands
the local file to the current interpreter's pip.
"""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

import requests
from nacl.exceptions import BadSignatureError
from nacl.signing import VerifyKey
from packaging.version import InvalidVersion, Version

from connectonion.backend import backend_url
from connectonion.credentials import require_ambient_api_key

ONIONWRIGHT_VERSION = "0.0.13"
ONIONWRIGHT_ARTIFACT = (
    "onionwright/0.0.13/onionwright-0.0.13-py3-none-any.whl"
)

# This is the public half of oo-api's production licence-signing key.  Fetching
# a verification key beside the manifest would let a compromised delivery path
# bless its own wheel, so releases intentionally require a ConnectOnion update
# when this trust root changes.
RELEASE_VERIFY_KEY_HEX = (
    "be8cca51dcbb9c51af19e3f18ef1d355"
    "abbc0e6549b017c2932ab2bdc25c7fb3"
)

REQUEST_TIMEOUT = (10, 120)
MAX_WHEEL_BYTES = 100 * 1024 * 1024


class OnionwrightInstallError(RuntimeError):
    """The private client could not be verified, downloaded, or installed."""


@dataclass(frozen=True)
class InstallResult:
    version: str
    already_installed: bool


def _installed_version() -> str | None:
    try:
        return importlib.metadata.version("onionwright")
    except importlib.metadata.PackageNotFoundError:
        return None


def _is_compatible(version: str | None) -> bool:
    if version is None:
        return False
    try:
        return Version(version) >= Version(ONIONWRIGHT_VERSION)
    except InvalidVersion:
        return False


def _request_json(method: str, url: str, **kwargs) -> dict:
    try:
        response = requests.request(
            method,
            url,
            timeout=REQUEST_TIMEOUT,
            allow_redirects=False,
            **kwargs,
        )
    except requests.RequestException as exc:
        raise OnionwrightInstallError(
            f"OpenOnion release service is unavailable during {method.upper()}."
        ) from exc
    try:
        if response.status_code != 200:
            raise OnionwrightInstallError(
                f"OpenOnion release service returned HTTP {response.status_code} "
                f"during {method.upper()}."
            )
        try:
            body = response.json()
        except (requests.JSONDecodeError, ValueError) as exc:
            raise OnionwrightInstallError(
                "OpenOnion release service returned invalid JSON."
            ) from exc
    finally:
        response.close()
    if not isinstance(body, dict):
        raise OnionwrightInstallError(
            "OpenOnion release service returned an invalid response shape."
        )
    return body


def _verified_manifest_digest(signed: dict) -> str:
    try:
        payload = bytes.fromhex(signed["payload"])
        signature = bytes.fromhex(signed["signature"])
        VerifyKey(bytes.fromhex(RELEASE_VERIFY_KEY_HEX)).verify(payload, signature)
        document = json.loads(payload)
        artifacts = document["artifacts"]
        digest = artifacts[ONIONWRIGHT_ARTIFACT]
    except (
        BadSignatureError,
        KeyError,
        TypeError,
        ValueError,
        json.JSONDecodeError,
    ) as exc:
        raise OnionwrightInstallError(
            "OpenOnion release manifest signature or schema is invalid."
        ) from exc
    if (
        not isinstance(digest, str)
        or len(digest) != 64
        or any(char not in "0123456789abcdef" for char in digest)
    ):
        raise OnionwrightInstallError(
            "OpenOnion release manifest contains an invalid wheel checksum."
        )
    return digest


def _download_wheel(url: str, destination: Path, expected_sha256: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise OnionwrightInstallError(
            "OpenOnion release service returned an invalid download URL."
        )
    if backend_url().startswith("https://") and parsed.scheme != "https":
        raise OnionwrightInstallError(
            "OpenOnion release service attempted an insecure download."
        )

    try:
        response = requests.get(
            url,
            stream=True,
            timeout=REQUEST_TIMEOUT,
            allow_redirects=False,
        )
    except requests.RequestException as exc:
        raise OnionwrightInstallError(
            "Onionwright wheel download failed before verification."
        ) from exc
    if response.status_code != 200:
        response.close()
        raise OnionwrightInstallError(
            f"Onionwright wheel download returned HTTP {response.status_code}."
        )

    digest = hashlib.sha256()
    size = 0
    try:
        try:
            with destination.open("wb") as wheel:
                for chunk in response.iter_content(chunk_size=1024 * 1024):
                    if not chunk:
                        continue
                    size += len(chunk)
                    if size > MAX_WHEEL_BYTES:
                        raise OnionwrightInstallError(
                            "Onionwright wheel exceeded the safe download limit."
                        )
                    digest.update(chunk)
                    wheel.write(chunk)
        except requests.RequestException as exc:
            raise OnionwrightInstallError(
                "Onionwright wheel download failed before verification."
            ) from exc
    finally:
        response.close()
    if size == 0 or digest.hexdigest() != expected_sha256:
        raise OnionwrightInstallError(
            "Onionwright wheel checksum did not match the signed manifest."
        )


def install_onionwright() -> InstallResult:
    """Install the current private client into this exact Python environment."""
    current = _installed_version()
    if _is_compatible(current):
        return InstallResult(version=current or ONIONWRIGHT_VERSION, already_installed=True)

    token = require_ambient_api_key()
    headers = {"Authorization": f"Bearer {token}"}
    base = backend_url()
    signed = _request_json(
        "get",
        f"{base}/api/v1/license/manifest",
        headers=headers,
    )
    expected_sha256 = _verified_manifest_digest(signed)
    grant = _request_json(
        "post",
        f"{base}/api/v1/license/download",
        headers=headers,
        json={"artifact": ONIONWRIGHT_ARTIFACT},
    )
    if grant.get("sha256") != expected_sha256 or not isinstance(grant.get("url"), str):
        raise OnionwrightInstallError(
            "OpenOnion download grant did not match the signed manifest."
        )

    with tempfile.TemporaryDirectory(prefix="co-onionwright-") as temp_dir:
        wheel = Path(temp_dir) / Path(ONIONWRIGHT_ARTIFACT).name
        _download_wheel(grant["url"], wheel, expected_sha256)
        command = [
            sys.executable,
            "-m",
            "pip",
            "install",
            "--upgrade",
            "--disable-pip-version-check",
            str(wheel),
        ]
        try:
            completed = subprocess.run(command, check=False)
        except OSError as exc:
            raise OnionwrightInstallError(
                "Could not start pip in the current Python environment."
            ) from exc
        if completed.returncode != 0:
            raise OnionwrightInstallError(
                f"pip could not install Onionwright (exit {completed.returncode})."
            )

    installed = _installed_version()
    if not _is_compatible(installed):
        raise OnionwrightInstallError(
            f"pip completed but Onionwright {ONIONWRIGHT_VERSION} or newer is not installed."
        )
    return InstallResult(version=installed or ONIONWRIGHT_VERSION, already_installed=False)

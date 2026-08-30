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
import math
import re
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

import requests
from nacl.exceptions import BadSignatureError
from nacl.signing import VerifyKey
from packaging.version import InvalidVersion, Version

from connectonion.browser_preview import (
    ONIONWRIGHT_ARTIFACT,
    ONIONWRIGHT_VERSION,
    RELEASE_CHANNEL,
    BrowserPreviewConfigError,
    api_url,
)
from connectonion.credentials import require_ambient_api_key

# This is the public half of oo-api's production licence-signing key.  Fetching
# a verification key beside the manifest would let a compromised delivery path
# bless its own wheel, so releases intentionally require a ConnectOnion update
# when this trust root changes.
RELEASE_VERIFY_KEY_HEX = (
    "be8cca51dcbb9c51af19e3f18ef1d355" "abbc0e6549b017c2932ab2bdc25c7fb3"
)

REQUEST_TIMEOUT = (10, 120)
MAX_WHEEL_BYTES = 100 * 1024 * 1024
LOOPBACK_HOSTS = {"localhost", "127.0.0.1", "::1"}
MANIFEST_VERSION = 2
MANIFEST_PURPOSE = "openonion-release-manifest"
MANIFEST_PRODUCT = "openonion-artifacts"
MANIFEST_LIFETIME_SECONDS = 15 * 60
MANIFEST_FUTURE_SKEW_SECONDS = 60
MAX_MANIFEST_PAYLOAD_BYTES = 1024 * 1024
MAX_JSON_RESPONSE_BYTES = 2 * MAX_MANIFEST_PAYLOAD_BYTES + 4096
MAX_ARTIFACT_KEY_LENGTH = 512


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
        # Preview semantics are part of these immutable bytes. A newer final
        # may be a production-channel client and must not be accepted merely
        # because PEP 440 sorts it after this preview.
        return Version(version) == Version(ONIONWRIGHT_VERSION)
    except InvalidVersion:
        return False


def _request_json(method: str, url: str, **kwargs) -> dict:
    try:
        response = requests.request(
            method,
            url,
            stream=True,
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
        encoded = bytearray()
        try:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if not chunk:
                    continue
                if len(encoded) + len(chunk) > MAX_JSON_RESPONSE_BYTES:
                    raise OnionwrightInstallError(
                        "OpenOnion release service response exceeded the safe limit."
                    )
                encoded.extend(chunk)
        except requests.RequestException as exc:
            raise OnionwrightInstallError(
                f"OpenOnion release service is unavailable during {method.upper()}."
            ) from exc
        try:
            body = json.loads(encoded)
        except (UnicodeError, json.JSONDecodeError, ValueError) as exc:
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


def _verified_manifest_digest(signed: dict, *, clock=time.time) -> str:
    """Return the pinned wheel digest from one exact, fresh preview manifest.

    This verifier deliberately lives in ConnectOnion: it is the bootstrap that
    installs Onionwright, so delegating trust to an optional or outdated
    Onionwright package would create a circular dependency.  Keep its contract
    byte-for-byte aligned with oo-api's seven-field preview v2 payload.
    """
    try:
        if not isinstance(signed, dict) or set(signed) != {"payload", "signature"}:
            raise ValueError("response must contain exactly payload and signature")
        payload_hex = signed["payload"]
        signature_hex = signed["signature"]
        if (
            not isinstance(payload_hex, str)
            or not payload_hex
            or len(payload_hex) > 2 * MAX_MANIFEST_PAYLOAD_BYTES
            or len(payload_hex) % 2
            or re.fullmatch(r"[0-9a-f]+", payload_hex) is None
            or not isinstance(signature_hex, str)
            or re.fullmatch(r"[0-9a-f]{128}", signature_hex) is None
        ):
            raise ValueError("payload and signature must be canonical lowercase hex")
        payload = bytes.fromhex(payload_hex)
        signature = bytes.fromhex(signature_hex)
        if not payload or len(payload) > MAX_MANIFEST_PAYLOAD_BYTES:
            raise ValueError("signed manifest payload has an invalid size")
        VerifyKey(bytes.fromhex(RELEASE_VERIFY_KEY_HEX)).verify(payload, signature)
        document = json.loads(payload)
        expected_fields = {
            "v",
            "purpose",
            "product",
            "issued_at",
            "expires_at",
            "artifacts",
            "channel",
        }
        if not isinstance(document, dict) or set(document) != expected_fields:
            raise ValueError("signed manifest fields are incomplete or unexpected")
        canonical = json.dumps(
            document, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        if payload != canonical:
            raise ValueError("signed manifest JSON is not canonical")

        issued_at = document["issued_at"]
        expires_at = document["expires_at"]
        artifacts = document["artifacts"]
        if (
            type(document["v"]) is not int
            or document["v"] != MANIFEST_VERSION
            or document["purpose"] != MANIFEST_PURPOSE
            or document["product"] != MANIFEST_PRODUCT
            or document["channel"] != RELEASE_CHANNEL
            or type(issued_at) is not int
            or type(expires_at) is not int
            or issued_at <= 0
            or expires_at - issued_at != MANIFEST_LIFETIME_SECONDS
        ):
            raise ValueError("signed manifest version, domain, or lifetime is invalid")
        now = clock()
        if type(now) not in (int, float) or not math.isfinite(now):
            raise ValueError("manifest verifier clock is invalid")
        if issued_at > now + MANIFEST_FUTURE_SKEW_SECONDS:
            raise ValueError("signed manifest was issued too far in the future")
        if expires_at <= now:
            raise ValueError("signed manifest is expired")
        if not isinstance(artifacts, dict) or not artifacts:
            raise ValueError("signed manifest artifacts must be a nonempty object")
        for key, digest in artifacts.items():
            if (
                not isinstance(key, str)
                or not key
                or len(key) > MAX_ARTIFACT_KEY_LENGTH
                or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._/-]*", key) is None
                or key.startswith("/")
                or "\\" in key
                or any(part in {"", ".", ".."} for part in key.split("/"))
                or not isinstance(digest, str)
                or re.fullmatch(r"[0-9a-f]{64}", digest) is None
            ):
                raise ValueError(
                    "signed manifest contains a noncanonical artifact mapping"
                )
        digest = artifacts[ONIONWRIGHT_ARTIFACT]
    except (
        BadSignatureError,
        KeyError,
        OverflowError,
        TypeError,
        UnicodeError,
        ValueError,
        json.JSONDecodeError,
    ) as exc:
        raise OnionwrightInstallError(
            "OpenOnion release manifest signature or schema is invalid."
        ) from exc
    return digest


def _download_wheel(
    url: str,
    destination: Path,
    expected_sha256: str,
    *,
    preview_api_url: str | None = None,
) -> None:
    parsed = urlparse(url)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.netloc
        or parsed.username is not None
        or parsed.password is not None
    ):
        raise OnionwrightInstallError(
            "OpenOnion release service returned an invalid download URL."
        )
    if parsed.scheme != "https":
        preview = urlparse(preview_api_url or "")
        local_e2e = (
            parsed.scheme == "http"
            and parsed.hostname in LOOPBACK_HOSTS
            and preview.scheme == "http"
            and preview.hostname in LOOPBACK_HOSTS
        )
        if not local_e2e:
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
        return InstallResult(
            version=current or ONIONWRIGHT_VERSION, already_installed=True
        )

    token = require_ambient_api_key()
    headers = {"Authorization": f"Bearer {token}"}
    try:
        base = api_url()
    except BrowserPreviewConfigError as exc:
        raise OnionwrightInstallError(str(exc)) from exc
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
        _download_wheel(
            grant["url"],
            wheel,
            expected_sha256,
            preview_api_url=base,
        )
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
            f"pip completed but exact preview Onionwright {ONIONWRIGHT_VERSION} "
            "is not installed."
        )
    return InstallResult(
        version=installed or ONIONWRIGHT_VERSION, already_installed=False
    )

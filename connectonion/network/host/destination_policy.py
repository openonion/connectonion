"""Pure Remote Browser destination normalization and address classification.

This module performs no DNS lookup and opens no socket.  It exists so every
later egress layer makes the same decision on Python 3.10-3.13 instead of
inheriting release-dependent ``ipaddress.is_global`` behavior.
"""

from __future__ import annotations

import ipaddress
from dataclasses import dataclass
from typing import Iterable, Sequence
from urllib.parse import SplitResult, urlsplit

import idna

WEB_SCHEMES = frozenset({"http", "https", "ws", "wss"})
WEB_PORTS = frozenset({80, 443, 8080, 8443})
DEFAULT_PORTS = {"http": 80, "https": 443, "ws": 80, "wss": 443}
POLICY_SCHEMA_VERSION = 1
IANA_REGISTRY_SNAPSHOT = "2025-10-09"
IPAddress = ipaddress.IPv4Address | ipaddress.IPv6Address

INVALID = "DESTINATION_INVALID"
SCHEME_DENIED = "DESTINATION_SCHEME_DENIED"
PORT_DENIED = "DESTINATION_PORT_DENIED"
HOST_DENIED = "DESTINATION_HOST_DENIED"
DNS_FAILED = "DESTINATION_DNS_FAILED"
ADDRESS_DENIED = "DESTINATION_ADDRESS_DENIED"
ALLOWED = "DESTINATION_ALLOWED"

_SPECIAL_HOSTS = frozenset(
    {
        "localhost",
        "localhost.localdomain",
        "metadata.google.internal",
        "metadata.goog",
    }
)
_SPECIAL_SUFFIXES = (
    ".localhost",
    ".local",
    ".internal",
    ".invalid",
    ".test",
    ".example",
)

# Conservative frozen policy derived from the IANA IPv4 special-purpose
# registry.  A few globally reachable protocol-anycast exceptions within these
# blocks remain denied: they are not ordinary public-web destinations.
_FORBIDDEN_V4 = tuple(
    ipaddress.ip_network(value)
    for value in (
        "0.0.0.0/8",
        "10.0.0.0/8",
        "100.64.0.0/10",
        "127.0.0.0/8",
        "169.254.0.0/16",
        "172.16.0.0/12",
        "192.0.0.0/24",
        "192.0.2.0/24",
        "192.31.196.0/24",
        "192.52.193.0/24",
        "192.88.99.0/24",
        "192.168.0.0/16",
        "192.175.48.0/24",
        "198.18.0.0/15",
        "198.51.100.0/24",
        "203.0.113.0/24",
        "224.0.0.0/4",
        "240.0.0.0/4",
    )
)

_FORBIDDEN_V6 = tuple(
    ipaddress.ip_network(value)
    for value in (
        "::/128",
        "::1/128",
        "64:ff9b:1::/48",
        "100::/64",
        "100:0:0:1::/64",
        "2001::/23",
        "2001:db8::/32",
        "3fff::/20",
        "5f00::/16",
        "2620:4f:8000::/48",
        "fc00::/7",
        "fe80::/10",
        "ff00::/8",
    )
)
_GLOBAL_V6 = ipaddress.ip_network("2000::/3")
_IPV4_TRANSLATED = ipaddress.ip_network("::ffff:0:0:0/96")
_NAT64_WKP = ipaddress.ip_network("64:ff9b::/96")
_SIX_TO_FOUR = ipaddress.ip_network("2002::/16")


class DestinationPolicyError(ValueError):
    """A stable policy refusal that never retains the submitted URL."""

    def __init__(self, code: str, reason: str):
        super().__init__(reason)
        self.code = code
        self.reason = reason


@dataclass(frozen=True)
class DestinationAuthority:
    """Normalized network authority without path, query, userinfo, or fragment."""

    scheme: str
    host: str
    port: int
    literal: IPAddress | None = None


@dataclass(frozen=True)
class AddressClassification:
    """One canonical numeric address and its frozen policy class."""

    address: str
    allowed: bool
    address_class: str


@dataclass(frozen=True)
class DestinationDecision:
    """Final pure decision over an authority and its complete DNS answer set."""

    ok: bool
    code: str
    scheme: str
    host: str
    port: int
    address_class: str
    addresses: tuple[str, ...]


def _has_forbidden_character(value: str) -> bool:
    return any(ord(character) < 0x21 or ord(character) == 0x7F for character in value)


def _split_url(url: str) -> SplitResult:
    if not isinstance(url, str) or not url or _has_forbidden_character(url):
        raise DestinationPolicyError(INVALID, "URL contains invalid characters")
    split: SplitResult | None
    try:
        split = urlsplit(url)
        # Accessors perform bracket and port validation lazily.
        split.hostname
        split.port
    except (TypeError, ValueError):
        split = None
    if split is None:
        raise DestinationPolicyError(INVALID, "URL authority is malformed")
    return split


def _parse_ipv4_number(part: str) -> int | None:
    if not part:
        return None
    base = 10
    digits = part
    if len(part) >= 2 and part[:2].lower() == "0x":
        base, digits = 16, part[2:]
    elif len(part) >= 2 and part[0] == "0":
        base, digits = 8, part[1:]
    if not digits:
        return 0
    alphabet = {
        8: "01234567",
        10: "0123456789",
        16: "0123456789abcdefABCDEF",
    }[base]
    if any(character not in alphabet for character in digits):
        return None
    return int(digits, base)


def _ends_in_number(host: str) -> bool:
    last = host.rsplit(".", 1)[-1]
    return _parse_ipv4_number(last) is not None or (last.isascii() and last.isdigit())


def _whatwg_ipv4(host: str) -> ipaddress.IPv4Address | None:
    """Parse the non-canonical IPv4 forms accepted by browser URL parsers."""
    if not _ends_in_number(host):
        return None
    parts = host.split(".")
    if not 1 <= len(parts) <= 4:
        raise DestinationPolicyError(INVALID, "IPv4 address has too many parts")
    numbers = [_parse_ipv4_number(part) for part in parts]
    if any(number is None for number in numbers):
        raise DestinationPolicyError(INVALID, "IPv4 address is malformed")
    parsed = [int(number) for number in numbers]
    if any(number > 255 for number in parsed[:-1]):
        raise DestinationPolicyError(INVALID, "IPv4 part exceeds 255")
    final_limit = 256 ** (5 - len(parsed))
    if parsed[-1] >= final_limit:
        raise DestinationPolicyError(INVALID, "IPv4 final part is too large")
    value = parsed[-1]
    for index, number in enumerate(parsed[:-1]):
        value += number * (256 ** (3 - index))
    return ipaddress.IPv4Address(value)


def _normalize_host(host: str) -> tuple[str, IPAddress | None]:
    if not host:
        raise DestinationPolicyError(INVALID, "hostname is invalid")

    # An IPv6 literal reaches here already unbracketed, and its `:` separators
    # are disallowed under STD3, so it is classified before the mapping below.
    # Its grammar is fixed ASCII; there is nothing for UTS-46 to map.
    if ":" not in host:
        # UTS-46 mapping runs before every other check, which is the order a
        # browser URL parser uses. U+3002 U+FF0E U+FF61 all map to `.` and the
        # fullwidth digits map to ASCII, so a check reading the string first
        # reads a different name than the one Chromium will dial: `localhost。`
        # normalizes to `localhost.`, and `１２７.０.０.１` to the literal
        # 127.0.0.1.
        remapped: str | None
        try:
            remapped = idna.uts46_remap(host, std3_rules=True, transitional=False)
        except (idna.IDNAError, UnicodeError):
            remapped = None
        if remapped is None:
            raise DestinationPolicyError(INVALID, "hostname mapping is invalid")
        host = remapped

    if not host or "\\" in host or "%" in host:
        raise DestinationPolicyError(INVALID, "hostname is invalid")
    if host.endswith(".."):
        raise DestinationPolicyError(INVALID, "hostname has multiple trailing dots")
    host = host[:-1] if host.endswith(".") else host
    if not host:
        raise DestinationPolicyError(INVALID, "hostname is empty")

    if ":" in host:
        literal: ipaddress.IPv6Address | None
        try:
            literal = ipaddress.IPv6Address(host)
        except ipaddress.AddressValueError:
            literal = None
        if literal is None:
            raise DestinationPolicyError(INVALID, "IPv6 address is malformed")
        return literal.compressed, literal

    ipv4 = _whatwg_ipv4(host)
    if ipv4 is not None:
        return str(ipv4), ipv4

    normalized: str | None
    try:
        normalized = idna.encode(host, uts46=True, std3_rules=True).decode("ascii")
    except idna.IDNAError:
        normalized = None
    if normalized is None:
        raise DestinationPolicyError(INVALID, "hostname IDNA is invalid")
    normalized = normalized.lower()
    if len(normalized) > 253:
        raise DestinationPolicyError(INVALID, "hostname is too long")
    if normalized in _SPECIAL_HOSTS or normalized.endswith(_SPECIAL_SUFFIXES):
        raise DestinationPolicyError(HOST_DENIED, "special-use hostname is denied")
    return normalized, None


def normalize_web_destination(
    url: str, *, allowed_ports: Iterable[int] = WEB_PORTS
) -> DestinationAuthority:
    """Normalize one web URL to the authority Chromium must request."""
    split = _split_url(url)
    scheme = split.scheme.lower()
    if scheme not in WEB_SCHEMES:
        raise DestinationPolicyError(SCHEME_DENIED, "URL scheme is not web traffic")
    if not split.netloc or "@" in split.netloc:
        raise DestinationPolicyError(INVALID, "userinfo or empty authority is denied")
    host, literal = _normalize_host(split.hostname or "")
    port = split.port if split.port is not None else DEFAULT_PORTS[scheme]
    allowed: frozenset[int] | None
    try:
        allowed = frozenset(allowed_ports)
    except TypeError:
        allowed = None
    if allowed is None:
        raise DestinationPolicyError(INVALID, "allowed port policy is invalid")
    if any(
        isinstance(candidate, bool)
        or not isinstance(candidate, int)
        or not 1 <= candidate <= 65535
        for candidate in allowed
    ):
        raise DestinationPolicyError(INVALID, "allowed port policy is invalid")
    if port not in allowed:
        raise DestinationPolicyError(PORT_DENIED, "destination port is denied")
    return DestinationAuthority(scheme=scheme, host=host, port=port, literal=literal)


def _operator_networks(
    values: Iterable[str | ipaddress.IPv4Network | ipaddress.IPv6Network],
) -> tuple[ipaddress.IPv4Network | ipaddress.IPv6Network, ...]:
    networks: tuple[ipaddress.IPv4Network | ipaddress.IPv6Network, ...] | None
    try:
        networks = tuple(ipaddress.ip_network(value, strict=False) for value in values)
    except (TypeError, ValueError):
        networks = None
    if networks is None:
        raise DestinationPolicyError(INVALID, "operator deny network is invalid")
    return networks


def classify_address(
    value: str | ipaddress.IPv4Address | ipaddress.IPv6Address,
    *,
    deny_networks: Iterable[str | ipaddress.IPv4Network | ipaddress.IPv6Network] = (),
) -> AddressClassification:
    """Classify one numeric address against frozen and operator deny ranges."""
    if not isinstance(value, (str, ipaddress.IPv4Address, ipaddress.IPv6Address)):
        raise DestinationPolicyError(INVALID, "DNS answer is not an IP address")
    address: IPAddress | None
    try:
        address = ipaddress.ip_address(value)
    except (TypeError, ValueError):
        address = None
    if address is None:
        raise DestinationPolicyError(INVALID, "DNS answer is not an IP address")

    # Materialize once. The transition-address branches below recurse with this
    # same value, and a one-shot iterable would arrive there already exhausted —
    # protecting the outer address and silently nothing inside it.
    frozen_denies = _operator_networks(deny_networks)
    for network in frozen_denies:
        if address.version == network.version and address in network:
            return AddressClassification(str(address), False, "operator_denied")

    if isinstance(address, ipaddress.IPv4Address):
        for network in _FORBIDDEN_V4:
            if address in network:
                return AddressClassification(str(address), False, "special_ipv4")
        return AddressClassification(str(address), True, "public_ipv4")

    if address.ipv4_mapped is not None:
        inner = classify_address(address.ipv4_mapped, deny_networks=frozen_denies)
        return AddressClassification(
            str(address), inner.allowed, f"ipv4_mapped_{inner.address_class}"
        )
    if address in _IPV4_TRANSLATED:
        inner = classify_address(
            ipaddress.IPv4Address(int(address) & 0xFFFFFFFF),
            deny_networks=frozen_denies,
        )
        return AddressClassification(
            str(address), inner.allowed, f"ipv4_translated_{inner.address_class}"
        )
    if address in _NAT64_WKP:
        inner = classify_address(
            ipaddress.IPv4Address(int(address) & 0xFFFFFFFF),
            deny_networks=frozen_denies,
        )
        return AddressClassification(
            str(address), inner.allowed, f"nat64_{inner.address_class}"
        )
    if address in _SIX_TO_FOUR:
        inner = classify_address(
            ipaddress.IPv4Address((int(address) >> 80) & 0xFFFFFFFF),
            deny_networks=frozen_denies,
        )
        return AddressClassification(
            str(address), inner.allowed, f"6to4_{inner.address_class}"
        )
    for network in _FORBIDDEN_V6:
        if address in network:
            return AddressClassification(str(address), False, "special_ipv6")
    if address not in _GLOBAL_V6:
        return AddressClassification(str(address), False, "non_global_ipv6")
    return AddressClassification(str(address), True, "public_ipv6")


def decide_destination(
    authority: DestinationAuthority,
    resolved_addresses: Sequence[
        str | ipaddress.IPv4Address | ipaddress.IPv6Address
    ] = (),
    *,
    deny_networks: Iterable[str | ipaddress.IPv4Network | ipaddress.IPv6Network] = (),
) -> DestinationDecision:
    """Decide one literal or complete DNS answer set without network effects."""
    answers: Sequence[str | IPAddress]
    if authority.literal is not None:
        answers = (authority.literal,)
    else:
        answers = resolved_addresses
    if not answers:
        raise DestinationPolicyError(DNS_FAILED, "hostname has no DNS answers")

    frozen_denies = _operator_networks(deny_networks)
    classifications = tuple(
        classify_address(answer, deny_networks=frozen_denies) for answer in answers
    )
    ordered = sorted(
        classifications,
        key=lambda item: (
            ipaddress.ip_address(item.address).version,
            int(ipaddress.ip_address(item.address)),
            item.address_class,
        ),
    )
    denied = next((item for item in ordered if not item.allowed), None)
    ordered_addresses = tuple(dict.fromkeys(item.address for item in ordered))
    if denied is not None:
        return DestinationDecision(
            ok=False,
            code=ADDRESS_DENIED,
            scheme=authority.scheme,
            host=authority.host,
            port=authority.port,
            address_class=denied.address_class,
            addresses=ordered_addresses,
        )
    classes = sorted({item.address_class for item in classifications})
    return DestinationDecision(
        ok=True,
        code=ALLOWED,
        scheme=authority.scheme,
        host=authority.host,
        port=authority.port,
        address_class="+".join(classes),
        addresses=ordered_addresses,
    )

"""Versioned contract for Remote Browser's pure destination policy."""

import dataclasses
import ipaddress
import json
from pathlib import Path

import pytest

from connectonion.network.host import destination_policy as policy

VECTORS = json.loads(
    (
        Path(__file__).parents[1]
        / "fixtures"
        / "remote_browser_destination_vectors.json"
    ).read_text(encoding="utf-8")
)


def test_vector_catalogue_has_authoritative_sources_and_version():
    assert VECTORS["schema_version"] == policy.POLICY_SCHEMA_VERSION
    assert VECTORS["sources"] == {
        "url": "https://url.spec.whatwg.org/",
        "ipv4": "https://www.iana.org/assignments/iana-ipv4-special-registry",
        "ipv6": "https://www.iana.org/assignments/iana-ipv6-special-registry",
        "registry_snapshot": "2025-10-09",
    }
    assert VECTORS["sources"]["registry_snapshot"] == policy.IANA_REGISTRY_SNAPSHOT


@pytest.mark.parametrize("vector", VECTORS["authorities"], ids=lambda item: item["url"])
def test_authority_vectors(vector):
    if not vector["ok"]:
        with pytest.raises(policy.DestinationPolicyError) as raised:
            policy.normalize_web_destination(vector["url"])
        assert raised.value.code == vector["code"]
        assert "token=secret" not in repr(raised.value)
        return

    authority = policy.normalize_web_destination(vector["url"])
    assert authority.scheme == vector["scheme"]
    assert authority.host == vector["host"]
    assert authority.port == vector["port"]
    serialized = repr(authority)
    assert "/private/path" not in serialized
    assert "token=secret" not in serialized
    assert "fragment" not in serialized


@pytest.mark.parametrize(
    "vector", VECTORS["addresses"], ids=lambda item: item["address"]
)
def test_address_vectors(vector):
    result = policy.classify_address(vector["address"])
    assert result.allowed is vector["allowed"]
    assert result.address_class == vector["class"]


@pytest.mark.parametrize("vector", VECTORS["answer_sets"], ids=lambda item: item["url"])
def test_complete_dns_answer_sets_fail_when_any_answer_is_denied(vector):
    authority = policy.normalize_web_destination(vector["url"])
    result = policy.decide_destination(authority, vector["answers"])
    assert result.ok is vector["ok"]
    assert result.code == vector["code"]
    expected_addresses = {
        str(ipaddress.ip_address(address)) for address in vector["answers"]
    }
    assert set(result.addresses) == expected_addresses
    serialized = repr(result)
    assert "hidden" not in serialized
    assert "secret=yes" not in serialized


def test_literal_uses_its_canonical_address_and_ignores_dns_answers():
    authority = policy.normalize_web_destination("http://2130706433/")
    result = policy.decide_destination(authority, ["8.8.8.8"])

    assert result.ok is False
    assert result.code == policy.ADDRESS_DENIED
    assert result.addresses == ("127.0.0.1",)


def test_hostname_requires_a_complete_nonempty_answer_set():
    authority = policy.normalize_web_destination("https://openonion.ai/")

    with pytest.raises(policy.DestinationPolicyError) as raised:
        policy.decide_destination(authority, [])
    assert raised.value.code == policy.DNS_FAILED


def test_operator_deny_generator_applies_to_every_answer():
    authority = policy.normalize_web_destination("https://openonion.ai/")
    denies = (value for value in ["8.8.8.0/24"])
    result = policy.decide_destination(
        authority,
        ["1.1.1.1", "8.8.8.8"],
        deny_networks=denies,
    )

    assert result.ok is False
    assert result.address_class == "operator_denied"


@pytest.mark.parametrize(
    "address",
    [
        "::ffff:8.8.8.8",
        "::ffff:0:8.8.8.8",
        "64:ff9b::808:808",
        "2002:808:808::",
    ],
)
def test_operator_ipv4_deny_applies_inside_transition_addresses(address):
    result = policy.classify_address(address, deny_networks=["8.8.8.0/24"])

    assert result.allowed is False
    assert result.address_class.endswith("operator_denied")


def test_invalid_operator_network_fails_before_a_decision():
    with pytest.raises(policy.DestinationPolicyError) as raised:
        policy.classify_address("8.8.8.8", deny_networks=["not-a-network"])
    assert raised.value.code == policy.INVALID


@pytest.mark.parametrize(
    ("operation", "secret"),
    [
        (lambda: policy.classify_address("secret-dns-payload"), "secret-dns"),
        (
            lambda: policy.normalize_web_destination("http://[secret-url-payload"),
            "secret-url",
        ),
        (
            lambda: policy.normalize_web_destination(
                "https://\u200dsecret-idna.tested/"
            ),
            "secret-idna",
        ),
        (
            lambda: policy.classify_address(
                "8.8.8.8", deny_networks=["secret-operator-payload"]
            ),
            "secret-operator",
        ),
    ],
)
def test_policy_errors_do_not_retain_parser_payloads(operation, secret):
    with pytest.raises(policy.DestinationPolicyError) as raised:
        operation()

    assert secret not in repr(raised.value)
    assert raised.value.__cause__ is None
    assert raised.value.__context__ is None


@pytest.mark.parametrize(
    "network",
    [*policy._FORBIDDEN_V4, *policy._FORBIDDEN_V6],
    ids=str,
)
def test_both_edges_of_every_frozen_forbidden_network_are_denied(network):
    first = policy.classify_address(network.network_address)
    last = policy.classify_address(network.broadcast_address)

    assert first.allowed is False
    assert last.allowed is False


@pytest.mark.parametrize(
    "network",
    [*policy._FORBIDDEN_V4, *policy._FORBIDDEN_V6],
    ids=str,
)
def test_before_inside_and_after_every_frozen_network_match_the_frozen_table(
    network,
):
    maximum = (1 << network.max_prefixlen) - 1
    candidates = {
        max(0, int(network.network_address) - 1),
        int(network.network_address),
        (int(network.network_address) + int(network.broadcast_address)) // 2,
        int(network.broadcast_address),
        min(maximum, int(network.broadcast_address) + 1),
    }
    forbidden = policy._FORBIDDEN_V4 if network.version == 4 else policy._FORBIDDEN_V6

    for numeric in candidates:
        address = type(network.network_address)(numeric)
        expected_denied = any(address in candidate for candidate in forbidden)
        if network.version == 6 and address not in policy._GLOBAL_V6:
            expected_denied = True
        assert policy.classify_address(address).allowed is not expected_denied


@pytest.mark.parametrize(
    ("address", "allowed"),
    [
        ("9.255.255.255", True),
        ("10.0.0.0", False),
        ("10.255.255.255", False),
        ("11.0.0.0", True),
        ("100.63.255.255", True),
        ("100.64.0.0", False),
        ("100.127.255.255", False),
        ("100.128.0.0", True),
        ("172.15.255.255", True),
        ("172.16.0.0", False),
        ("172.31.255.255", False),
        ("172.32.0.0", True),
        ("192.167.255.255", True),
        ("192.168.0.0", False),
        ("192.168.255.255", False),
        ("192.169.0.0", True),
        ("223.255.255.255", True),
        ("224.0.0.0", False),
        ("255.255.255.255", False),
    ],
)
def test_selected_cidr_transition_boundaries(address, allowed):
    assert policy.classify_address(address).allowed is allowed


def test_decision_is_bounded_authority_data_not_the_submitted_url():
    authority = policy.normalize_web_destination(
        "https://OpenOnion.ai/private/customer/path?api_key=secret#account"
    )
    result = policy.decide_destination(authority, ["8.8.8.8"])
    value = dataclasses.asdict(result)

    assert value["host"] == "openonion.ai"
    serialized = json.dumps(value)
    for secret in ("customer", "api_key", "secret", "account"):
        assert secret not in serialized


def test_duplicate_answers_are_canonicalized_and_sorted():
    authority = policy.normalize_web_destination("https://openonion.ai/")
    result = policy.decide_destination(
        authority,
        [ipaddress.ip_address("8.8.8.8"), "1.1.1.1", "8.8.8.8"],
    )

    assert result.addresses == ("1.1.1.1", "8.8.8.8")


def test_dns_answer_order_cannot_change_the_decision():
    authority = policy.normalize_web_destination("https://openonion.ai/")
    answers = ["169.254.169.254", "127.0.0.1", "8.8.8.8"]

    forward = policy.decide_destination(authority, answers)
    reverse = policy.decide_destination(authority, list(reversed(answers)))

    assert forward == reverse


def test_ports_can_only_be_expanded_by_an_explicit_policy():
    with pytest.raises(policy.DestinationPolicyError) as raised:
        policy.normalize_web_destination("https://example.com:9443/")
    assert raised.value.code == policy.PORT_DENIED

    authority = policy.normalize_web_destination(
        "https://example.com:9443/", allowed_ports={443, 9443}
    )
    assert authority.port == 9443


@pytest.mark.parametrize("allowed_ports", [{True}, {"443"}, {0}, {65536}, None])
def test_invalid_explicit_port_policies_fail_closed(allowed_ports):
    with pytest.raises(policy.DestinationPolicyError) as raised:
        policy.normalize_web_destination(
            "https://example.com/", allowed_ports=allowed_ports
        )
    assert raised.value.code == policy.INVALID


# UTS-46 maps several Unicode characters onto ASCII `.` and onto ASCII digits.
# Chromium runs that mapping FIRST, so a caller who writes `localhost。` reaches
# the same host as `localhost`. Any check that reads the string before the
# mapping is reading a different name than the browser will dial.
@pytest.mark.parametrize(
    "host",
    [
        "localhost。",
        "localhost．",
        "localhost｡",
        "metadata.google.internal。",
        "metadata.goog。",
        "localhost.localdomain。",
        "anything.internal。",
        "anything.local。",
        "kubernetes.default.svc.cluster.local。",
    ],
)
def test_unicode_dots_do_not_smuggle_a_special_hostname(host):
    with pytest.raises(policy.DestinationPolicyError) as raised:
        policy.normalize_web_destination(f"http://{host}/")
    assert raised.value.code == policy.HOST_DENIED


# The mapping also produces the double trailing dot the parser rejects outright.
def test_a_unicode_dot_cannot_build_a_second_trailing_dot():
    with pytest.raises(policy.DestinationPolicyError) as raised:
        policy.normalize_web_destination("http://localhost。./")
    assert raised.value.code == policy.INVALID


# The same mapping produces ASCII digits, so these are IP literals to the
# browser. A destination the browser dials numerically must be pinned here as a
# literal, never handed to a resolver whose answer the caller can influence.
@pytest.mark.parametrize(
    "host",
    ["127。0。0。1", "127.0.0.1。", "０x７f.１", "２１３０７０６４３３", "１２７.０.０.１"],
)
def test_unicode_digits_and_dots_still_pin_an_ip_literal(host):
    authority = policy.normalize_web_destination(f"http://{host}/")

    assert authority.literal is not None
    assert str(authority.literal) == "127.0.0.1"
    result = policy.decide_destination(authority, ["8.8.8.8"])
    assert result.ok is False
    assert result.code == policy.ADDRESS_DENIED
    assert result.addresses == ("127.0.0.1",)


# classify_address consumes deny_networks before recursing into a transition
# address, so a one-shot iterable protected the outer address and nothing else.
@pytest.mark.parametrize(
    "address",
    ["::ffff:8.8.8.8", "::ffff:0:8.8.8.8", "64:ff9b::808:808", "2002:808:808::"],
)
def test_operator_deny_generator_survives_transition_recursion(address):
    result = policy.classify_address(
        address, deny_networks=(value for value in ["8.8.8.0/24"])
    )

    assert result.allowed is False
    assert result.address_class.endswith("operator_denied")


# The frozen tables were only ever compared to themselves, which proves the two
# uses of one table agree but can never detect a MISSING range. These vectors
# are transcribed from the IANA registries independently of the code, so a
# special-purpose block the table forgets shows up here.
@pytest.mark.parametrize("block", VECTORS["registry_must_deny"]["ipv4"])
def test_every_registry_ipv4_block_is_covered_by_the_frozen_table(block):
    network = ipaddress.ip_network(block)
    covered = any(
        network.subnet_of(frozen)
        for frozen in policy._FORBIDDEN_V4
        if frozen.version == 4
    )
    assert covered, f"{block} is in the IANA registry but no frozen network covers it"


@pytest.mark.parametrize("block", VECTORS["registry_must_deny"]["ipv6"])
def test_every_registry_ipv6_block_is_covered(block):
    network = ipaddress.ip_network(block)
    covered = network.subnet_of(policy._GLOBAL_V6) is False or any(
        network.subnet_of(frozen)
        for frozen in policy._FORBIDDEN_V6
        if frozen.version == 6
    )
    # Everything outside 2000::/3 is denied by the global catch-all; everything
    # inside must be named in the frozen table.
    assert covered, f"{block} is in the IANA registry but nothing denies it"


# Special-use TLDs that resolve split-horizon: the address layer cannot judge
# them, so the suffix list is the only thing that can.
@pytest.mark.parametrize(
    "host",
    [
        "server.corp",
        "printer.home",
        "nas.lan",
        "wiki.intranet",
        "1.0.0.127.in-addr.arpa",
        "service.alt",
        "facebookcorewwwi.onion",
    ],
)
def test_reserved_and_squatted_tlds_are_denied(host):
    with pytest.raises(policy.DestinationPolicyError) as raised:
        policy.normalize_web_destination(f"http://{host}/")
    assert raised.value.code == policy.HOST_DENIED

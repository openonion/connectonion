"""Unit tests for connectonion/network/host/session/merge.py"""

from connectonion.network.host.session.merge import merge_sessions


def test_server_higher_iteration_wins():
    """Server made more LLM calls → server state wins."""
    client = {'iteration': 3, 'messages': ['c']}
    server = {'iteration': 5, 'messages': ['s']}
    merged, server_won = merge_sessions(client, server)
    assert merged is server
    assert server_won is True


def test_client_higher_iteration_wins():
    """Client got further (rare) → keep client."""
    client = {'iteration': 7, 'messages': ['c']}
    server = {'iteration': 2, 'messages': ['s']}
    merged, server_won = merge_sessions(client, server)
    assert merged is client
    assert server_won is False


def test_equal_iteration_server_updated_more_recent_wins():
    client = {'iteration': 4, 'updated': 100}
    server = {'iteration': 4, 'updated': 200}
    merged, server_won = merge_sessions(client, server)
    assert merged is server
    assert server_won is True


def test_equal_iteration_client_updated_more_recent_wins():
    client = {'iteration': 4, 'updated': 500}
    server = {'iteration': 4, 'updated': 100}
    merged, server_won = merge_sessions(client, server)
    assert merged is client
    assert server_won is False


def test_fully_equal_defaults_to_client():
    """No signal to prefer server → keep client (avoid spurious server takeover)."""
    client = {'iteration': 1, 'updated': 50}
    server = {'iteration': 1, 'updated': 50}
    merged, server_won = merge_sessions(client, server)
    assert merged is client
    assert server_won is False


def test_missing_iteration_treated_as_zero():
    client = {'iteration': 0}
    server = {}  # missing iteration → defaults to 0
    merged, server_won = merge_sessions(client, server)
    # Both 0, both updated 0 → client wins
    assert merged is client
    assert server_won is False


def test_server_iteration_with_missing_client_iteration_wins():
    client = {}
    server = {'iteration': 1}
    merged, server_won = merge_sessions(client, server)
    assert merged is server
    assert server_won is True

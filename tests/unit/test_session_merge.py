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


def test_a_stale_device_does_not_erase_a_turn_run_on_another_device():
    """`iteration` restarts at 0 every turn, so it is only a version inside one.

    Laptop's last turn took 7 LLM calls; the phone then ran turn 5 in 2. When
    the laptop reconnects carrying its copy, comparing iteration alone let 7
    beat 2 and turn 5 vanished from the conversation — no concurrency needed,
    just switching devices (#1606).
    """
    laptop = {'turn': 4, 'iteration': 7, 'updated': 100, 'messages': ['t1', 't2', 't3', 't4']}
    server = {'turn': 5, 'iteration': 2, 'updated': 200,
              'messages': ['t1', 't2', 't3', 't4', 't5 from the phone']}
    merged, server_won = merge_sessions(laptop, server)
    assert merged is server
    assert server_won is True


def test_a_client_further_by_turns_still_wins():
    """The one legitimate client win — the server lost its latest save."""
    client = {'turn': 6, 'iteration': 1}
    server = {'turn': 5, 'iteration': 9}
    merged, server_won = merge_sessions(client, server)
    assert merged is client
    assert server_won is False

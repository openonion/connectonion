"""SDK profile integration and QuickConnect migration regressions."""
from unittest.mock import MagicMock, Mock, patch
import httpx
import pytest
from tests.unit.synology_test_storage import STORAGE, isolated_keyring
from connectonion.useful_tools.synology import Synology, SynologyError
from connectonion.useful_tools.synology_profiles import ProfileStore

# === QuickConnect resolution ===


def test_resolve_quickconnect_puts_lan_before_relay():
    """The relay is throttled, so same-network addresses must be tried first."""
    from connectonion.useful_tools.synology import resolve_quickconnect

    body = {
        "server": {
            "port": 5001,
            "interface": [{"ip": "192.168.1.50"}],
            "ddns": "mynas.synology.me",
            "external": {"ip": "203.0.113.9"},
        },
    }
    with patch("connectonion.useful_tools.synology_discovery._read_discovery", return_value=body):
        candidates = resolve_quickconnect("mynas")

    assert candidates[0] == "https://192.168.1.50:5001"
    assert "https://mynas.synology.me:5001" in candidates
    assert candidates[-1] == "https://mynas.quickconnect.to"


def test_resolve_quickconnect_skips_null_ddns():
    """DSM reports a literal 'NULL' string when no DDNS is configured."""
    from connectonion.useful_tools.synology import resolve_quickconnect

    body = {"server": {"port": 5001, "interface": [], "ddns": "NULL"}}
    with patch("connectonion.useful_tools.synology_discovery._read_discovery", return_value=body):
        candidates = resolve_quickconnect("mynas")

    assert not any("NULL" in c for c in candidates)


def test_resolve_quickconnect_rejects_unknown_id():
    """errno 4 is 'Alias not found' — verified against the live endpoint."""
    from connectonion.useful_tools.synology import resolve_quickconnect

    body = {"errno": 4, "errinfo": "get_server_info.go:92[Alias not found]"}
    with patch("connectonion.useful_tools.synology_discovery._read_discovery", return_value=body):
        with pytest.raises(ValueError, match="not found"):
            resolve_quickconnect("nope")


# === Connection ladder ===


def test_pick_reachable_falls_past_unreachable_candidates():
    """An address that isn't on this network is expected, not fatal."""
    from connectonion.useful_tools.synology import pick_reachable

    def get(method, url, **kwargs):
        if "192.168" in url:
            raise SynologyError("Not reachable", "network_error")
        return {"success": True}

    with patch("connectonion.useful_tools.synology_discovery._read_discovery", side_effect=get):
        assert pick_reachable(["https://192.168.1.50:5001", "https://relay"]) == "https://relay"


def test_pick_reachable_falls_past_a_200_that_is_not_dsm():
    """A portal or proxy answering 200 with HTML is "not DSM", same as no answer.

    Seen for real: `co syno login openonion-nas` resolved four candidates and
    died with a JSONDecodeError on the first one instead of probing the rest.
    """
    from connectonion.useful_tools.synology import pick_reachable

    def get(method, url, **kwargs):
        if "portal" in url:
            raise SynologyError("Not DSM", "discovery_failed")
        return {"success": True}

    with patch("connectonion.useful_tools.synology_discovery._read_discovery", side_effect=get):
        assert pick_reachable(["https://portal", "https://relay"]) == "https://relay"


def test_pick_reachable_raises_when_nothing_answers():
    from connectonion.useful_tools.synology import pick_reachable

    with patch("connectonion.useful_tools.synology_discovery._read_discovery", side_effect=SynologyError("down", "network_error")):
        with pytest.raises(ValueError, match="Could not reach"):
            pick_reachable(["https://a", "https://b"])




def test_sdk_uses_one_saved_record_and_does_not_consult_legacy_env(tmp_path,monkeypatch):
    store=ProfileStore(tmp_path)
    store.save('home',{'url':'https://nas.test','account':'one'}, {'sid':'saved'},storage=STORAGE)
    monkeypatch.setenv('SYNOLOGY_URL','https://other.test')
    monkeypatch.setenv('SYNOLOGY_SID','other')
    client=Synology(store=store)
    assert client.url=='https://nas.test' and client.sid=='saved'


def test_sdk_explicit_connection_never_inherits_a_saved_session(tmp_path,monkeypatch):
    monkeypatch.setenv('SYNOLOGY_SID','other')
    client=Synology('https://nas.test','one','password',store=ProfileStore(tmp_path))
    assert client.sid=='' and not client._saved_profile
    assert not tmp_path.joinpath('profiles.json').exists()


def test_sdk_missing_profile_has_verified_login_migration_guidance(tmp_path):
    with pytest.raises(ValueError,match='co syno login'):
        Synology(store=ProfileStore(tmp_path))


def test_sdk_refresh_reuses_another_process_fresh_session(tmp_path):
    store=ProfileStore(tmp_path)
    profile=store.save('home',{'url':'https://nas.test','account':'one'}, {'sid':'old'},storage=STORAGE)
    client=Synology(store=store)
    store.update_auth(profile,{'sid':'fresh'})
    with patch('connectonion.useful_tools.synology_transport.SynologyTransport._login') as login:
        client._login()
    assert client.sid=='fresh'
    login.assert_not_called()


def test_sdk_logout_clears_local_auth_even_when_remote_is_unreachable(tmp_path):
    store=ProfileStore(tmp_path)
    store.save('home',{'url':'https://nas.test','account':'one'}, {'sid':'old'},storage=STORAGE)
    client=Synology(store=store)
    client._logout_remote=Mock(side_effect=SynologyError('Unavailable','network_error'))
    result=client.logout()
    assert result['local_auth_cleared'] and result['remote_invalidation']=='unconfirmed'
    assert store.credentials(store.selected())=={}


def test_sdk_dry_run_never_refreshes_or_saves_auth(tmp_path):
    store=ProfileStore(tmp_path)
    store.save('home',{'url':'https://nas.test','account':'one'}, {'password':'saved'},storage=STORAGE)
    client=Synology(store=store,dry_run=True)
    with pytest.raises(SynologyError) as error:
        client._login()
    assert error.value.code=='auth_required'
    assert 'sid' not in store.credentials(store.selected())

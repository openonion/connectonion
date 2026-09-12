"""Profiles publish only after verified login, and never mix NAS credentials."""
from pathlib import Path
import json
import stat
import os

import pytest
from tests.unit.synology_test_storage import STORAGE, isolated_keyring

from connectonion.useful_tools import synology_profiles as profiles


@pytest.fixture
def store(tmp_path):
    return profiles.ProfileStore(tmp_path)


def test_first_profile_default_and_replacement_keeps_other_accounts(store):
    first = store.save('home', {'url':'https://nas.example.test:5001','account':'one'},
                       {'password':'first','sid':'first-sid'}, storage=STORAGE)
    store.save('office', {'url':'https://office.example.test:5001','account':'two'},
               {'password':'second','sid':'second-sid'}, storage=STORAGE)
    assert store.selected()['name'] == 'home'
    store.use('office')
    assert store.selected()['name'] == 'office'
    assert store.credentials(store.selected())['password'] == 'second'
    assert 'first' not in store.index_path.read_text()
    assert store.selected('home')['id'] == first['id']


def test_secret_store_failure_cannot_replace_usable_profile(store, monkeypatch):
    first = store.save('home', {'url':'https://nas.example.test','account':'one'}, {'sid':'old'}, storage=STORAGE)
    def fail(*args, **kwargs):
        raise profiles.ProfileError('credential_store_unavailable', 'Unavailable')
    monkeypatch.setattr(store, '_write_secret', fail)
    with pytest.raises(profiles.ProfileError):
        store.save('home', {'url':'https://other.example.test','account':'two'}, {'sid':'new'}, storage='keyring')
    assert store.selected() == first
    assert store.credentials(first)['sid'] == 'old'


def test_logout_removes_auth_but_keeps_profile_and_default(store):
    profile = store.save('home', {'url':'https://nas.example.test','account':'one'}, {'sid':'old'}, storage=STORAGE)
    store.clear_auth(profile)
    kept = store.selected()
    assert kept['url'] == profile['url'] and kept['account'] == 'one'
    assert store.credentials(kept) == {}


@pytest.mark.skipif(os.name == "nt", reason="POSIX private-file fallback; Windows uses the synthetic OS keyring above")
def test_file_secrets_are_private_and_symlinks_rejected(store, tmp_path):
    profile = store.save('home', {'url':'https://nas.example.test','account':'one'}, {'sid':'opaque'}, storage=STORAGE)
    path = store.secret_path(profile['credential_ref'])
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    path.unlink()
    outside = tmp_path/'outside'
    outside.write_text('{"sid":"wrong"}')
    path.symlink_to(outside)
    with pytest.raises(profiles.ProfileError):
        store.credentials(profile)


def test_settings_reject_insecure_or_credential_bearing_endpoints(store):
    for url in ['http://nas.test', 'https://user:password@nas.test', 'https://nas.test/path', 'https://nas.test/?token=secret']:
        with pytest.raises(profiles.ProfileError):
            store.save('home', {'url':url,'account':'one'}, {'sid':'opaque'}, storage=STORAGE)
    assert not store.index_path.exists()


def test_profile_stale_refresh_cannot_update_a_replaced_account(store):
    old = store.save('home', {'url':'https://nas.test','account':'one'}, {'sid':'old'}, storage=STORAGE)
    store.save('home', {'url':'https://nas.test','account':'two'}, {'sid':'new'}, storage=STORAGE)
    with pytest.raises(profiles.ProfileError, match='changed'):
        store.update_auth(old, {'sid':'late'})
    assert store.credentials(store.selected())['sid'] == 'new'


def test_monitoring_passwords_cannot_enter_profile_settings(store):
    with pytest.raises(profiles.ProfileError):
        store.save('home', {'url':'https://nas.test','account':'one',
                           'snmp':{'host':'nas.test','password':'private'}}, {'sid':'opaque'}, storage=STORAGE)
    assert not store.index_path.exists()


def test_failed_old_secret_cleanup_does_not_report_published_login_as_failed(store, monkeypatch):
    store.save('home', {'url':'https://nas.test','account':'one'}, {'sid':'old'}, storage=STORAGE)
    def fail(profile):
        raise profiles.ProfileError('credential_store_unavailable', 'Locked')
    monkeypatch.setattr(store, '_delete_secret', fail)
    saved = store.save('home', {'url':'https://nas.test','account':'two'}, {'sid':'new'}, storage=STORAGE)
    assert store.selected()['account'] == 'two'
    assert saved['cleanup_warning'] == 'Previous credential record could not be removed; it is no longer selected.'

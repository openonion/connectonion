"""Importing the CLI must not pin later writes to the import-time home."""
from connectonion.cli.commands import keys_commands as keys


def test_per_host_key_write_uses_current_home_after_import(tmp_path, monkeypatch):
    home = tmp_path/'isolated-home'
    monkeypatch.setenv('HOME', str(home))
    monkeypatch.setenv('CO_DIR', str(home/'.co'))
    monkeypatch.setattr(keys.Path, 'home', staticmethod(lambda: home))
    monkeypatch.setattr('connectonion.address.derive_ssh_key', lambda *a, **kw: dict(private_key='fictional private fixture', public_line='fictional public fixture'))
    path = keys.per_host_key_path('staging')
    assert path == home/'.co/ssh/id_ed25519_staging'
    assert keys.write_per_host_ssh_key('fictional phrase', 'staging') == path
    assert path.read_text() == 'fictional private fixture'

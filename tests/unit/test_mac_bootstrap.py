"""Standard init prepares storage without mail mapping or a model request."""
import yaml
import sys

from connectonion.cli import mac_bootstrap
from connectonion.cli.host_service import HostService
from connectonion.cli.commands import init as init_commands
from connectonion import environment
from connectonion.rem import config


def test_bootstrap_reuses_profile_preserves_rem_and_reports_missing_connector(tmp_path, monkeypatch):
    root = tmp_path/'co'
    monkeypatch.setattr(environment, 'global_config_dir', lambda: root)
    monkeypatch.setattr(sys, 'platform', 'darwin')
    def initialize(ai, key, template, description, yes, force, path):
        assert ai is None and key is None and template is None and description is None
        assert yes is True and force is False
        directory = path/'.co'
        directory.mkdir(parents=True, exist_ok=True)
        target = directory/'host.yaml'
        if not target.exists():
            target.write_text('name: default\ntrust: careful\n')
    monkeypatch.setattr(init_commands, 'handle_init', initialize)
    monkeypatch.setattr(config, 'first_runner', lambda value: value)
    monkeypatch.setattr(HostService, 'start', lambda instance: {'configured': True, 'running': True, 'pid': 123})
    monkeypatch.setattr(mac_bootstrap, '_codex_readiness', lambda environment=None: {
        'codex_ready': False, 'codex_problem': 'Codex is not signed in', 'next_action': 'codex login'})
    result = mac_bootstrap.prepare_mac_host()
    assert result['rem_prepared'] and result['running'] and not result['codex_ready']
    assert result['watch_connector_ready'] is False
    runtime = root/'runtime'/'mac-host'
    host = yaml.safe_load((runtime/'.co'/'host.yaml').read_text())
    assert host['trust'] == 'strict' and host['directory'] == 'unlisted' and host['listen'] == []
    rem = root/'rem'/'config.yaml'
    original = rem.read_bytes()
    assert yaml.safe_load(original)['runner'] == 'codex'
    host['name'] = 'my custom name'
    (runtime/'.co'/'host.yaml').write_text(yaml.safe_dump(host))
    mac_bootstrap.prepare_mac_host()
    assert rem.read_bytes() == original
    assert yaml.safe_load((runtime/'.co'/'host.yaml').read_text())['name'] == 'my custom name'


def test_programmatic_global_setup_rejects_explicit_env_without_writing(tmp_path, monkeypatch):
    import pytest
    from connectonion.cli.host_service import HostServiceError
    monkeypatch.setattr(sys, 'platform', 'darwin')
    monkeypatch.setattr(environment, 'explicit_env_file', lambda: tmp_path/'account.env')
    monkeypatch.setattr(mac_bootstrap, '_prepare_profile', lambda *args: pytest.fail('must reject before writing'))
    with pytest.raises(HostServiceError, match='does not accept'):
        mac_bootstrap.prepare_mac_host()

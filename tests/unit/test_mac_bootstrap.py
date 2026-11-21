"""Mac Host setup leaves REM creation and consent to global initialization."""
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
    monkeypatch.setattr(mac_bootstrap, '_available_port', lambda: 8123)
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
    monkeypatch.setattr('connectonion.cli.codex_setup.claude_ready', lambda: False)
    result = mac_bootstrap.prepare_mac_host()
    # Neither Codex nor Claude Code is signed in: the Host starts on the managed default (#3170).
    from connectonion.core.usage import DEFAULT_MODEL
    assert not result['rem_prepared'] and result['running'] and result['model'] == DEFAULT_MODEL
    assert result['model_ready'] is True
    assert not (root/'rem').exists()
    assert result['watch_connector_ready'] is False
    runtime = root/'runtime'/'mac-host'
    host = yaml.safe_load((runtime/'.co'/'host.yaml').read_text())
    assert host['trust'] == 'strict' and host['directory'] == 'unlisted' and host['listen'] == []
    assert host['port'] == 8123 and host['model'] == DEFAULT_MODEL
    config.prepare(root/'rem')
    rem = root/'rem'/'config.yaml'
    original = rem.read_bytes()
    assert yaml.safe_load(original)['runner'] == 'codex'
    host['name'] = 'my custom name'
    (runtime/'.co'/'host.yaml').write_text(yaml.safe_dump(host))
    mac_bootstrap.prepare_mac_host()
    assert rem.read_bytes() == original
    assert yaml.safe_load((runtime/'.co'/'host.yaml').read_text())['name'] == 'my custom name'


def test_fresh_profile_chooses_an_unused_port_without_stopping_an_existing_host(monkeypatch):
    import socket
    attempted = []
    class Socket:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def bind(self, address):
            attempted.append(address)
            if address[1] == 8000:
                raise OSError('synthetic occupied port')
        def getsockname(self): return ('0.0.0.0', 49123)
    monkeypatch.setattr(socket, 'socket', lambda *args: Socket())
    assert mac_bootstrap._available_port() == 49123
    assert attempted == [('0.0.0.0', 8000), ('0.0.0.0', 0)]


def test_programmatic_global_setup_rejects_explicit_env_without_writing(tmp_path, monkeypatch):
    import pytest
    from connectonion.cli.host_service import HostServiceError
    monkeypatch.setattr(sys, 'platform', 'darwin')
    monkeypatch.setattr(environment, 'explicit_env_file', lambda: tmp_path/'account.env')
    monkeypatch.setattr(mac_bootstrap, '_prepare_profile', lambda *args: pytest.fail('must reject before writing'))
    with pytest.raises(HostServiceError, match='does not accept'):
        mac_bootstrap.prepare_mac_host()


def test_windows_profile_is_not_owner_only(tmp_path, monkeypatch):
    """Global co init from an elevated Windows shell made runtime/host with
    mkdir(mode=0o700): an owner-only ACL owned by Administrators. The logon
    task runs with the user's limited token, read no host.yaml, and printed
    "No .co/host.yaml here" every ten seconds while co said it was running."""
    from pathlib import Path
    monkeypatch.setattr(sys, 'platform', 'win32')
    monkeypatch.setattr(mac_bootstrap, '_available_port', lambda: 8123)
    monkeypatch.setattr(mac_bootstrap, 'default_model', lambda: 'claude-code')

    def initialize(ai, key, template, description, yes, force, path):
        (path/'.co').mkdir(parents=True, exist_ok=True)
        (path/'.co'/'host.yaml').write_text('name: default\n')
    monkeypatch.setattr(init_commands, 'handle_init', initialize)
    runtime = tmp_path/'co'/'runtime'/'host'
    modes = []
    real = Path.mkdir
    monkeypatch.setattr(Path, 'mkdir', lambda self, *a, **k: (modes.append((self, k.get('mode'))), real(self, *a, **k))[1])
    mac_bootstrap._prepare_profile(runtime)
    assert (runtime, 0o700) not in modes
    assert yaml.safe_load((runtime/'.co'/'host.yaml').read_text())['model'] == 'claude-code'

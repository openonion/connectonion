"""macOS lifecycle using an isolated filesystem and fake launchctl."""
import importlib
import plistlib
from pathlib import Path
import subprocess
import sys
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[2]/'connectonion'
PREFIX = '_host_service_fixture'
for suffix, path in [('', ROOT), ('.cli', ROOT/'cli')]:
    package = ModuleType(PREFIX+suffix)
    package.__path__ = [str(path)]
    sys.modules[package.__name__] = package


def module():
    return importlib.import_module(PREFIX+'.cli.host_service')


class Launchctl:
    def __init__(self):
        self.calls = []
        self.running = False
    def __call__(self, args, **kwargs):
        self.calls.append((args, kwargs))
        action = args[1]
        if action == 'print':
            return subprocess.CompletedProcess(args, 0 if self.running else 113,
                'state = running\n pid = 12345\n' if self.running else '', '')
        if action == 'bootstrap':
            self.running = True
        if action == 'bootout':
            self.running = False
        return subprocess.CompletedProcess(args, 0, '', '')


@pytest.fixture
def service(tmp_path, monkeypatch):
    project = tmp_path/'project with spaces'
    project.mkdir()
    (project/'agent.py').write_text('# synthetic fixture')
    api = module()
    monkeypatch.setattr(api.sys, 'platform', 'darwin')
    control = Launchctl()
    return api.HostService(project, home=tmp_path/'home', runner=control, uid=501), control


def test_install_and_rerun_use_one_service_without_secrets(service, monkeypatch):
    instance, control = service
    monkeypatch.setenv('OPENONION_API_KEY', 'synthetic-must-not-persist')
    result = instance.start()
    assert result['running'] and result['pid'] == 12345
    data = plistlib.loads(instance.plist.read_bytes())
    assert data['WorkingDirectory'] == str(instance.project)
    assert data['ProgramArguments'][-1] == 'host'
    assert 'synthetic-must-not-persist' not in instance.plist.read_text()
    assert data['KeepAlive'] is True and data['RunAtLoad'] is True
    instance.start()
    assert sum(args[1] == 'bootstrap' for args, _ in control.calls) == 1


def test_status_does_not_create_files(service):
    instance, _ = service
    assert instance.status() == {'configured': False, 'running': False, 'pid': None, 'device_ready': False}
    assert not instance.plist.exists()


def test_stop_then_restart_and_uninstall_keep_project(service):
    instance, _ = service
    instance.start()
    assert not instance.stop()['running']
    assert instance.plist.exists()
    assert instance.start()['running']
    instance.uninstall()
    assert not instance.plist.exists() and (instance.project/'agent.py').exists()


def test_modified_service_is_preserved(service):
    instance, _ = service
    instance.start()
    data = plistlib.loads(instance.plist.read_bytes())
    data['ProgramArguments'] = ['custom-user-command']
    instance.plist.write_bytes(plistlib.dumps(data))
    before = instance.plist.read_bytes()
    with pytest.raises(module().HostServiceError, match='modified'):
        instance.start()
    assert instance.plist.read_bytes() == before


def test_missing_agent_and_unsupported_platform_are_actionable(service, monkeypatch):
    instance, _ = service
    (instance.project/'agent.py').unlink()
    with pytest.raises(module().HostServiceError, match='agent.py'):
        instance.start()
    monkeypatch.setattr(module().sys, 'platform', 'linux')
    with pytest.raises(module().HostServiceError, match='macOS'):
        instance.status()

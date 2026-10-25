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


def test_restart_waits_for_launchd_to_retire_its_previous_job(service, monkeypatch):
    instance, control = service
    instance.start()
    instance.stop()
    failures = []
    def retiring(args, **kwargs):
        if args[1] == 'bootstrap' and not failures:
            failures.append(True)
            return subprocess.CompletedProcess(args, 5, '', 'Bootstrap failed: 5: Input/output error')
        return control(args, **kwargs)
    instance.runner = retiring
    monkeypatch.setattr(module().time, 'sleep', lambda _: None)
    assert instance.start()['running'] and failures


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


def test_selected_config_root_is_persisted(service):
    instance, _ = service
    instance.config_root = instance.home/'alternate-co'
    instance.start()
    data = plistlib.loads(instance.plist.read_bytes())
    assert data['EnvironmentVariables']['AGENT_CONFIG_PATH'] == str(instance.config_root)


def test_selected_codex_paths_are_persisted_and_reused(service):
    instance, control = service
    instance.provider_paths = {'CODEX_HOME': str(instance.home/'codex-profile'), 'CODEX_CMD': '/synthetic/codex'}
    instance.start()
    rerun = module().HostService(instance.project, home=instance.home, runner=control, uid=501)
    rerun.start()
    data = plistlib.loads(rerun.plist.read_bytes())
    assert data['EnvironmentVariables']['CODEX_HOME'] == str(instance.home/'codex-profile')
    assert data['EnvironmentVariables']['CODEX_CMD'] == '/synthetic/codex'


def test_custom_runtime_path_and_relative_codex_are_resolved(service, tmp_path, monkeypatch):
    instance, control = service
    binaries = tmp_path/'npm-prefix'/'bin'
    binaries.mkdir(parents=True)
    command = binaries/'codex'
    command.write_text('# synthetic executable')
    command.chmod(0o700)
    monkeypatch.setenv('PATH', str(binaries))
    monkeypatch.setenv('CODEX_CMD', './npm-prefix/bin/codex')
    monkeypatch.chdir(tmp_path)
    selected = module().HostService(instance.project, home=instance.home, runner=control, uid=501)
    selected.start()
    data = plistlib.loads(selected.plist.read_bytes())
    assert data['EnvironmentVariables']['CODEX_CMD'] == str(command.resolve())
    assert str(binaries) in data['EnvironmentVariables']['PATH'].split(':')


def test_rerun_reuses_options_and_upgrade_replaces_owned_interpreter(service, monkeypatch):
    instance, control = service
    instance.port = 8001
    instance.env_file = instance.home/'selected.env'
    instance.start()
    api = module()
    rerun = api.HostService(instance.project, home=instance.home, runner=control, uid=501)
    rerun.start()
    assert rerun.port == 8001 and rerun.env_file == instance.env_file
    monkeypatch.setattr(api.sys, 'executable', '/synthetic/upgraded/python')
    rerun.start()
    data = plistlib.loads(instance.plist.read_bytes())
    assert data['ProgramArguments'][0] == '/synthetic/upgraded/python'
    assert sum(args[1] == 'bootstrap' for args, _ in control.calls) == 2


def test_lifecycle_actions_cannot_overlap(service):
    instance, _ = service
    with instance._locked():
        with pytest.raises(module().HostServiceError, match='Another service action'):
            instance.start()


def test_interrupted_first_plist_write_reuses_saved_intent(service, monkeypatch):
    instance, control = service
    instance.port = 8001
    original = instance._atomic
    def interrupted(path, data):
        if path == instance.plist:
            raise OSError('synthetic interruption')
        original(path, data)
    monkeypatch.setattr(instance, '_atomic', interrupted)
    with pytest.raises(OSError):
        instance.start()
    rerun = module().HostService(instance.project, home=instance.home, runner=control, uid=501)
    assert rerun.start()['running'] and rerun.port == 8001


@pytest.mark.parametrize('listener_pid,expected', [('12345', True), ('99999', False), ('', False)])
def test_native_health_requires_our_listener_not_a_shared_identity(service, monkeypatch, listener_pid, expected):
    import httpx
    instance, _ = service
    instance.native_codex = True
    (instance.project/'.co').mkdir()
    (instance.project/'.co'/'host.yaml').write_text('port: 8123\n')
    calls = []
    def listener(args, **kwargs):
        calls.append(args)
        return subprocess.CompletedProcess(args, 0 if listener_pid else 1,
                                           'p'+listener_pid+'\nn*:8124\n', '')
    instance.runner = listener
    def response(request):
        assert request.url.port == 8124  # actual listener may override YAML via AGENT_PORT
        return httpx.Response(200, json={'status': 'healthy'} if request.url.path == '/health' else {'address': '0x'+'a'*64})
    client = httpx.Client
    monkeypatch.setattr(httpx, 'Client', lambda **kwargs: client(transport=httpx.MockTransport(response), **kwargs))
    assert instance._native_healthy(12345) is expected
    assert '-i4TCP' in calls[0]
    assert not (instance.project/'.co'/'keys').exists()

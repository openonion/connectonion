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
    assert data['ProgramArguments'][-3:] == ['host', '--agent', 'agent.py']
    assert 'synthetic-must-not-persist' not in instance.plist.read_text()
    assert data['KeepAlive'] is True and data['RunAtLoad'] is True
    instance.start()
    assert sum(args[1] == 'bootstrap' for args, _ in control.calls) == 1


def test_status_does_not_create_files(service):
    instance, _ = service
    assert instance.status() == {'configured': False, 'running': False, 'pid': None, 'device_ready': False}
    assert not instance.plist.exists()


@pytest.mark.parametrize('action', ['status', 'stop', 'uninstall'])
def test_lifecycle_observation_and_stop_ignore_invalid_codex_command(service, monkeypatch, action):
    instance, control = service
    instance.start()
    monkeypatch.setenv('CODEX_CMD', 'codex --profile work')
    rerun = module().HostService(instance.project, home=instance.home, runner=control, uid=501)
    getattr(rerun, action)()
    assert control.calls


def test_generic_service_does_not_validate_or_persist_native_codex_override(service, monkeypatch):
    instance, control = service
    monkeypatch.setenv('CODEX_CMD', 'codex --profile work')
    selected = module().HostService(instance.project, home=instance.home, runner=control, uid=501)
    assert selected.start()['running']
    assert 'CODEX_CMD' not in plistlib.loads(selected.plist.read_bytes())['EnvironmentVariables']


def test_native_start_validates_provider_command_before_service_registration(service, monkeypatch):
    instance, control = service
    monkeypatch.setenv('CODEX_CMD', 'codex --profile work')
    selected = module().HostService(instance.project, home=instance.home, runner=control, uid=501, native_codex=True)
    with pytest.raises(module().HostServiceError, match='one executable'):
        selected.start()
    assert not control.calls and not selected.plist.exists()


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
    instance.builtin = False
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
    instance.native_codex = True
    instance._native_healthy = lambda pid: True
    instance.provider_paths = {'CODEX_HOME': str(instance.home/'codex-profile'), 'CODEX_CMD': '/synthetic/codex'}
    instance.start()
    rerun = module().HostService(instance.project, home=instance.home, runner=control, uid=501)
    rerun._native_healthy = lambda pid: True
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
    selected = module().HostService(instance.project, home=instance.home, runner=control, uid=501, native_codex=True)
    selected._native_healthy = lambda pid: True
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


def test_a_project_without_agent_py_serves_the_built_in_agent(service):
    """#3170: an agent is host.yaml plus skills; no agent.py is the default, not an error."""
    instance, control = service
    (instance.project/'agent.py').unlink()
    fresh = module().HostService(instance.project, home=instance.home, runner=control, uid=501)
    fresh._native_healthy = lambda pid: True
    fresh.start()
    data = plistlib.loads(fresh.plist.read_bytes())
    assert data['ProgramArguments'][-2:] == ['host', '--serve']


class Systemctl:
    """A fake `systemctl --user`: one unit that runs once started."""
    def __init__(self):
        self.calls = []
        self.active = False
    def __call__(self, args, **kwargs):
        self.calls.append(tuple(args[2:]))
        action = args[2]
        if action in ('start', 'restart'):
            self.active = True
        if action == 'disable':
            self.active = False
        if action == 'show':
            out = 'MainPID=4321\nActiveState=active\n' if self.active else 'MainPID=0\nActiveState=inactive\n'
            return subprocess.CompletedProcess(args, 0, out, '')
        return subprocess.CompletedProcess(args, 0, '', '')


def test_linux_runs_the_same_host_as_a_systemd_user_unit(tmp_path):
    """#3170: co init leaves a Host running on Linux too, as a user unit, no root."""
    profile = tmp_path/'profile'
    profile.mkdir()
    control = Systemctl()
    service = module().SystemdHostService(profile, home=tmp_path/'home', runner=control, builtin=True)
    state = service.start()
    assert state == {'configured': True, 'running': True, 'pid': 4321, 'device_ready': False}
    unit = service.unit.read_text()
    assert service.unit.parent == tmp_path/'home'/'.config'/'systemd'/'user'
    assert '"host" "--serve"' in unit and f'WorkingDirectory={profile.resolve()}' in unit
    assert 'Restart=always' in unit and 'WantedBy=default.target' in unit
    assert ('enable', service.unit_name) in control.calls
    # A rerun with nothing changed starts it, without rewriting or reloading.
    control.calls.clear()
    service.start()
    assert ('daemon-reload',) not in control.calls and ('start', service.unit_name) in control.calls
    assert service.stop()['running'] is False
    service.uninstall()
    assert not service.unit.exists()


def test_linux_project_with_agent_py_serves_it_and_never_writes_secrets(tmp_path, monkeypatch):
    project = tmp_path/'project'
    project.mkdir()
    (project/'agent.py').write_text('# synthetic')
    monkeypatch.setenv('OPENAI_API_KEY', 'sk-synthetic-secret')
    service = module().SystemdHostService(project, home=tmp_path/'home', runner=Systemctl(), port=8123)
    service.start()
    unit = service.unit.read_text()
    assert '"host" "--agent" "agent.py" "--port" "8123"' in unit
    assert 'sk-synthetic-secret' not in unit


def test_the_platform_picks_launchd_or_systemd(tmp_path, monkeypatch):
    api = module()
    monkeypatch.setattr(api.sys, 'platform', 'darwin')
    assert type(api.host_service(tmp_path)).__name__ == 'HostService'
    monkeypatch.setattr(api.sys, 'platform', 'linux')
    monkeypatch.setattr(api.shutil, 'which', lambda name: '/usr/bin/systemctl')
    monkeypatch.setattr(api, '_user_systemd_ready', lambda: True)
    assert type(api.host_service(tmp_path)).__name__ == 'SystemdHostService'
    monkeypatch.setattr(api.sys, 'platform', 'win32')
    assert type(api.host_service(tmp_path)).__name__ == 'ScheduledTaskHostService'
    monkeypatch.setattr(api.sys, 'platform', 'freebsd14')
    with pytest.raises(api.HostServiceUnavailable, match='co host --serve'):
        api.host_service(tmp_path)


def test_linux_without_a_systemd_user_session_has_no_background_service(tmp_path, monkeypatch):
    """CI runners, containers and SSH logins without linger have systemctl but no user manager:
    that is a machine without a background service, not a failed start (rc39 release gate)."""
    api = module()
    monkeypatch.setattr(api.sys, 'platform', 'linux')
    monkeypatch.setattr(api.shutil, 'which', lambda name: '/usr/bin/systemctl')
    monkeypatch.setattr(api.subprocess, 'run', lambda args, **kwargs: subprocess.CompletedProcess(
        args, 1, '', 'Failed to connect to bus: No medium found'))
    with pytest.raises(api.HostServiceUnavailable, match='systemctl --user is not reachable.*co host --serve'):
        api.host_service(tmp_path)


class Schtasks:
    def __init__(self):
        self.calls, self.created, self.running = [], False, False

    def __call__(self, args, **kwargs):
        assert args[0] == 'schtasks' and 'shell' not in kwargs
        action = args[1]
        self.calls.append(tuple(args[1:]))
        if action == '/Create':
            self.created = True
        elif action == '/Run':
            self.running = True
        elif action == '/End':
            self.running = False
        elif action == '/Delete':
            self.created = False
        elif action == '/Query':
            if not self.created:
                return subprocess.CompletedProcess(args, 1, '', 'ERROR: The system cannot find the file specified.')
            state = 'Running' if self.running else 'Ready'
            return subprocess.CompletedProcess(args, 0, f'"\\{args[3]}","N/A","{state}"\r\n', '')
        return subprocess.CompletedProcess(args, 0, 'SUCCESS', '')


def test_windows_runs_the_same_host_as_a_logon_task(tmp_path):
    """On Windows co init used to stop at "needs macOS or Linux"; the Host now
    runs as a Scheduled Task at logon, as the logged-in user, no admin."""
    profile = tmp_path/'profile'
    profile.mkdir()
    control = Schtasks()
    service = module().ScheduledTaskHostService(profile, home=tmp_path/'home', runner=control, builtin=True)
    state = service.start()
    assert state == {'configured': True, 'running': True, 'pid': None, 'device_ready': False}
    script = service.unit.read_text(encoding='utf-8')
    assert ' host --serve >> ' in script and f'cd /d "{profile.resolve()}"' in script
    assert 'goto run' in script  # starts again after an exit, like Restart=always
    create = next(call for call in control.calls if call[0] == '/Create')
    assert ('/SC', 'ONLOGON') == create[2:4] and service.task_name in create and '/RU' not in create
    assert service.stop()['running'] is False
    service.uninstall()
    assert not service.unit.exists() and control.created is False


def test_windows_task_serves_agent_py_and_never_writes_secrets(tmp_path, monkeypatch):
    project = tmp_path/'project'
    project.mkdir()
    (project/'agent.py').write_text('# synthetic')
    monkeypatch.setenv('OPENAI_API_KEY', 'sk-synthetic-secret')
    service = module().ScheduledTaskHostService(project, home=tmp_path/'home', runner=Schtasks(), port=8123)
    service.start()
    script = service.unit.read_text(encoding='utf-8')
    assert ' host --agent agent.py --port 8123 >> ' in script
    assert 'sk-synthetic-secret' not in script


def test_windows_task_script_has_one_cr_per_line(tmp_path, monkeypatch):
    """The .cmd was joined with \\r\\n and then written in text mode, which on
    Windows turned every line ending into \\r\\r\\n."""
    project = tmp_path/'project'
    project.mkdir()
    real = Path.write_text

    def windows_text_mode(self, data, encoding=None, errors=None, newline=None):
        return real(self, data, encoding=encoding, errors=errors, newline='\r\n' if newline is None else newline)
    monkeypatch.setattr(Path, 'write_text', windows_text_mode)
    service = module().ScheduledTaskHostService(project, home=tmp_path/'home', runner=Schtasks(), builtin=True)
    service.start()
    raw = service.unit.read_bytes()
    assert b'\r\r' not in raw and raw.count(b'\r\n') == raw.count(b'\n')


def test_windows_logs_folder_is_not_owner_only(tmp_path, monkeypatch):
    """mkdir(mode=0o700) on Windows gives an owner-only ACL. From an elevated
    shell the owner is Administrators, so the logon task, which runs with the
    user's limited token, could not write its log and exited at once."""
    project = tmp_path/'project'
    project.mkdir()
    modes = []
    real = Path.mkdir
    monkeypatch.setattr(Path, 'mkdir', lambda self, *a, **k: (modes.append(k.get('mode')), real(self, *a, **k))[1])
    service = module().ScheduledTaskHostService(project, home=tmp_path/'home', runner=Schtasks(), builtin=True)
    service.start()
    assert 0o700 not in modes

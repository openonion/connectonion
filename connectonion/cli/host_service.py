"""Own one macOS user service for a project Host; no account reads on import."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import plistlib
import re
import shutil
import subprocess
import sys
import tempfile
import time
from contextlib import contextmanager


class HostServiceError(ValueError):
    """Actionable lifecycle failure, without launchctl environment/log contents."""


class HostServiceUnavailable(HostServiceError):
    """This machine has no user service manager to keep a Host running; `co init` skips the step."""


class HostService:
    def __init__(self, project: Path, *, home: Path | None = None,
                 runner=subprocess.run, uid: int | None = None,
                 port: int | None = None, env_file: Path | None = None,
                 builtin: bool | None = None, native_codex: bool | None = None):
        self.project = project.resolve()
        self.home = home or Path.home()
        self.runner = runner
        self.uid = uid if uid is not None else getattr(os, 'getuid', lambda: 0)()
        self.port = port
        # builtin: serve the built-in agent that host.yaml's `model:` picks
        # (`co host --serve`); otherwise the project's own agent.py. None
        # decides from the project: no agent.py means built-in (#3170).
        # native_codex is the pre-#3170 name, kept for callers and saved options.
        self.builtin = builtin if builtin is not None else native_codex
        self.env_file = env_file.expanduser().resolve() if env_file else None
        self.explicit_config_root = os.environ.get('AGENT_CONFIG_PATH')
        self.config_root = Path(self.explicit_config_root or self.home/'.co').expanduser().resolve()
        self.provider_paths = {key: os.environ[key] for key in ('CODEX_HOME', 'CODEX_CMD') if os.environ.get(key)}
        self.execution_path = os.pathsep.join(str(Path(item).expanduser().resolve())
                                             for item in os.environ.get('PATH', os.defpath).split(os.pathsep) if item)
        digest = hashlib.sha256(str(self.project).encode()).hexdigest()[:16]
        self.label = 'ai.connectonion.host.' + digest
        self.domain = f'gui/{self.uid}'
        self.target = f'{self.domain}/{self.label}'
        self.plist = self.home/'Library'/'LaunchAgents'/(self.label+'.plist')
        self.logs = self.home/'.co'/'host-services'/digest
        self.baseline = self.logs/'service.json'

    @property
    def native_codex(self):
        """The pre-#3170 name for `builtin`."""
        return self.builtin

    @native_codex.setter
    def native_codex(self, value):
        self.builtin = value

    def _prepare_provider(self):
        # Observation and shutdown must work even with invalid provider settings.
        # Generic agent.py services load their provider configuration normally.
        if not self.builtin:
            self.provider_paths = {}
            return
        if 'CODEX_HOME' in self.provider_paths:
            self.provider_paths['CODEX_HOME'] = str(Path(self.provider_paths['CODEX_HOME']).expanduser().resolve())
        from ..codex_cli import resolve_codex
        command = self.provider_paths.get('CODEX_CMD') or resolve_codex()
        if command:
            expanded = Path(command).expanduser()
            if expanded.is_file():
                command = str(expanded.resolve())
            elif len(command.split()) != 1 or command.startswith('-'):
                raise HostServiceError('Background CODEX_CMD must name one executable, not arguments or credentials. Next: co host --help')
            else:
                command = shutil.which(command) or command
            self.provider_paths['CODEX_CMD'] = command

    def _mac(self):
        if sys.platform != 'darwin':
            raise HostServiceError('Background Host currently supports macOS user sessions. Next: co host')

    def _ctl(self, *arguments, allowed=(0,)):
        self._mac()
        try:
            result = self.runner(['/bin/launchctl', *arguments], stdin=subprocess.DEVNULL,
                                 capture_output=True, text=True, timeout=15,
                                 env={'PATH': os.defpath, 'HOME': str(self.home)})
        except (OSError, subprocess.TimeoutExpired):
            raise HostServiceError('Cannot contact the macOS user service manager. Next: co host --status') from None
        if result.returncode not in allowed:
            raise HostServiceError('macOS service operation failed; use an unlocked logged-in user session. Next: co host --status')
        return result

    def status(self) -> dict:
        result = self._ctl('print', self.target, allowed=(0, 3, 113))
        match = re.search(r'^\s*pid\s*=\s*(\d+)\s*$', result.stdout, re.MULTILINE) if result.returncode == 0 else None
        running = re.search(r'^\s*state\s*=\s*running\s*$', result.stdout, re.MULTILINE)
        pid = int(match.group(1)) if match and running and int(match.group(1)) > 0 else None
        return {'configured': self.plist.exists(), 'running': pid is not None,
                'pid': pid, 'device_ready': False}

    def _definition(self) -> dict:
        arguments = [sys.executable, '-m', 'connectonion.cli.main']
        if self.env_file:
            arguments.extend(['--env-file', str(self.env_file.expanduser().resolve())])
        arguments.append('host')
        arguments.extend(['--serve'] if self.builtin else ['--agent', 'agent.py'])
        if self.port is not None:
            if not 1 <= self.port <= 65535:
                raise HostServiceError('Port must be between 1 and 65535. Next: co host --help')
            arguments.extend(['--port', str(self.port)])
        return {'Label': self.label, 'ProgramArguments': arguments,
                'WorkingDirectory': str(self.project), 'RunAtLoad': True,
                'KeepAlive': True, 'ThrottleInterval': 10,
                'EnvironmentVariables': {'HOME': str(self.home), 'AGENT_CONFIG_PATH': str(self.config_root), **self.provider_paths,
                    'PATH': os.pathsep.join(item for item in dict.fromkeys([str(Path(sys.executable).parent), *self.execution_path.split(os.pathsep),
                                                         '/opt/homebrew/bin', '/usr/local/bin', *os.defpath.split(os.pathsep)]) if item)},
                'StandardOutPath': str(self.logs/'stdout.log'),
                'StandardErrorPath': str(self.logs/'stderr.log')}

    def _previous(self):
        if not self.plist.exists() and not self.baseline.exists():
            return None
        try:
            record = json.loads(self.baseline.read_text())
            if record['version'] != 1 or record['project'] != str(self.project):
                raise ValueError('unknown ownership')
            options = record['options']
            if not isinstance(options, dict):
                raise ValueError('invalid saved options')
            provider_paths = options.get('provider_paths', {})
            if (not isinstance(options, dict) or not {'port', 'env_file', 'config_root'}.issubset(options)
                    or (options['port'] is not None and (type(options['port']) is not int or not 1 <= options['port'] <= 65535))
                    or not isinstance(options['config_root'], str) or not Path(options['config_root']).is_absolute()
                    or (options['env_file'] is not None and (not isinstance(options['env_file'], str) or not Path(options['env_file']).is_absolute()))
                    or not isinstance(provider_paths, dict) or set(provider_paths) - {'CODEX_HOME', 'CODEX_CMD'}
                    or any(not isinstance(value, str) or not value or any(char in value for char in '\0\r\n') for value in provider_paths.values())
                    or type(options.get('native_codex', False)) is not bool
                    or type(options.get('builtin', False)) is not bool
                    or not isinstance(options.get('execution_path', ''), str)):
                raise ValueError('invalid saved options')
            if not self.plist.exists():
                return record
            current = self.plist.read_bytes()
            allowed = [record['definition'], record.get('previous_definition')]
            if not any(isinstance(definition, dict) and current == plistlib.dumps(definition) for definition in allowed):
                raise ValueError('edited definition')
            return record
        except (OSError, ValueError, KeyError, TypeError):
            raise HostServiceError('Existing service configuration is modified or unreadable; preserved. Next: co host --status') from None

    @contextmanager
    def _locked(self):
        self._mac()
        import fcntl
        self.logs.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.logs.parent.chmod(0o700)
        self.logs.chmod(0o700)
        descriptor = os.open(self.logs/'lifecycle.lock', os.O_CREAT | os.O_RDWR | getattr(os, 'O_NOFOLLOW', 0), 0o600)
        try:
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise HostServiceError('Another service action is running. Next: co host --status') from None
            yield
        finally:
            os.close(descriptor)

    def _atomic(self, path: Path, data: bytes):
        with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as file:
            temporary = Path(file.name)
            try:
                file.write(data)
                file.flush()
                os.fsync(file.fileno())
                os.chmod(temporary, 0o600)
                os.replace(temporary, path)
            finally:
                temporary.unlink(missing_ok=True)

    def start(self) -> dict:
        self._mac()
        with self._locked():
            return self._start()

    def _start(self) -> dict:
        previous = self._previous()
        if previous:
            options = previous['options']
            if self.port is None:
                self.port = options['port']
            if self.env_file is None and options['env_file']:
                self.env_file = Path(options['env_file'])
            if not self.explicit_config_root:
                self.config_root = Path(options['config_root'])
            self.provider_paths = {**options.get('provider_paths', {}), **self.provider_paths}
            self.execution_path = os.pathsep.join(dict.fromkeys([*self.execution_path.split(os.pathsep),
                                                                *options.get('execution_path', '').split(os.pathsep)]))
            if self.builtin is None:
                self.builtin = options.get('builtin', options.get('native_codex', False))
        if self.builtin is None:
            self.builtin = not (self.project/'agent.py').is_file()
        if not self.builtin and not (self.project/'agent.py').is_file():
            raise HostServiceError('No agent.py in this project. Next: co host --background, to serve the built-in agent')
        self._prepare_provider()
        definition = self._definition()
        self.plist.parent.mkdir(parents=True, exist_ok=True)
        for name in ('stdout.log', 'stderr.log'):
            descriptor = os.open(self.logs/name, os.O_CREAT | os.O_APPEND | os.O_WRONLY | getattr(os, 'O_NOFOLLOW', 0), 0o600)
            os.fchmod(descriptor, 0o600)
            os.close(descriptor)
        changed = not self.plist.exists() or self.plist.read_bytes() != plistlib.dumps(definition)
        if changed:
            record = {'version': 1, 'project': str(self.project), 'definition': definition,
                      'previous_definition': plistlib.loads(self.plist.read_bytes()) if self.plist.exists() else None,
                      'options': {'port': self.port, 'env_file': str(self.env_file) if self.env_file else None,
                                  'config_root': str(self.config_root), 'builtin': bool(self.builtin),
                                  'provider_paths': self.provider_paths, 'execution_path': self.execution_path}}
            # Save old+new known definitions before replacing the plist. A crash
            # between files is recoverable without accepting arbitrary edits.
            self._atomic(self.baseline, json.dumps(record).encode())
            self._atomic(self.plist, plistlib.dumps(definition))
        self._ctl('enable', self.target)
        state = self.status()
        if state['running'] and not changed:
            if not self.builtin or self._native_healthy(state['pid']):
                return {**state, **({'host_healthy': True} if self.builtin else {})}
        loaded = self._ctl('print', self.target, allowed=(0, 3, 113)).returncode == 0
        if loaded:
            self._ctl('bootout', self.target)
        # bootout may return before launchd has retired the previous job. A
        # bootstrap during that interval returns EIO even for an unchanged plist.
        # Retry only that code, bounded; invalid sessions/config still fail.
        retirement_deadline = time.monotonic() + 5
        while True:
            result = self._ctl('bootstrap', self.domain, str(self.plist), allowed=(0, 5))
            if result.returncode == 0:
                break
            if time.monotonic() >= retirement_deadline:
                raise HostServiceError('macOS could not load the service; its files were preserved. Next: co host --status')
            time.sleep(.25)
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            state = self.status()
            if state['running'] and (not self.builtin or self._native_healthy(state['pid'])):
                return {**state, **({'host_healthy': True} if self.builtin else {})}
            time.sleep(.25)
        raise HostServiceError('Service is configured but a matching healthy Host was not observed; inspect its status and logs. Next: co host --status')

    def _native_healthy(self, pid: int) -> bool:
        """Require the launchd process to own the healthy IPv4 listener.

        Profiles can share the global identity, so matching /info addresses
        alone cannot prove that this service started successfully.
        """
        import httpx
        try:
            # Discover the real listener: explicit flags, AGENT_PORT and YAML
            # can choose different ports. Do not reread account files to guess.
            listener = self.runner(['/usr/sbin/lsof', '-nP', '-a', '-p', str(pid),
                                    '-i4TCP', '-sTCP:LISTEN', '-Fpn'],
                                   stdin=subprocess.DEVNULL, capture_output=True,
                                   text=True, timeout=2,
                                   env={'PATH': os.defpath, 'HOME': str(self.home)})
            fields = listener.stdout.splitlines()
            if listener.returncode != 0 or f'p{pid}' not in fields:
                return False
            ports = {int(match.group(1)) for field in fields
                     if (match := re.fullmatch(r'n.+:(\d+)', field))}
            for port in sorted(ports):
                with httpx.Client(timeout=1, trust_env=False) as client:
                    health = client.get(f'http://127.0.0.1:{port}/health')
                    info = client.get(f'http://127.0.0.1:{port}/info')
                if (health.status_code == 200 and health.json().get('status') == 'healthy'
                        and info.status_code == 200
                        and re.fullmatch(r'0x[0-9a-fA-F]{64}', info.json().get('address', '')) is not None):
                    return True
            return False
        except (OSError, ValueError, KeyError, TypeError, AttributeError, subprocess.TimeoutExpired, httpx.HTTPError):
            return False

    def stop(self) -> dict:
        with self._locked():
            return self._stop()

    def _stop(self) -> dict:
        self._mac()
        self._ctl('disable', self.target)
        loaded = self._ctl('print', self.target, allowed=(0, 3, 113)).returncode == 0
        if loaded:
            self._ctl('bootout', self.target)
        return self.status()

    def uninstall(self) -> dict:
        with self._locked():
            self._stop()
            self.plist.unlink(missing_ok=True)
            self.baseline.unlink(missing_ok=True)
            return self.status()


class SystemdHostService:
    """The Linux counterpart of HostService: one systemd user unit per project Host.

    Same lifecycle (start, status, stop, uninstall) and the same command line,
    `co host --serve` for the built-in agent or `co host --agent agent.py`.
    No root: a user unit, with linger needed to keep running after logout.
    """

    def __init__(self, project: Path, *, home: Path | None = None, runner=subprocess.run,
                 port: int | None = None, env_file: Path | None = None,
                 builtin: bool | None = None, native_codex: bool | None = None):
        self.project = project.resolve()
        self.home = home or Path.home()
        self.runner = runner
        self.port = port
        self.env_file = env_file.expanduser().resolve() if env_file else None
        builtin = builtin if builtin is not None else native_codex
        self.builtin = (not (self.project/'agent.py').is_file()) if builtin is None else builtin
        self.config_root = Path(os.environ.get('AGENT_CONFIG_PATH') or self.home/'.co').expanduser().resolve()
        digest = hashlib.sha256(str(self.project).encode()).hexdigest()[:16]
        self.unit_name = f'connectonion-host-{digest}.service'
        self.unit = self.home/'.config'/'systemd'/'user'/self.unit_name
        self.logs = self.home/'.co'/'host-services'/digest

    def _systemctl(self, *args, allowed=(0,)):
        try:
            result = self.runner(['systemctl', '--user', *args], stdin=subprocess.DEVNULL,
                                 capture_output=True, text=True, timeout=30)
        except (OSError, subprocess.TimeoutExpired):
            raise HostServiceError('systemctl is not available. Next: co host --serve, to run it in this terminal') from None
        if result.returncode not in allowed:
            raise HostServiceError(f"systemctl --user {' '.join(args)} failed. Log into a systemd user session; "
                                   "to keep it running while logged out, run: loginctl enable-linger")
        return result

    def _definition(self) -> str:
        def quote(value: str) -> str:
            return '"' + value.replace('\\', '\\\\').replace('"', '\\"') + '"'
        arguments = [sys.executable, '-m', 'connectonion.cli.main']
        if self.env_file:
            arguments.extend(['--env-file', str(self.env_file)])
        arguments.append('host')
        arguments.extend(['--serve'] if self.builtin else ['--agent', 'agent.py'])
        if self.port is not None:
            if not 1 <= self.port <= 65535:
                raise HostServiceError('Port must be between 1 and 65535. Next: co host --help')
            arguments.extend(['--port', str(self.port)])
        path = os.pathsep.join(dict.fromkeys([str(Path(sys.executable).parent),
                                              *os.environ.get('PATH', os.defpath).split(os.pathsep)]))
        return '\n'.join([
            '[Unit]', 'Description=ConnectOnion Host', '',
            '[Service]',
            'ExecStart=' + ' '.join(quote(argument) for argument in arguments),
            f'WorkingDirectory={self.project}',
            f'Environment={quote("HOME=" + str(self.home))}',
            f'Environment={quote("AGENT_CONFIG_PATH=" + str(self.config_root))}',
            f'Environment={quote("PATH=" + path)}',
            'Restart=always', 'RestartSec=10',
            f'StandardOutput=append:{self.logs/"stdout.log"}',
            f'StandardError=append:{self.logs/"stderr.log"}', '',
            '[Install]', 'WantedBy=default.target', '',
        ])

    def status(self) -> dict:
        result = self._systemctl('show', self.unit_name, '-p', 'MainPID', '-p', 'ActiveState', allowed=(0, 1, 3, 4, 5))
        fields = dict(line.split('=', 1) for line in result.stdout.splitlines() if '=' in line)
        pid = int(fields.get('MainPID', '0') or 0)
        running = fields.get('ActiveState') == 'active' and pid > 0
        return {'configured': self.unit.exists(), 'running': running, 'pid': pid if running else None,
                'device_ready': False}

    def start(self) -> dict:
        if not self.builtin and not (self.project/'agent.py').is_file():
            raise HostServiceError('No agent.py in this project. Next: co host --background, to serve the built-in agent')
        self.logs.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.unit.parent.mkdir(parents=True, exist_ok=True)
        definition = self._definition()
        changed = not self.unit.exists() or self.unit.read_text() != definition
        if changed:
            with tempfile.NamedTemporaryFile('w', dir=self.unit.parent, delete=False) as file:
                file.write(definition)
            os.replace(file.name, self.unit)
            self._systemctl('daemon-reload')
        self._systemctl('enable', self.unit_name)
        self._systemctl('restart' if changed else 'start', self.unit_name)
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            state = self.status()
            if state['running']:
                return state
            time.sleep(.25)
        raise HostServiceError(f'Service is configured but not running; inspect it. Next: systemctl --user status {self.unit_name}')

    def stop(self) -> dict:
        self._systemctl('disable', '--now', self.unit_name, allowed=(0, 1, 5))
        return self.status()

    def uninstall(self) -> dict:
        self.stop()
        self.unit.unlink(missing_ok=True)
        self._systemctl('daemon-reload')
        return self.status()


class ScheduledTaskHostService(SystemdHostService):
    """The Windows counterpart: one Scheduled Task per project Host, run at logon.

    Same lifecycle and command line as the systemd unit. Task Scheduler has no
    Restart=always, so the task runs a small .cmd that starts the Host again ten
    seconds after it exits; its output goes to the same logs folder. No admin:
    the task runs as the logged-in user, only while that user is logged on.
    """

    def __init__(self, project: Path, **options):
        super().__init__(project, **options)
        digest = self.unit_name.removeprefix('connectonion-host-').removesuffix('.service')
        self.task_name = f'ConnectOnion Host {digest}'
        self.unit = self.logs/'run-host.cmd'

    def _schtasks(self, *args, allowed=(0,)):
        try:
            result = self.runner(['schtasks', *args], stdin=subprocess.DEVNULL,
                                 capture_output=True, text=True, timeout=30)
        except (OSError, subprocess.TimeoutExpired):
            raise HostServiceError('schtasks is not available. Next: co host --serve, to run it in this terminal') from None
        if result.returncode not in allowed:
            raise HostServiceError(f"schtasks {args[0]} failed: {(result.stderr or result.stdout).strip()}. "
                                   "Next: co host --serve, to run it in this terminal")
        return result

    def _definition(self) -> str:
        arguments = [sys.executable, '-m', 'connectonion.cli.main']
        if self.env_file:
            arguments.extend(['--env-file', str(self.env_file)])
        arguments.append('host')
        arguments.extend(['--serve'] if self.builtin else ['--agent', 'agent.py'])
        if self.port is not None:
            if not 1 <= self.port <= 65535:
                raise HostServiceError('Port must be between 1 and 65535. Next: co host --help')
            arguments.extend(['--port', str(self.port)])
        command = subprocess.list2cmdline(arguments)
        return '\n'.join([
            '@echo off', 'rem ConnectOnion Host, started at logon by Task Scheduler.',
            f'cd /d "{self.project}"',
            f'set "AGENT_CONFIG_PATH={self.config_root}"', 'set "PYTHONIOENCODING=utf-8"',
            ':run', f'{command} >> "{self.logs/"stdout.log"}" 2>> "{self.logs/"stderr.log"}"',
            'timeout /t 10 /nobreak > nul', 'goto run', '',
        ])

    def status(self) -> dict:
        result = self._schtasks('/Query', '/TN', self.task_name, '/FO', 'CSV', '/NH', allowed=(0, 1))
        running = result.returncode == 0 and '"Running"' in result.stdout
        return {'configured': self.unit.exists() and result.returncode == 0, 'running': running,
                'pid': None, 'device_ready': False}

    def start(self) -> dict:
        if not self.builtin and not (self.project/'agent.py').is_file():
            raise HostServiceError('No agent.py in this project. Next: co host --background, to serve the built-in agent')
        # No mode=0o700: on Windows it sets an owner-only ACL, and from an elevated
        # shell the owner is Administrators, which the task's limited token cannot write.
        # The folder is in the user's profile, which is already private to them.
        self.logs.mkdir(parents=True, exist_ok=True)
        definition = self._definition()
        if not self.unit.exists() or self.unit.read_text(encoding='utf-8') != definition:
            self.unit.write_text(definition, encoding='utf-8', newline='\r\n')
        self._schtasks('/Create', '/F', '/SC', 'ONLOGON', '/RL', 'LIMITED', '/TN', self.task_name,
                       '/TR', f'"{self.unit}"')
        if not self.status()['running']:
            self._schtasks('/Run', '/TN', self.task_name)
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            state = self.status()
            if state['running']:
                return state
            time.sleep(.25)
        raise HostServiceError(f'Task is configured but not running; inspect it. Next: schtasks /Query /TN "{self.task_name}" /V')

    def stop(self) -> dict:
        self._schtasks('/End', '/TN', self.task_name, allowed=(0, 1))
        self._schtasks('/Change', '/TN', self.task_name, '/DISABLE', allowed=(0, 1))
        return self.status()

    def uninstall(self) -> dict:
        self._schtasks('/End', '/TN', self.task_name, allowed=(0, 1))
        self._schtasks('/Delete', '/TN', self.task_name, '/F', allowed=(0, 1))
        self.unit.unlink(missing_ok=True)
        return self.status()


def host_service(project: Path, **options):
    """The background-service manager for this platform: launchd on macOS,
    systemd on Linux, Task Scheduler on Windows."""
    if sys.platform == 'darwin':
        return HostService(project, **options)
    if sys.platform.startswith('linux') and shutil.which('systemctl'):
        if not _user_systemd_ready():
            raise HostServiceUnavailable('A background Host needs a systemd user session, and systemctl --user is not '
                                         'reachable here (a container, CI, or SSH without linger). '
                                         'Next: co host --serve, to run it in this terminal')
        return SystemdHostService(project, **options)
    if sys.platform == 'win32':
        return ScheduledTaskHostService(project, **options)
    raise HostServiceUnavailable('A background Host needs macOS or Linux with systemd, or Windows. Next: co host --serve, to run it in this terminal')


def _user_systemd_ready() -> bool:
    """Whether this login has a systemd user manager to talk to; the binary alone is not enough."""
    try:
        result = subprocess.run(['systemctl', '--user', 'show-environment'], stdin=subprocess.DEVNULL,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0

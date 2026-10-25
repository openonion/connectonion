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


class HostService:
    def __init__(self, project: Path, *, home: Path | None = None,
                 runner=subprocess.run, uid: int | None = None,
                 port: int | None = None, env_file: Path | None = None,
                 native_codex: bool | None = None):
        self.project = project.resolve()
        self.home = home or Path.home()
        self.runner = runner
        self.uid = uid if uid is not None else getattr(os, 'getuid', lambda: 0)()
        self.port = port
        self.native_codex = native_codex
        self.env_file = env_file.expanduser().resolve() if env_file else None
        self.explicit_config_root = os.environ.get('AGENT_CONFIG_PATH')
        self.config_root = Path(self.explicit_config_root or self.home/'.co').expanduser().resolve()
        self.provider_paths = {key: os.environ[key] for key in ('CODEX_HOME', 'CODEX_CMD') if os.environ.get(key)}
        if 'CODEX_HOME' in self.provider_paths:
            self.provider_paths['CODEX_HOME'] = str(Path(self.provider_paths['CODEX_HOME']).expanduser().resolve())
        command = self.provider_paths.get('CODEX_CMD') or shutil.which('codex')
        if command:
            expanded = Path(command).expanduser()
            if expanded.is_file():
                command = str(expanded.resolve())
            elif len(command.split()) != 1 or command.startswith('-'):
                raise HostServiceError('Background CODEX_CMD must name one executable, not arguments or credentials. Next: co host --help')
            else:
                command = shutil.which(command) or command
            self.provider_paths['CODEX_CMD'] = command
        self.execution_path = os.pathsep.join(str(Path(item).expanduser().resolve())
                                             for item in os.environ.get('PATH', os.defpath).split(os.pathsep) if item)
        digest = hashlib.sha256(str(self.project).encode()).hexdigest()[:16]
        self.label = 'ai.connectonion.host.' + digest
        self.domain = f'gui/{self.uid}'
        self.target = f'{self.domain}/{self.label}'
        self.plist = self.home/'Library'/'LaunchAgents'/(self.label+'.plist')
        self.logs = self.home/'.co'/'host-services'/digest
        self.baseline = self.logs/'service.json'

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
        if self.native_codex:
            arguments.append('--native-codex')
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
            if self.native_codex is None:
                self.native_codex = options.get('native_codex', False)
        if not self.native_codex and not (self.project/'agent.py').is_file():
            raise HostServiceError('No agent.py in this project. Next: co create my-agent')
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
                                  'config_root': str(self.config_root), 'native_codex': bool(self.native_codex),
                                  'provider_paths': self.provider_paths, 'execution_path': self.execution_path}}
            # Save old+new known definitions before replacing the plist. A crash
            # between files is recoverable without accepting arbitrary edits.
            self._atomic(self.baseline, json.dumps(record).encode())
            self._atomic(self.plist, plistlib.dumps(definition))
        self._ctl('enable', self.target)
        state = self.status()
        if state['running'] and not changed:
            if not self.native_codex or self._native_healthy(state['pid']):
                return {**state, **({'host_healthy': True} if self.native_codex else {})}
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
            if state['running'] and (not self.native_codex or self._native_healthy(state['pid'])):
                return {**state, **({'host_healthy': True} if self.native_codex else {})}
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

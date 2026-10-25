"""Own one macOS user service for a project Host; no account reads on import."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import plistlib
import re
import subprocess
import sys
import tempfile
import time


class HostServiceError(ValueError):
    """Actionable lifecycle failure, without launchctl environment/log contents."""


class HostService:
    def __init__(self, project: Path, *, home: Path | None = None,
                 runner=subprocess.run, uid: int | None = None,
                 port: int | None = None, env_file: Path | None = None):
        self.project = project.resolve()
        self.home = home or Path.home()
        self.runner = runner
        self.uid = uid if uid is not None else getattr(os, 'getuid', lambda: 0)()
        self.port, self.env_file = port, env_file
        digest = hashlib.sha256(str(self.project).encode()).hexdigest()[:16]
        self.label = 'ai.connectonion.host.' + digest
        self.domain = f'gui/{self.uid}'
        self.target = f'{self.domain}/{self.label}'
        self.plist = self.home/'Library'/'LaunchAgents'/(self.label+'.plist')
        self.logs = self.home/'.co'/'host-services'/digest

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
        pid = int(match.group(1)) if match else None
        return {'configured': self.plist.exists(), 'running': pid is not None,
                'pid': pid, 'device_ready': False}

    def _definition(self) -> dict:
        arguments = [sys.executable, '-m', 'connectonion.cli.main']
        if self.env_file:
            arguments.extend(['--env-file', str(self.env_file.expanduser().resolve())])
        arguments.append('host')
        if self.port is not None:
            if not 1 <= self.port <= 65535:
                raise HostServiceError('Port must be between 1 and 65535. Next: co host --help')
            arguments.extend(['--port', str(self.port)])
        return {'Label': self.label, 'ProgramArguments': arguments,
                'WorkingDirectory': str(self.project), 'RunAtLoad': True,
                'KeepAlive': True, 'ThrottleInterval': 10,
                'EnvironmentVariables': {'HOME': str(self.home),
                    'PATH': os.pathsep.join([str(Path(sys.executable).parent), '/opt/homebrew/bin', '/usr/local/bin', os.defpath])},
                'StandardOutPath': str(self.logs/'stdout.log'),
                'StandardErrorPath': str(self.logs/'stderr.log')}

    def _preserve_modified(self, expected):
        if not self.plist.exists():
            return
        try:
            actual = plistlib.loads(self.plist.read_bytes())
        except (OSError, ValueError, plistlib.InvalidFileException):
            raise HostServiceError('Existing service configuration is modified or unreadable; preserved. Next: co host --status') from None
        if actual != expected:
            raise HostServiceError('Existing service configuration was modified; preserved. Next: co host --status')

    def start(self) -> dict:
        self._mac()
        if not (self.project/'agent.py').is_file():
            raise HostServiceError('No agent.py in this project. Next: co create my-agent')
        definition = self._definition()
        self._preserve_modified(definition)
        self.plist.parent.mkdir(parents=True, exist_ok=True)
        self.logs.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.logs.chmod(0o700)
        for name in ('stdout.log', 'stderr.log'):
            descriptor = os.open(self.logs/name, os.O_CREAT | os.O_APPEND | os.O_WRONLY, 0o600)
            os.close(descriptor)
        if not self.plist.exists():
            with tempfile.NamedTemporaryFile(dir=self.plist.parent, delete=False) as file:
                temporary = Path(file.name)
                try:
                    file.write(plistlib.dumps(definition))
                    file.flush()
                    os.fsync(file.fileno())
                    os.chmod(temporary, 0o600)
                    os.replace(temporary, self.plist)
                finally:
                    temporary.unlink(missing_ok=True)
        self._ctl('enable', self.target)
        state = self.status()
        if state['running']:
            return state
        loaded = self._ctl('print', self.target, allowed=(0, 3, 113)).returncode == 0
        if loaded:
            self._ctl('bootout', self.target)
        self._ctl('bootstrap', self.domain, str(self.plist))
        for _ in range(20):
            state = self.status()
            if state['running']:
                return state
            time.sleep(.25)
        raise HostServiceError('Service is configured but its Host process did not stay running. Next: co host --status')

    def stop(self) -> dict:
        self._mac()
        self._ctl('disable', self.target)
        loaded = self._ctl('print', self.target, allowed=(0, 3, 113)).returncode == 0
        if loaded:
            self._ctl('bootout', self.target)
        return self.status()

    def uninstall(self) -> dict:
        self.stop()
        self.plist.unlink(missing_ok=True)
        return self.status()

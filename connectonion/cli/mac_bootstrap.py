"""The always-on Host that `co init` leaves running, built from existing init/Host/REM pieces.

`co init` prepares one profile, ~/.co/runtime/mac-host on macOS (its pre-#3170
name, kept so an upgraded Mac keeps its one service) and ~/.co/runtime/host on
Linux, writes the model it should use into that profile's host.yaml, and starts
it as a user service: launchd on macOS, systemd on Linux (#3170).
"""
import sys
from pathlib import Path

import yaml

from .host_service import HostServiceError, host_service


def _available_port() -> int:
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        try:
            listener.bind(('0.0.0.0', 8000))
        except OSError:
            listener.bind(('0.0.0.0', 0))
        return listener.getsockname()[1]


def profile_dir() -> Path:
    """Where the always-on Host's own project lives."""
    from ..environment import global_config_dir
    return global_config_dir()/'runtime'/('mac-host' if sys.platform == 'darwin' else 'host')


def default_model() -> str:
    """What this machine can run without a key: a logged-in Codex, then Claude Code, else the managed default."""
    from ..core.usage import DEFAULT_MODEL
    from .codex_setup import claude_ready
    if _codex_readiness()['codex_ready']:
        return 'codex'
    if claude_ready():
        return 'claude-code'
    return DEFAULT_MODEL


def _prepare_profile(runtime: Path) -> None:
    from ..rem.files import atomic_write
    from .commands.init import handle_init
    fresh = not (runtime/'.co'/'host.yaml').exists()
    if sys.platform == 'win32':
        # mode=0o700 sets an owner-only ACL on Windows; from an elevated shell the owner
        # is Administrators and the logon task's limited token cannot read the profile.
        runtime.mkdir(parents=True, exist_ok=True)
    else:
        runtime.mkdir(parents=True, exist_ok=True, mode=0o700)
        runtime.chmod(0o700)
    handle_init(ai=None, key=None, template=None, description=None,
                yes=True, force=False, path=runtime)
    path = runtime/'.co'/'host.yaml'
    config = yaml.safe_load(path.read_text()) or {}
    if fresh:
        config.update(name='my-mac' if sys.platform == 'darwin' else 'my-host', trust='strict',
                      directory='unlisted', listen=[], port=_available_port())
    if 'model' not in config:
        # A profile from before #3170 always served native Codex; keep it doing so.
        config['model'] = default_model() if fresh else 'codex'
    elif not fresh:
        return
    atomic_write(path, yaml.safe_dump(config, sort_keys=False))


def _codex_readiness(environment: dict | None = None) -> dict:
    import os
    import shlex
    import subprocess

    from ..codex_cli import INSTALL_COMMAND, resolve_codex
    if environment is None:
        environment = {key: os.environ[key] for key in ('PATH', 'HOME', 'TMPDIR', 'CODEX_HOME', 'CODEX_CMD', 'SYSTEMROOT') if key in os.environ}
    command = environment.get('CODEX_CMD') or resolve_codex(path=environment.get('PATH', os.defpath))
    if not command:
        return {'codex_ready': False, 'codex_problem': 'Codex CLI is not installed',
                'next_action': INSTALL_COMMAND}
    try:
        result = subprocess.run([command, 'login', 'status'], env=environment,
                                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL, timeout=15)
        signed_in = result.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        signed_in = False
    return {'codex_ready': signed_in, 'codex_problem': '' if signed_in else 'Codex login check did not pass',
            'next_action': '' if signed_in else shlex.join([command, 'login'])}


def _model_readiness(model: str, environment: dict) -> dict:
    """Whether the configured native provider can answer; a managed model needs no login."""
    provider = model.partition('/')[0]
    if provider == 'codex':
        return _codex_readiness(environment=environment)
    if provider == 'claude-code':
        from .codex_setup import claude_ready
        ready = claude_ready()
        return {'codex_ready': True, 'model_ready': ready, 'model_problem': '' if ready else 'Claude Code is not logged in',
                'next_action': '' if ready else 'claude auth login'}
    return {'codex_ready': True, 'model_ready': True}


def prepare_host() -> dict:
    """Prepare and start the always-on Host; global init owns the consent-aware REM step."""
    from ..environment import explicit_env_file, global_config_dir
    if explicit_env_file() is not None:
        raise HostServiceError('Global Host setup does not accept --env-file. Next: co init')
    runtime = profile_dir()
    _prepare_profile(runtime)
    from .co_ai.native_host import configured_model
    model = configured_model(runtime/'.co')
    service = host_service(runtime, builtin=True)
    state = service.start()
    environment = service._definition()['EnvironmentVariables'] if hasattr(service, 'plist') else None
    readiness = _model_readiness(model, environment)
    readiness.setdefault('model_ready', readiness['codex_ready'])
    return {**state, 'profile': str(runtime), 'model': model,
            'rem_prepared': (global_config_dir()/'rem'/'config.yaml').is_file(),
            **readiness, 'watch_connector_ready': False}


prepare_mac_host = prepare_host  # pre-#3170 name


def serve_project(project: Path, *, port: int | None = None, model: str | None = None) -> None:
    """Serve this directory's Host in the foreground with the built-in agent `model:` picks."""
    from ..environment import global_config_dir
    from ..network.host.server import host
    from .co_ai.native_host import host_agent_factory
    co_dir = project/'.co'
    if not (co_dir/'host.yaml').is_file():
        raise HostServiceError('No .co/host.yaml here. Next: co init')
    options = {}
    if project.resolve() == profile_dir().resolve():
        # The profile init records the creator as admin. Strict trust retains the
        # existing authenticated Host boundary; setup does not grant arbitrary callers.
        options = {'trust': 'strict', 'rem_root': global_config_dir()/'rem'}
    host(host_agent_factory(project, co_dir, model), port=port, co_dir=co_dir, **options)


def serve_native_mac(project: Path, *, port: int | None = None) -> None:
    """`co host --native-codex`, from before #3170: this profile, native Codex."""
    serve_project(project, port=port, model='codex')

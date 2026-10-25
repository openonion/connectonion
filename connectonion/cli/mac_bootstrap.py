"""Standard Mac preparation uses existing init/Host/REM boundaries, not a second CLI."""
from pathlib import Path

import yaml

from .host_service import HostService, HostServiceError


def _prepare_profile(runtime: Path) -> None:
    from .commands.init import handle_init
    from ..rem.files import atomic_write
    fresh = not (runtime/'.co'/'host.yaml').exists()
    runtime.mkdir(parents=True, exist_ok=True, mode=0o700)
    runtime.chmod(0o700)
    handle_init(ai=None, key=None, template=None, description=None,
                yes=True, force=False, path=runtime)
    if fresh:
        path = runtime/'.co'/'host.yaml'
        config = yaml.safe_load(path.read_text()) or {}
        config.update(name='my-mac', trust='strict', directory='unlisted', listen=[])
        atomic_write(path, yaml.safe_dump(config, sort_keys=False))


def _prepare_rem(root: Path) -> None:
    from ..rem.config import prepare, default_config
    from ..rem.files import atomic_write, maintenance_lock
    with maintenance_lock(root):
        fresh = not (root/'config.yaml').exists()
        prepare(root)
        if fresh:
            # Keep the owner's Codex selection even when login is not ready;
            # do not silently select another runner during device setup.
            atomic_write(root/'config.yaml', yaml.safe_dump(default_config(), sort_keys=False))


def _codex_readiness(environment: dict | None = None) -> dict:
    import os
    import shutil
    import subprocess
    if environment is None:
        environment = {key: os.environ[key] for key in ('PATH', 'HOME', 'TMPDIR', 'CODEX_HOME', 'CODEX_CMD', 'SYSTEMROOT') if key in os.environ}
    command = environment.get('CODEX_CMD') or shutil.which('codex', path=environment.get('PATH', os.defpath))
    if not command:
        return {'codex_ready': False, 'codex_problem': 'Codex CLI is not installed',
                'next_action': 'npm install -g @openai/codex'}
    try:
        result = subprocess.run([command, 'login', 'status'], env=environment,
                                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL, timeout=15)
        signed_in = result.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        signed_in = False
    return {'codex_ready': signed_in, 'codex_problem': '' if signed_in else 'Codex login check did not pass',
            'next_action': '' if signed_in else 'codex login'}


def prepare_mac_host() -> dict:
    """Prepare storage/profile and a persistent native Host; never scan sources."""
    import sys
    if sys.platform != 'darwin':
        raise HostServiceError('Background Mac setup requires macOS. Next: co init')
    from ..environment import global_config_dir, explicit_env_file
    if explicit_env_file() is not None:
        raise HostServiceError('Global Mac setup does not accept --env-file. Next: co init --background')
    root = global_config_dir()
    runtime = root/'runtime'/'mac-host'
    _prepare_profile(runtime)
    _prepare_rem(root/'rem')
    service = HostService(runtime, native_codex=True)
    state = service.start()
    return {**state, 'profile': str(runtime), 'rem_prepared': True,
            **_codex_readiness(environment=service._definition()['EnvironmentVariables']), 'watch_connector_ready': False}


def serve_native_mac(project: Path, *, port: int | None = None) -> None:
    from ..environment import global_config_dir
    from ..network.host.server import host
    from .co_ai.native_host import NativeCodexHostAgent
    co_dir = project/'.co'
    if not (co_dir/'host.yaml').is_file():
        raise HostServiceError('Initialize the native Host profile first. Next: co init ./')
    # The project init records the creator as admin. Strict trust retains the
    # existing authenticated Host boundary; setup does not grant arbitrary callers.
    host(lambda: NativeCodexHostAgent(project, co_dir=co_dir),
         port=port, co_dir=co_dir, trust='strict',
         rem_root=global_config_dir()/'rem')

"""Signed Control Center commands and authenticated descriptor/status pushes."""
import asyncio
import logging

from ..control_center.runtime import RuntimeErrorState

logger = logging.getLogger(__name__)


async def send_control_center(send_msg, session_id, controller):
    try:
        state = await asyncio.to_thread(controller.snapshot)
    except (RuntimeErrorState, OSError):
        state = {'schema': 1, 'status': 'unavailable', 'active': None, 'history': [], 'updates': {},
                 'error': {'code': 'runtime_unavailable', 'message': 'Control Center state is unavailable'}}
    await send_msg({'type': 'CONTROL_CENTER_STATE', 'session_id': session_id, 'state': state})
    await send_msg({'type': 'CONTROL_CENTER_APP', 'session_id': session_id, 'app': state.get('active')})


async def watch_control_center(send_msg, conn, controller):
    last = None
    while True:
        if conn.get('authenticated') and not conn.get('session_sync_only'):
            stamps = []
            for name in ('state.json', 'updates.json'):
                try:
                    stat = (controller.runtime.state_dir / name).stat()
                    stamps.append((stat.st_mtime_ns, stat.st_size))
                except FileNotFoundError:
                    stamps.append(None)
            stamp = (conn.get('session_id'), tuple(stamps))
            if stamp != last:
                await send_control_center(send_msg, conn.get('session_id'), controller)
                last = stamp
        await asyncio.sleep(2)


async def handle_control_center(data, send_msg, conn, routes):
    request_id = data.get('request_id')
    if not isinstance(request_id, str) or not 1 <= len(request_id) <= 128:
        return
    response = {'type': 'CONTROL_CENTER_RESULT', 'request_id': request_id, 'ok': False}
    try:
        if not conn.get('authenticated'):
            raise PermissionError('A signed authenticated Control Center command is required')
        if not conn.get('signed_commands'):
            # React can negotiate Session Sync without signing every legacy frame.
            # These author commands still require their own verified envelope.
            from ..auth import authenticated_command_payload
            from .connect import replay_check_for
            data, error = authenticated_command_payload(data, conn.get('agent_address'),
                conn.get('recipient_address'), replay_check_for(conn, routes))
            if error:
                raise PermissionError(error)
            request_id = data.get('request_id')
            if not isinstance(request_id, str) or not 1 <= len(request_id) <= 128:
                raise ValueError('Invalid signed request ID')
            response['request_id'] = request_id
        controller = routes.get('control_center')
        if controller is None:
            raise RuntimeErrorState('Control Center is not configured on this Host')
        trust = routes.get('trust_agent')
        admin = bool(trust and trust.is_admin(conn.get('agent_address')))
        result = await controller.command(data.get('action'), data.get('payload', {}), is_admin=admin)
        response.update(ok=True, result=result)
    except (PermissionError, ValueError, RuntimeErrorState) as exc:
        response['error'] = {'code': type(exc).__name__, 'message': str(exc)}
    except Exception:
        logger.exception('Control Center command failed')
        response['error'] = {'code': 'unavailable', 'message': 'Control Center command could not complete'}
    await send_msg(response)

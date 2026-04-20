"""
Execution Control plugin - Pause/Resume/Stop agent execution via WebSocket.

Checks for control messages at each iteration boundary (before_iteration).
Pause blocks the agent thread until resume or stop is received.
Stop uses the existing stop_signal mechanism.

Protocol:
    Client → Server:  {type: 'EXECUTION_CONTROL', action: 'pause'|'resume'|'stop'}
    Server → Client:  {type: 'EXECUTION_STATE', state: 'running'|'paused'|'stopped'}

Usage:
    from connectonion import Agent
    from connectonion.useful_plugins import execution_control

    agent = Agent("worker", plugins=[execution_control])
    host(agent)
"""

import time
from typing import TYPE_CHECKING
from ..core.events import before_iteration

if TYPE_CHECKING:
    from ..core.agent import Agent


def _drain_control_messages(agent: 'Agent') -> str | None:
    """Drain all pending EXECUTION_CONTROL messages, return the last action."""
    action = None
    for msg in agent.io.receive_all('EXECUTION_CONTROL'):
        action = msg.get('action')
    return action


@before_iteration
def check_execution_control(agent: 'Agent') -> None:
    """Check for pause/resume/stop signals at iteration boundaries."""
    if not agent.io:
        return

    action = _drain_control_messages(agent)

    if action == 'stop':
        agent.current_session['stop_signal'] = 'User requested stop.'
        agent.io.send({'type': 'EXECUTION_STATE', 'state': 'stopped'})
        return

    if action == 'pause':
        agent.io.send({'type': 'EXECUTION_STATE', 'state': 'paused'})

        while True:
            time.sleep(0.2)
            inner_action = _drain_control_messages(agent)
            if inner_action == 'resume':
                agent.io.send({'type': 'EXECUTION_STATE', 'state': 'running'})
                return
            if inner_action == 'stop':
                agent.current_session['stop_signal'] = 'User requested stop.'
                agent.io.send({'type': 'EXECUTION_STATE', 'state': 'stopped'})
                return
            # Check if connection closed while paused
            if agent.io.receive_all('io_closed'):
                return


execution_control = [check_execution_control]

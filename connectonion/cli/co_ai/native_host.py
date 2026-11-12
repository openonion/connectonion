"""A hosted Codex turn uses the native plugin directly, never an outer model."""
import json
from pathlib import Path

from ...core.agent import Agent
from ...core.llm import LLM
from ...plugins.coding_agents import CodexPlugin


class _NoOuterModel(LLM):
    """Metadata for Host/Agent plumbing; inference through this path is forbidden."""
    model = 'codex (native account default)'

    def complete(self, *args, **kwargs):
        raise RuntimeError('Native Codex Host must not invoke an outer model')

    def structured_complete(self, *args, **kwargs):
        raise RuntimeError('Native Codex Host must not invoke an outer model')


class NativeCodexHostAgent(Agent):
    """Reuse Agent session/lifecycle and bounded Codex plugin without COAI routing.

    Host authenticates/claims the session before input(). Remote callers supply
    text, not cwd/model/native-thread IDs. The operator fixes the workspace and
    model here; the existing plugin enforces Host permission ceilings.
    """
    def __init__(self, workspace: Path, *, co_dir: Path, model: str = ''):
        self.native_model = model
        plugin = CodexPlugin(workspace=workspace, use_host_permissions=True)
        super().__init__('Mac Codex', llm=_NoOuterModel(), plugins=[plugin],
                         co_dir=co_dir, state_dir=co_dir, log=False, quiet=True,
                         system_prompt='This Host delegates explicit owner tasks directly to Codex.')

    def input(self, prompt, *, images=None, files=None, **kwargs):
        if images or files:
            raise ValueError('Native Codex Host currently accepts text tasks; transcribe selected audio first')
        return super().input(prompt, **kwargs)

    def _run_iteration_loop(self, max_iterations):
        self.current_session['iteration'] = 1
        self._invoke_events('before_iteration')
        result = self.execute_tool('codex', {
            'prompt': self.current_session['user_prompt'], 'model': self.native_model,
            'session_id': self._native_thread(),
        })
        if result['status'] != 'success':
            raise RuntimeError('Codex task did not complete; inspect the provider result')
        try:
            answer = json.loads(result['result'])
        except (ValueError, TypeError):
            raise RuntimeError('Codex returned an invalid result') from None
        if (not isinstance(answer, dict) or answer.get('error') or answer.get('exit_code') not in (None, 0)
                or answer.get('status') == 'cancelled' or not isinstance(answer.get('last_message'), str)
                or not answer['last_message'].strip()):
            raise RuntimeError('Codex did not return a completed text answer')
        text = answer['last_message']
        self.current_session['messages'].append({'role': 'assistant', 'content': text, 'id': self._next_trace_id()})
        self._invoke_events('after_iteration')
        return text, 'natural'

    def _native_thread(self):
        for event in reversed(self.current_session.get('trace', [])):
            if (event.get('type') == 'provider_invocation' and event.get('provider') == 'codex'
                    and event.get('status') in ('completed', 'cancelled', 'failed')
                    and isinstance(event.get('sessionId'), str) and 0 < len(event['sessionId']) <= 512):
                return event['sessionId']
        return ''

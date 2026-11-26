"""A hosted Codex or Claude Code turn uses the native plugin directly, never an outer model.

`model:` in .co/host.yaml picks what a Host serves (#3170):

    model: codex                  native Codex, the account you are logged into
    model: claude-code            native Claude Code, the account you are logged into
    model: claude-code/<model>    native Claude Code on that model (codex/<model> too)
    model: co/gemini-4-hydrogen   the co-ai agent on that model (the default)

A `restricted:` block beside `model: claude-code/<model>` makes that Claude Code
safe to serve to outside callers: only the tools and skills it lists, the
project's own CLAUDE.md and skills, no MCP server, and the verified caller in
the system prompt (see ClaudeRestriction).

`host_agent_factory()` turns that one line into the function `host()` calls for
every conversation, so neither the frontend nor an agent.py changes when it does.
"""
import json
import re
from pathlib import Path

import yaml

from ...core.agent import Agent
from ...core.llm import LLM
from ...core.usage import DEFAULT_MODEL
from ...plugins.coding_agents import ClaudeCodePlugin, CodexPlugin
from ...useful_tools.claude_code import ClaudeRestriction


class _NoOuterModel(LLM):
    """Metadata for Host/Agent plumbing; inference through this path is forbidden."""

    def __init__(self, label: str):
        self.model = label

    def complete(self, *args, **kwargs):
        raise RuntimeError('A native Host must not invoke an outer model')

    def structured_complete(self, *args, **kwargs):
        raise RuntimeError('A native Host must not invoke an outer model')


class _NativeHostAgent(Agent):
    """Reuse Agent session/lifecycle and a bounded coding plugin without COAI routing.

    Host authenticates/claims the session before input(). Remote callers supply
    text, not cwd/model/native-thread IDs. The operator fixes the workspace and
    model here; the plugin enforces Host permission ceilings.
    """
    provider = ''
    tool = ''
    login_command = ''

    def __init__(self, name: str, plugin, *, co_dir: Path, model: str, label: str):
        self.native_model = model
        super().__init__(name, llm=_NoOuterModel(label), plugins=[plugin],
                         co_dir=co_dir, state_dir=co_dir, log=False, quiet=True,
                         system_prompt=f'This Host delegates explicit owner tasks directly to {name}.')

    def input(self, prompt, *, images=None, files=None, **kwargs):
        if images or files:
            raise ValueError(f'{self.name} currently accepts text tasks; transcribe selected audio first')
        return super().input(prompt, **kwargs)

    def _run_iteration_loop(self, max_iterations):
        self.current_session['iteration'] = 1
        self._invoke_events('before_iteration')
        result = self.execute_tool(self.tool, {
            'prompt': self.current_session['user_prompt'], 'model': self.native_model,
            'session_id': self._native_thread(),
        })
        if result['status'] != 'success':
            text = self._failure_reply(_provider_error(result['result']))
        else:
            text = self._completed_text(result['result'])
        self.current_session['messages'].append({'role': 'assistant', 'content': text, 'id': self._next_trace_id()})
        self._invoke_events('after_iteration')
        return text, 'natural'

    def _completed_text(self, raw) -> str:
        try:
            answer = json.loads(raw)
        except (ValueError, TypeError):
            raise RuntimeError(f'{self.name} returned an invalid result') from None
        text = self._answer_text(answer) if isinstance(answer, dict) else None
        if not text:
            raise RuntimeError(f'{self.name} did not return a completed text answer')
        return text

    def _failure_reply(self, error: str) -> str:
        """A missing login is the owner's to fix, so it is the reply; anything else is a failed turn (#3215)."""
        if self.login_command and 'not logged in' in error.lower():
            return (f'{self.name} is not logged in for this user. '
                    f'Next: run `{self.login_command}` on this computer, then send your message again.')
        raise RuntimeError(f'{self.name} task did not complete: {error or "inspect the provider result"}')

    def _answer_text(self, answer: dict) -> str | None:
        raise NotImplementedError

    def _native_thread(self):
        for event in reversed(self.current_session.get('trace', [])):
            if (event.get('type') == 'provider_invocation' and event.get('provider') == self.provider
                    and event.get('status') in ('completed', 'cancelled', 'failed')
                    and isinstance(event.get('sessionId'), str) and 0 < len(event['sessionId']) <= 512):
                return event['sessionId']
        return ''


def _provider_error(raw) -> str:
    """The `error` line of a provider envelope, or '' when it carries none."""
    try:
        envelope = json.loads(raw)
    except (ValueError, TypeError):
        return ''
    error = envelope.get('error') if isinstance(envelope, dict) else None
    return error if isinstance(error, str) else ''


def _label(provider: str, model: str) -> str:
    """What /info reports as the model: the provider and the model it runs."""
    return f'{provider}/{model}' if model else f'{provider} (native account default)'


class NativeCodexHostAgent(_NativeHostAgent):
    provider = 'codex'
    tool = 'codex'

    def __init__(self, workspace: Path, *, co_dir: Path, model: str = ''):
        super().__init__('Mac Codex', CodexPlugin(workspace=workspace, use_host_permissions=True),
                         co_dir=co_dir, model=model, label=_label('codex', model))

    def _answer_text(self, answer: dict) -> str | None:
        if (answer.get('error') or answer.get('exit_code') not in (None, 0)
                or answer.get('status') == 'cancelled' or not isinstance(answer.get('last_message'), str)):
            return None
        return answer['last_message'].strip() and answer['last_message']


class NativeClaudeHostAgent(_NativeHostAgent):
    provider = 'claude_code'
    tool = 'claude_code'
    login_command = 'claude auth login'

    def __init__(self, workspace: Path, *, co_dir: Path, model: str = '',
                 restriction: ClaudeRestriction | None = None):
        plugin = ClaudeCodePlugin(workspace=workspace, use_host_permissions=True, restriction=restriction)
        super().__init__('Claude Code', plugin, co_dir=co_dir, model=model, label=_label('claude-code', model))
        # What the Control Center lists under Capabilities: these skills are the
        # agent's real capability, and none of them is a published one.
        self.restriction = restriction

    def _answer_text(self, answer: dict) -> str | None:
        if answer.get('error') or answer.get('status') != 'completed' or not isinstance(answer.get('result'), str):
            return None
        return answer['result'].strip() and answer['result']


NATIVE_MODELS = {'codex': NativeCodexHostAgent, 'claude-code': NativeClaudeHostAgent}


def _host_config(co_dir: Path) -> dict:
    path = Path(co_dir) / 'host.yaml'
    config = yaml.safe_load(path.read_text(encoding='utf-8')) if path.is_file() else None
    return config if isinstance(config, dict) else {}


def configured_model(co_dir: Path) -> str:
    """The `model:` line of this Host's host.yaml, or the managed default."""
    path = Path(co_dir) / 'host.yaml'
    model = _host_config(co_dir).get('model')
    if model is None:
        return DEFAULT_MODEL
    if not isinstance(model, str) or not model.strip():
        raise ValueError(f"model in {path} must be a model name, codex or claude-code")
    return model.strip()


def native_provider(model: str) -> tuple[str, str] | None:
    """`claude-code/claude-sonnet-4-5` -> ('claude-code', 'claude-sonnet-4-5'); None for a non-native model."""
    provider, _, native_model = model.partition('/')
    if provider not in NATIVE_MODELS:
        return None
    if '/' in model and not native_model.strip():
        raise ValueError(f"model: {model} names no model after the slash; write {provider} or {provider}/<model>")
    return provider, native_model.strip()


RESTRICTED_KEYS = ('allowed_tools', 'skills', 'system_prompt', 'env')
# A trust level whose callers get more tools: `admin: {allowed_tools: [...]}` (#3340).
LEVEL_KEYS = ('admin', 'whitelist', 'contact')


def configured_restriction(co_dir: Path) -> ClaudeRestriction | None:
    """host.yaml's `restricted:` block, or None when there is none (the unrestricted Host)."""
    block = _host_config(co_dir).get('restricted')
    if block is None:
        return None
    if not isinstance(block, dict) or set(block) - set(RESTRICTED_KEYS) - set(LEVEL_KEYS):
        raise ValueError(f"restricted: in {Path(co_dir) / 'host.yaml'} takes only "
                         f"{', '.join(RESTRICTED_KEYS + LEVEL_KEYS)}")
    return ClaudeRestriction(allowed_tools=_names(block, 'allowed_tools'), skills=_names(block, 'skills'),
                             system_prompt=_text(block, 'system_prompt'), env=_env_names(block),
                             by_level=tuple((level, _level_tools(block, level)) for level in LEVEL_KEYS
                                            if level in block))


def _level_tools(block: dict, level: str) -> tuple[str, ...]:
    """The extra tools one trust level gets; only allowed_tools, so a level cannot change the prompt or env."""
    extra = block[level]
    if not isinstance(extra, dict) or set(extra) != {'allowed_tools'}:
        raise ValueError(f'restricted: {level} takes only allowed_tools, e.g. '
                         f'{level}: {{allowed_tools: ["Bash(python write_contact.py:*)"]}}')
    return _names(extra, 'allowed_tools')


def _env_names(block: dict) -> tuple[str, ...]:
    """Names of the Host's variables its tools need; values stay in the Host's environment, never in host.yaml."""
    names = _names(block, 'env') if isinstance(block.get('env'), list) else None
    if names is None and block.get('env'):
        raise ValueError('restricted: env must be a list of variable names, e.g. env: [FRESHDESK_API_KEY]')
    for name in names or ():
        if not re.fullmatch(r'[A-Z_][A-Z0-9_]*', name) or name.startswith('CO_CALLER_'):
            raise ValueError(f'restricted: env takes UPPER_CASE variable names; {name!r} is not one '
                             '(CO_CALLER_ADDRESS and CO_CALLER_TRUST are set by the Host)')
    return names or ()


def _names(block: dict, key: str) -> tuple[str, ...]:
    value = block.get(key) or []
    if not isinstance(value, list) or not all(isinstance(item, str) and item.strip() for item in value):
        raise ValueError(f'restricted: {key} must be a list of names, e.g. {key}: ["Bash(python tool.py:*)"]')
    return tuple(item.strip() for item in value)


def _text(block: dict, key: str) -> str:
    value = block.get(key) or ''
    if not isinstance(value, str):
        raise ValueError(f'restricted: {key} must be text')
    return value.strip()


def host_agent_factory(project: Path, co_dir: Path, model: str | None = None):
    """The per-conversation agent factory for a Host whose model is one config line."""
    model = model or configured_model(co_dir)
    native = native_provider(model)
    restriction = configured_restriction(co_dir)
    if restriction is not None and (not native or native[0] != 'claude-code' or not native[1]):
        raise ValueError(f'restricted: needs model: claude-code/<model> in host.yaml, not {model}')
    if restriction is not None:
        return lambda: NativeClaudeHostAgent(Path(project), co_dir=Path(co_dir), model=native[1],
                                             restriction=restriction)
    if native:
        provider, native_model = native
        return lambda: NATIVE_MODELS[provider](Path(project), co_dir=Path(co_dir), model=native_model)
    from .agent import create_agent
    return lambda: create_agent(model=model, co_dir=Path(co_dir), role='coding')

"""A claude-code Host that outside callers may use: host.yaml's `restricted:` block.

Without the block, `model: claude-code/<model>` runs a general coding agent with
the Host's own permissions in the workspace. With it, the claude CLI gets only
the tools and skills the operator listed, the project's own settings, no MCP
server, a permission mode that refuses anything not listed, and the verified
caller in its system prompt. A Host that serves an agent.py on a co/ model while
host.yaml names a native model must refuse to start, not route every message
through the co/ model first.
"""
import importlib
import json

import pytest

from connectonion.plugins import coding_agents
claude = importlib.import_module('connectonion.useful_tools.claude_code')

SESSION = '3f2b9c1e-5d4a-4e8b-9a6f-1c2d3e4f5a6b'
RESTRICTED = '''model: claude-code/claude-sonnet-5-5
restricted:
  allowed_tools:
    - "Bash(python tool.py:*)"
  skills: [quote]
  system_prompt: You answer questions about quotes.
'''


def _host_yaml(tmp_path, text):
    co_dir = tmp_path/'.co'
    co_dir.mkdir(exist_ok=True)
    (co_dir/'host.yaml').write_text(text, encoding='utf-8')
    return co_dir


def _capture(monkeypatch):
    calls = []

    def run(**kwargs):
        calls.append(kwargs)
        return json.dumps({'session_id': SESSION, 'status': 'completed', 'result': 'ok'})
    monkeypatch.setattr(coding_agents, 'run_co_claude', run)
    return calls


def test_the_block_reaches_the_claude_cli_with_a_refuse_unlisted_mode(tmp_path, monkeypatch):
    from connectonion.cli.co_ai.native_host import host_agent_factory
    calls = _capture(monkeypatch)
    agent = host_agent_factory(tmp_path, _host_yaml(tmp_path, RESTRICTED))()
    assert agent.input('Quote for 3 rooms?') == 'ok'
    assert calls[0]['permission_mode'] == 'dontAsk'
    assert calls[0]['model'] == 'claude-sonnet-5-5'
    restriction = calls[0]['restriction']
    assert restriction.allowed_tools == ('Bash(python tool.py:*)',)
    assert restriction.skills == ('quote',)
    assert agent.llm.model == 'claude-code/claude-sonnet-5-5'


def test_a_caller_cannot_select_a_wider_permission_in_the_work_room(tmp_path, monkeypatch):
    from connectonion.cli.co_ai.native_host import host_agent_factory
    calls = _capture(monkeypatch)
    agent = host_agent_factory(tmp_path, _host_yaml(tmp_path, RESTRICTED))()
    agent.current_session = {'mode': 'full_access', '_provider_workroom_id': 'w1',
                             '_provider_permission_options': {'w1': 'claude:bypass-permissions'}}
    assert agent.installed_plugins[0]._policy(agent)[0] == 'dontAsk'


def test_no_block_keeps_todays_claude_code_host(tmp_path, monkeypatch):
    from connectonion.cli.co_ai.native_host import host_agent_factory
    calls = _capture(monkeypatch)
    agent = host_agent_factory(tmp_path, _host_yaml(tmp_path, 'model: claude-code/haiku\n'))()
    agent.input('Question')
    assert calls[0]['permission_mode'] != 'dontAsk'
    assert calls[0].get('restriction') is None


@pytest.mark.parametrize('text, message', [
    ('model: codex/gpt-5.5\nrestricted: {}\n', 'claude-code/<model>'),
    ('model: claude-code\nrestricted: {}\n', 'claude-code/<model>'),
    ('model: co/gemini-4-hydrogen\nrestricted: {}\n', 'claude-code/<model>'),
    ('model: claude-code/haiku\nrestricted: {allowed_tools: Bash}\n', 'allowed_tools'),
    ('model: claude-code/haiku\nrestricted: {tools: [Bash]}\n', 'tools'),
])
def test_a_block_that_cannot_be_honoured_stops_the_host(tmp_path, text, message):
    from connectonion.cli.co_ai.native_host import host_agent_factory
    with pytest.raises(ValueError, match=message):
        host_agent_factory(tmp_path, _host_yaml(tmp_path, text))


def test_restricted_argv_loads_only_the_project_and_lists_the_tools(tmp_path):
    restriction = claude.ClaudeRestriction(
        allowed_tools=('Bash(python tool.py:*)',), skills=('quote',), system_prompt='Answer quotes.')
    caller = {'address': '0xabc', 'level': 'contact'}
    argv = claude._stream_command(['claude'], 'hi', '', 'dontAsk', 'claude-sonnet-5-5',
                                  tmp_path/'settings.json', restriction=restriction, caller=caller)
    assert argv[argv.index('--setting-sources') + 1] == 'project'
    assert '--strict-mcp-config' in argv
    assert argv[argv.index('--permission-mode') + 1] == 'dontAsk'
    assert argv[argv.index('--tools') + 1] == 'Bash,Skill'
    allowed = argv[argv.index('--allowedTools') + 1:argv.index('--allowedTools') + 3]
    assert allowed == ['Bash(python tool.py:*)', 'Skill(quote)']
    system = argv[argv.index('--append-system-prompt') + 1]
    assert 'Answer quotes.' in system and '0xabc' in system and 'contact' in system
    assert argv[-2:] == ['--', 'hi']


def test_an_empty_block_gives_claude_no_tools_at_all(tmp_path):
    argv = claude._stream_command(['claude'], 'hi', '', 'dontAsk', 'haiku', tmp_path/'settings.json',
                                  restriction=claude.ClaudeRestriction(), caller=None)
    assert argv[argv.index('--tools') + 1] == ''
    assert '--allowedTools' not in argv


def test_a_restricted_turn_never_asks_the_owner_to_approve_an_edit(tmp_path, monkeypatch):
    handlers = []

    class Bridge:
        def __init__(self, permission_handler=None, tool_rules=None):
            handlers.append((permission_handler, tool_rules))

        def __enter__(self):
            raise RuntimeError('stop after the bridge is configured')

        def __exit__(self, *exc):
            return False
    monkeypatch.setattr(claude, 'scoped_bridge_settings', Bridge)
    agent = type('A', (), {'current_session': {}, 'io': None})()
    with pytest.raises(RuntimeError, match='stop after'):
        claude.run_co_claude('hi', agent=agent, workspace=tmp_path, restriction=claude.ClaudeRestriction())
    assert handlers == [(None, [])]


class _Sample:
    def __init__(self, model):
        self.llm = type('L', (), {'model': model})()


@pytest.mark.parametrize('configured, reported', [
    ('claude-code/claude-sonnet-5-5', 'co/gemini-4-hydrogen'),
    ('codex/gpt-5.5', 'co/gemini-4-hydrogen'),
    ('claude-code', 'gpt-4o'),
])
def test_an_agent_py_on_another_model_under_a_native_host_yaml_refuses_to_start(configured, reported):
    from connectonion.network.host.server import _refuse_silent_outer_model
    with pytest.raises(SystemExit) as stopped:
        _refuse_silent_outer_model(configured, reported)
    assert configured in str(stopped.value) and reported in str(stopped.value)


@pytest.mark.parametrize('configured, reported', [
    ('claude-code/claude-sonnet-5-5', 'claude-code/claude-sonnet-5-5'),
    ('claude-code', 'claude-code (native account default)'),
    ('codex/gpt-5.5', 'codex/gpt-5.5'),
    ('co/gemini-4-hydrogen', 'co/gemini-4-hydrogen'),
    (None, 'co/gemini-4-hydrogen'),
])
def test_an_agent_that_reports_the_configured_provider_starts(configured, reported):
    from connectonion.network.host.server import _refuse_silent_outer_model
    _refuse_silent_outer_model(configured, reported)


def test_host_refuses_an_agent_py_on_co_when_host_yaml_names_claude_code(tmp_path, monkeypatch):
    """The 1Cyber Host: agent.py kept the co/ default under `model: claude-code/<model>`."""
    from connectonion import address
    from connectonion.core.agent import Agent
    from connectonion.network.host import server
    co_dir = _host_yaml(tmp_path, 'name: quotes\nmodel: claude-code/claude-sonnet-5-5\n')
    address.save(address.generate(), co_dir)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr('connectonion.cli.commands.agent_index.refresh', lambda: [])
    served = []
    monkeypatch.setattr(server.uvicorn, 'run', lambda app, **options: served.append(app))
    agent = Agent('quotes', model='co/gemini-4-hydrogen', api_key='fixture-key', log=False)
    with pytest.raises(SystemExit, match='co/gemini-4-hydrogen before claude-code'):
        server.host(agent, port=18767, co_dir=co_dir, relay_url=None, listen=[], trust='strict')
    assert served == []


def test_info_names_a_managed_model_with_its_co_prefix(monkeypatch):
    """/info said gemini-4-hydrogen for co/gemini-4-hydrogen; host.yaml and /info write provider/model."""
    from connectonion.core.agent import Agent
    from connectonion.network.host import server
    agent = Agent('quotes', model='co/gemini-4-hydrogen', api_key='fixture-key', log=False)
    monkeypatch.setattr(type(agent.llm), 'get_balance', lambda self: None)
    metadata, _ = server._extract_agent_metadata(lambda: agent)
    assert metadata['model'] == 'co/gemini-4-hydrogen'


# ---- The PreToolUse guard: `--allowedTools` alone let `cat .env` run ----
# Measured on claude 2.1.326: under dontAsk with only Bash(python3 tool.py:*)
# allowed, a caller's "run cat .env" printed the key, because the claude CLI
# runs read-only commands without asking. The guard Hook refuses anything a
# listed rule does not name, before the CLI's own permission check.

RULES = ['Bash(python3 tool.py:*)', 'Skill(quote)']


@pytest.mark.parametrize('tool, tool_input', [
    ('Bash', {'command': 'python3 tool.py 3'}),
    ('Bash', {'command': 'python3 tool.py'}),
    ('Bash', {'command': 'python3 tool.py "3 rooms"'}),
    ('Skill', {'skill': 'quote'}),
])
def test_the_guard_allows_what_a_rule_names(tool, tool_input):
    bridge = importlib.import_module('connectonion.useful_tools.claude_code_bridge')
    assert bridge.tool_use_allowed(tool, tool_input, RULES)


@pytest.mark.parametrize('tool, tool_input', [
    ('Bash', {'command': 'cat .env'}),
    ('Bash', {'command': 'python3 tool.py 2; cat .env'}),
    ('Bash', {'command': 'python3 tool.py 2 && cat .env'}),
    ('Bash', {'command': 'python3 tool.py $(cat .env)'}),
    ('Bash', {'command': 'python3 tool.py `cat .env`'}),
    ('Bash', {'command': 'python3 tool.py 2 > out.txt'}),
    ('Bash', {'command': 'python3 tool.py 2\ncat .env'}),
    ('Bash', {'command': 'python3 tool.pyx'}),
    ('Read', {'file_path': '.env'}),
    ('Skill', {'skill': 'other'}),
    ('Skill', {}),
])
def test_the_guard_refuses_anything_else(tool, tool_input):
    bridge = importlib.import_module('connectonion.useful_tools.claude_code_bridge')
    assert not bridge.tool_use_allowed(tool, tool_input, RULES)


def _run_guard(tmp_path, event):
    import subprocess
    import sys
    bridge = importlib.import_module('connectonion.useful_tools.claude_code_bridge')
    rules = tmp_path/'rules.json'
    rules.write_text(json.dumps(RULES), encoding='utf-8')
    return subprocess.run([sys.executable, bridge.__file__, '--guard', str(rules)],
                          input=event, capture_output=True, text=True)


def test_the_guard_hook_blocks_with_exit_2_and_allows_with_0(tmp_path):
    refused = _run_guard(tmp_path, json.dumps({'tool_name': 'Bash', 'tool_input': {'command': 'cat .env'}}))
    assert refused.returncode == 2 and 'restricted' in refused.stderr
    allowed = _run_guard(tmp_path, json.dumps({'tool_name': 'Bash', 'tool_input': {'command': 'python3 tool.py 1'}}))
    assert allowed.returncode == 0


def test_a_guard_that_cannot_read_its_input_blocks(tmp_path):
    """A crashing Hook exits 1, which the claude CLI treats as non-blocking: the guard must exit 2."""
    assert _run_guard(tmp_path, 'not json').returncode == 2


def test_a_restricted_turn_installs_the_guard_hook():
    bridge = importlib.import_module('connectonion.useful_tools.claude_code_bridge')
    with bridge.scoped_bridge_settings(tool_rules=RULES) as (settings, _):
        hooks = json.loads(settings.read_text(encoding='utf-8'))['hooks']['PreToolUse'][0]['hooks']
        guard = [hook for hook in hooks if '--guard' in hook['args']]
        assert len(guard) == 1
        assert json.loads(open(guard[0]['args'][-1], encoding='utf-8').read()) == RULES
    with bridge.scoped_bridge_settings() as (settings, _):
        hooks = json.loads(settings.read_text(encoding='utf-8'))['hooks']['PreToolUse'][0]['hooks']
        assert not any('--guard' in hook['args'] for hook in hooks)


def test_env_names_reach_the_claude_cli_and_nothing_else_does(tmp_path, monkeypatch):
    """1Cyber's fd.py needs FRESHDESK_API_KEY; the child environment is an
    allowlist, so a restricted Host names what its tools need in host.yaml."""
    from connectonion.cli.co_ai.native_host import configured_restriction
    monkeypatch.setenv('FRESHDESK_API_KEY', 'fd-synthetic')
    monkeypatch.setenv('UNLISTED_SECRET', 'nope')
    co_dir = _host_yaml(tmp_path, RESTRICTED + '  env: [FRESHDESK_API_KEY, NOT_SET_HERE]\n')
    restriction = configured_restriction(co_dir)
    environment = restriction.environment({'address': '0xabc', 'level': 'contact'})
    assert environment == {'FRESHDESK_API_KEY': 'fd-synthetic',
                           'CO_CALLER_ADDRESS': '0xabc', 'CO_CALLER_TRUST': 'contact'}
    assert claude.ClaudeRestriction().environment(None) == {}


def test_a_restricted_turn_starts_claude_with_the_named_env(tmp_path, monkeypatch):
    monkeypatch.setenv('FRESHDESK_API_KEY', 'fd-synthetic')
    monkeypatch.setenv('UNLISTED_SECRET', 'nope')
    seen = {}

    class Started(Exception):
        pass

    def popen(argv, **kwargs):
        seen.update(kwargs['env'])
        raise Started
    monkeypatch.setattr(claude.subprocess, 'Popen', popen)
    restriction = claude.ClaudeRestriction(env=('FRESHDESK_API_KEY',))
    with pytest.raises(Started):
        claude._start_process(['claude'], str(tmp_path), restriction.environment({'address': '0xabc', 'level': 'contact'}))
    assert seen['FRESHDESK_API_KEY'] == 'fd-synthetic' and seen['CO_CALLER_ADDRESS'] == '0xabc'
    assert 'UNLISTED_SECRET' not in seen


@pytest.mark.parametrize('line', ['  env: FRESHDESK_API_KEY\n', '  env: ["lower-case"]\n', '  env: [CO_CALLER_ADDRESS]\n'])
def test_a_bad_env_list_stops_the_host(tmp_path, line):
    from connectonion.cli.co_ai.native_host import configured_restriction
    with pytest.raises(ValueError, match='restricted: env'):
        configured_restriction(_host_yaml(tmp_path, RESTRICTED + line))

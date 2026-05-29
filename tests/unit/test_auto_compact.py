"""Unit tests for connectonion/useful_plugins/auto_compact.py"""

from unittest.mock import Mock, patch

import pytest

# useful_plugins/__init__.py does `from .auto_compact import auto_compact`
# which rebinds the package attribute `connectonion.useful_plugins.auto_compact`
# from the *module* to the plugin-export *list* of the same name. That breaks
# both `mock.patch('connectonion.useful_plugins.auto_compact.X')` and
# `import connectonion.useful_plugins.auto_compact as foo`. Grab the actual
# module from sys.modules to get past the shadow.
import sys
import connectonion.useful_plugins.auto_compact  # noqa: F401 — ensures module load
import connectonion.llm_do  # noqa: F401 — same reason
ac_module = sys.modules['connectonion.useful_plugins.auto_compact']
llm_do_module = sys.modules['connectonion.llm_do']

COMPACT_THRESHOLD = ac_module.COMPACT_THRESHOLD
_do_compact = ac_module._do_compact
_format_messages_for_summary = ac_module._format_messages_for_summary
check_and_compact = ac_module.check_and_compact


class FakeAgent:
    def __init__(self, context_percent=0, messages=None, io=None):
        self.context_percent = context_percent
        self.current_session = {'messages': list(messages) if messages else []}
        self.io = io
        self.logger = Mock()
        self.logger.console = None  # silence prints


def _msgs(n, role='user'):
    return [{'role': role, 'content': f'msg {i}'} for i in range(n)]


# ---------- check_and_compact no-op gates ----------

def test_check_noop_when_context_below_threshold():
    agent = FakeAgent(context_percent=COMPACT_THRESHOLD - 1, messages=_msgs(20))
    with patch.object(ac_module, '_do_compact') as mock_compact:
        check_and_compact(agent)
        mock_compact.assert_not_called()


def test_check_noop_when_messages_too_few():
    agent = FakeAgent(context_percent=99, messages=_msgs(7))  # 7 < 8 threshold
    with patch.object(ac_module, '_do_compact') as mock_compact:
        check_and_compact(agent)
        mock_compact.assert_not_called()


def test_check_triggers_when_both_thresholds_met():
    agent = FakeAgent(context_percent=95, messages=_msgs(10))
    with patch.object(ac_module, '_do_compact', return_value="10 → 7 messages") as mock_compact:
        check_and_compact(agent)
        mock_compact.assert_called_once_with(agent)


def test_check_at_exact_threshold_triggers():
    """`context_percent < COMPACT_THRESHOLD` → at exactly 90% it should fire."""
    agent = FakeAgent(context_percent=COMPACT_THRESHOLD, messages=_msgs(10))
    with patch.object(ac_module, '_do_compact', return_value="ok") as mock_compact:
        check_and_compact(agent)
        mock_compact.assert_called_once()


def test_check_sends_compact_event_when_io_present():
    io = Mock()
    agent = FakeAgent(context_percent=95, messages=_msgs(10), io=io)
    with patch.object(ac_module, '_do_compact', return_value="10 → 7 messages"):
        check_and_compact(agent)
    # Two events: 'compacting' + 'done'
    sent_types = [c.args[0]['status'] for c in io.send.call_args_list]
    assert sent_types == ['compacting', 'done']


def test_check_sends_error_event_when_compact_fails():
    io = Mock()
    agent = FakeAgent(context_percent=95, messages=_msgs(10), io=io)
    with patch.object(ac_module, '_do_compact', side_effect=RuntimeError("llm down")):
        check_and_compact(agent)  # must NOT raise
    statuses = [c.args[0]['status'] for c in io.send.call_args_list]
    assert 'error' in statuses
    err_event = [c.args[0] for c in io.send.call_args_list if c.args[0]['status'] == 'error'][0]
    assert err_event['error'] == 'llm down'


# ---------- _do_compact behavior ----------

def test_do_compact_returns_nothing_to_compact_when_old_msgs_below_three():
    """If after taking system + last 5, fewer than 3 old messages remain → no-op."""
    # 7 messages = system + 1 old + 5 recent → old=1 < 3 → "Nothing to compact"
    messages = (
        [{'role': 'system', 'content': 'sys'}]
        + _msgs(1, role='user')
        + _msgs(5, role='assistant')
    )
    agent = FakeAgent(messages=messages)
    with patch.object(llm_do_module, 'llm_do') as mock_llm:
        result = _do_compact(agent)
    assert result == "Nothing to compact"
    mock_llm.assert_not_called()


def test_do_compact_replaces_old_messages_with_summary_keeping_system_and_recent():
    messages = (
        [{'role': 'system', 'content': 'sys'}]
        + _msgs(10, role='user')
    )
    agent = FakeAgent(messages=messages)
    with patch.object(llm_do_module, 'llm_do', return_value="SUMMARY_TEXT"):
        result = _do_compact(agent)

    new = agent.current_session['messages']
    assert new[0] == {'role': 'system', 'content': 'sys'}  # system preserved
    assert new[1]['role'] == 'user'
    assert "SUMMARY_TEXT" in new[1]['content']            # summary inserted
    assert new[-5:] == messages[-5:]                      # last 5 preserved
    assert len(new) == 1 + 1 + 5                          # system + summary + recent
    assert result == "11 → 7 messages"


def test_do_compact_works_without_system_message():
    """If no system message, the first old message gets compacted too."""
    messages = _msgs(10, role='user')
    agent = FakeAgent(messages=messages)
    with patch.object(
        llm_do_module, 'llm_do',
        return_value="S",
    ):
        result = _do_compact(agent)

    new = agent.current_session['messages']
    assert new[0]['role'] == 'user'  # summary message (no system to preserve)
    assert "S" in new[0]['content']
    assert new[-5:] == messages[-5:]
    assert result == "10 → 6 messages"


# ---------- _format_messages_for_summary ----------

def test_format_user_message_plain():
    out = _format_messages_for_summary([{'role': 'user', 'content': 'hello world'}])
    assert out == "[user] hello world"


def test_format_assistant_with_tool_calls_lists_tool_names():
    msg = {
        'role': 'assistant',
        'content': '',
        'tool_calls': [
            {'function': {'name': 'read_file'}},
            {'function': {'name': 'grep'}},
        ],
    }
    out = _format_messages_for_summary([msg])
    assert "Called tools: read_file, grep" in out


def test_format_tool_role_truncates_long_results():
    long_result = 'x' * 500
    msg = {'role': 'tool', 'name': 'cat', 'content': long_result}
    out = _format_messages_for_summary([msg])
    assert out.startswith("[tool:cat]")
    # Truncated at 200 + "..."
    assert "..." in out
    payload = out[len("[tool:cat] "):]
    assert len(payload) < len(long_result)


def test_format_short_tool_result_not_truncated():
    msg = {'role': 'tool', 'name': 'cat', 'content': 'short'}
    out = _format_messages_for_summary([msg])
    assert out == "[tool:cat] short"


def test_format_system_truncates_at_300_chars():
    msg = {'role': 'system', 'content': 'x' * 500}
    out = _format_messages_for_summary([msg])
    assert out.endswith("...")
    payload = out[len("[system] "):-3]
    assert len(payload) == 300


def test_format_joins_messages_with_double_newline():
    msgs = [
        {'role': 'user', 'content': 'a'},
        {'role': 'assistant', 'content': 'b'},
    ]
    out = _format_messages_for_summary(msgs)
    assert "\n\n" in out
    assert out == "[user] a\n\n[assistant] b"

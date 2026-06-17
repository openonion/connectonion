"""
LLM-Note: No-progress guard plugin.

Purpose: Stop the agent loop early when it makes the exact same tool call(s)
several iterations in a row — a stuck loop doing the same thing (the classic
browser-agent failure: screenshot -> same dead click -> screenshot -> ...).
max_iterations is the slow-drift backstop; this catches tight loops before they
burn the budget and pile screenshots into the context.

Data flow: after_iteration -> read the most recent assistant tool_calls ->
build a signature (tool names + arguments, call ids stripped) -> compare to the
previous iteration's signature stored in current_session -> if identical for
`max_repeats` consecutive iterations, set stop_signal so the loop halts and asks
the user what to do next.

State/Effects: reads/writes current_session['_noprogress_sig'] and
['_noprogress_count']; sets current_session['stop_signal'] when stuck. Touches
nothing else.

Note: the signature compares the whole set of tool calls in an iteration, so a
loop that varies any argument (e.g. a different selector each try) is treated as
progress and not stopped — max_iterations covers that drift. This guard targets
byte-identical repetition only, which keeps false positives near zero.
"""

import json
from ..core.events import after_iteration


def _last_tool_signature(messages):
    """Signature of the most recent assistant tool_calls, call ids stripped."""
    for message in reversed(messages):
        if message.get('role') == 'assistant' and message.get('tool_calls'):
            return json.dumps(
                [
                    [tc['function']['name'], tc['function'].get('arguments', '')]
                    for tc in message['tool_calls']
                ],
                sort_keys=True,
            )
    return None


def no_progress_guard(max_repeats: int = 3):
    """Plugin: halt the loop when the same tool call(s) repeat `max_repeats` times
    in a row.

    Args:
        max_repeats: consecutive identical iterations that trigger the stop
            (default 3 — the third identical call halts).
    """

    def _check(agent):
        session = agent.current_session
        signature = _last_tool_signature(session['messages'])
        if signature is None:
            return

        if signature == session.get('_noprogress_sig'):
            session['_noprogress_count'] = session.get('_noprogress_count', 1) + 1
        else:
            session['_noprogress_sig'] = signature
            session['_noprogress_count'] = 1

        if session['_noprogress_count'] >= max_repeats:
            agent.logger.print(
                f"[yellow]No-progress guard: same tool call repeated "
                f"{max_repeats}x — stopping the loop.[/yellow]"
            )
            session['stop_signal'] = True

    return [after_iteration(_check)]

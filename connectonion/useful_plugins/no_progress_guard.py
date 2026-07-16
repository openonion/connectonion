"""
LLM-Note: No-progress guard plugin.

Purpose: Stop the agent loop early when it emits the EXACT SAME tool call(s) in
consecutive iterations — an agent hammering one identical call that gets it nowhere
(e.g. retrying the same failing action with the same arguments, or an LLM stuck
re-issuing a call it already made). max_iterations is the slow-drift backstop; this
catches a tight byte-identical loop before it burns the budget.

Scope: compares the WHOLE tool-call set of one iteration to the previous iteration's,
and fires only on CONSECUTIVE byte-identical repetition. It deliberately does NOT
catch a loop that alternates or cycles (e.g. screenshot -> click -> screenshot ->
click, whose signature changes every step) or one that varies any argument — those
are left to max_iterations. Detecting cycles would risk stopping legitimate periodic
work (scroll -> screenshot -> scroll ...), so this stays narrow on purpose.

Data flow: after_user_input -> clear the per-turn counter | after_iteration -> read
the most recent assistant tool_calls -> build a signature (tool names + arguments,
call ids stripped) -> compare to the previous iteration's signature stored in
current_session -> if identical for `max_repeats` consecutive iterations, set
stop_signal so the loop halts and asks the user what to do next.

State/Effects: reads/writes current_session['_noprogress_sig'] and
['_noprogress_count'], cleared at each turn boundary so a streak never crosses turns;
sets current_session['stop_signal'] when stuck. Touches nothing else.

Caveat: a tool that is legitimately called identically several times in a row (a
fixed-interval poll, a same-args retry, paginating with an unchanged cursor) trips this
at `max_repeats`. It is opt-in for exactly that reason — enable it only for agents where
consecutive identical calls mean "stuck".
"""

import json
from ..core.events import after_user_input, after_iteration


def _last_tool_signature(messages):
    """Signature of the most recent assistant tool_calls, call ids stripped.

    `arguments` is compared as its raw serialized string, so detection relies on the
    tool-call producer serializing it deterministically (it does — json.dumps in
    tool_executor), which makes a repeated identical call serialize byte-for-byte.
    """
    for message in reversed(messages):
        if message.get('role') != 'assistant':
            continue
        tool_calls = message.get('tool_calls')
        if not tool_calls:
            return None
        return json.dumps(
            [
                [tc['function']['name'], tc['function'].get('arguments', '')]
                for tc in tool_calls
            ]
        )
    return None


def no_progress_guard(max_repeats: int = 3):
    """Plugin: halt the loop when the same tool call(s) repeat `max_repeats` times in a
    row within one turn.

    Args:
        max_repeats: consecutive identical iterations that trigger the stop
            (default 3 — the third identical call halts).
    """

    def _reset(agent):
        # The streak is per-turn: clear it when a new user message arrives, so a halt
        # can be continued (the next turn's first identical call doesn't immediately
        # re-halt) and identical calls across unrelated turns don't accumulate.
        agent.current_session.pop('_noprogress_sig', None)
        agent.current_session.pop('_noprogress_count', None)

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

    # List order is just a bundle — the agent registers each handler by its event type,
    # so _check stays first for callers/tests that index [0].
    return [after_iteration(_check), after_user_input(_reset)]

"""
Purpose: Select canonical per-turn slices from the cumulative Agent trace
LLM-Note:
  Dependencies: none | imported by [logger.py, useful_plugins/eval.py] | tested by [tests/unit/test_logger.py, tests/unit/test_eval_plugin.py]
  Data flow: cumulative trace + current turn number -> trace beginning at that turn's user_input marker
  State/Effects: pure; never mutates the trace
  Errors: legacy or hand-built traces without a matching marker remain unchanged
"""


def current_turn_trace(trace: list[dict], turn: object) -> list[dict]:
    """Return the canonical trace slice for one Agent turn.

    Agent sessions retain earlier turns.  The latest matching ``user_input``
    marker is the source-of-truth boundary; legacy traces without that marker
    stay usable by falling back to the complete trace.
    """
    for index in range(len(trace) - 1, -1, -1):
        entry = trace[index]
        if entry.get("type") == "user_input" and entry.get("turn") == turn:
            return trace[index:]
    return trace

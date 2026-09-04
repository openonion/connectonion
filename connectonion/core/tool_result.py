"""Typed return values that carry tool execution outcome semantics."""


class ToolFailure(str):
    """A string-compatible, expected tool failure.

    Tools use this for user-correctable refusals and validation failures that
    should reach the model as ordinary text while still being recorded and
    displayed as a failed execution. Ordinary strings, including strings that
    happen to start with ``"Error:"``, keep their existing success semantics.
    """

    __slots__ = ()

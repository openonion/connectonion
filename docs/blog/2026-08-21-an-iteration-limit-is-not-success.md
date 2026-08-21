# An iteration limit is not success

Automation needs a truthful process outcome. Until now, `co ai "..."` could
reach `--max-iterations`, print that the task was incomplete, and still exit
with status zero. A person could read the warning; a shell pipeline could not
distinguish it from completed work.

ConnectOnion 1.7 preserves the partial result but reports the boundary
honestly. Human-readable one-shot runs exit nonzero after printing the result.
JSON mode adds one stable `outcome` field:

```json
{"session_id":"...","result":"...","outcome":"max_iterations","error":null}
```

The other values are `natural` for a completed turn and `error` for execution
failure. Resumable state is committed before an incomplete run exits, so an
orchestrator can decide whether to resume without losing evidence.

This change deliberately does not add a cost-budget system. Cost ceilings and
in-context budget guidance require a separate product contract and remain a
1.8 concern; the bounded 1.7 fix is simply that incomplete work is never
reported as process success.

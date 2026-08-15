# When logging looked like authoring

The failure was easy to miss because nothing crashed. An agent tried to append a JSONL record with `>>`, then tried `tee`, then tried another shell spelling. The write policy rejected every spelling, the step kept retrying, and the pipeline eventually exited successfully with an empty ledger.

The rule had been written for a useful distinction: model-authored source should go through the Write or Edit tools so a reviewer can see a diff. But append-only state and command output are different operations. Replacing an entire ledger is not equivalent to appending one row, especially when two workers may write at the same time. Likewise, redirecting a subprocess's stdout is logging, not the model authoring a file.

The fix narrows the block to the dangerous case: `echo` and `printf` with a single overwrite redirect, plus heredocs. Append redirects, `tee`, and ordinary command-output redirects are now allowed. The regression tests make the boundary explicit, including `>>` next to the existing `2>` stderr exemption.

The practical lesson is that a safety rule needs to distinguish the effect it is protecting against, not just the shell punctuation used to spell it. A blocked operation without a viable alternative is not a guardrail; it is a retry loop with a bill attached.

# A review that finished but never arrived

A REM preview was ready for review. The model read the pull request and finished its turn, yet the review workflow stopped before posting anything. The only visible result was “invalid JSON result envelope.” From the PR, this looked much like a failed review, although no reviewer had actually reached a judgment.

The adapter still expected the old three-field `co ai` response. The current one-shot command reports five fields: session ID, result, outcome, error, and usage. Rejecting extra fields was deliberate: a publishing workflow should never guess at a protocol. But the adapter and producer had drifted apart, so every successful current response was rejected.

The adapter now validates the current envelope exactly and accepts a review only when its outcome is natural. A stopped iteration or provider error remains a failure. Thirty targeted tests pass, including a successful current envelope and those failure cases. The next proof is operational: the trusted workflow must post the completed review to the REM PR before that preview is released.

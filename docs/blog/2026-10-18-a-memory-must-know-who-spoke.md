# A memory must know who spoke

“Reply READY only” can be a perfectly valid instruction to a model. It becomes a bad memory when the notebook later treats it as something its owner wanted to remember.

REM runs investigations in its notebook's `.state/tasks` directory. Those model conversations can live beside ordinary coding conversations in the same session store. Both can say `originator: connectonion`: one belongs to REM's machinery, the other may contain a real person's request. Excluding the entire originator would discard useful user context. Looking only for particular prompt phrases would leave the next repair instruction exposed.

The existing boundary used the working directory. That was the right distinction, but its path parser assumed POSIX spelling. In a synthetic Windows rollout, a backslash-separated task directory was a single POSIX path component. The collector admitted the internal prompt. Invocation counting and evidence sampling had their own slash-only checks, so cached internal tasks could also look like the owner's skill use.

The failure was observable without asking a model or opening a private session: ten invented Codex and Claude collector cases admitted internal instructions; another test counted two internal invocations. The fix reads drive and UNC paths with Windows semantics and shares that task-directory decision with counts and samples. Windows casing and mixed separators work; POSIX case remains significant. Similar directory names and ordinary Windows user sessions stay available. Cached entries are filtered at consumption, avoiding a forced rescan.

The focused suites now pass 56 tests. This is source-level evidence on macOS, with Windows-shaped paths, rather than a native Windows onboarding trial. It does not prove the quality of generated pages. Nor does it quietly remove old memories: any earlier imported prompt and claims based on it need a separate review.

For a memory product, identifying the speaker starts before summarization. A convincing sentence with a citation can still be wrong if the cited speaker was the notebook talking to itself. The fix has merged after review and CI. Candidate 1.9.3rc7 carries it; availability depends on the immutable-tag release workflow completing. The candidate does not claim a mature memory product.

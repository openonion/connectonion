# 077. Concurrent Onboarding Investigation and Full-Cohort Synthesis

- **Status**: Accepted
- **Date**: 2026-10-03
- **Context**: ConnectOnion Agent Long-Term Memory (`co rem`)

## Context

Prior versions of `co rem init` and `co rem investigate` operated with artificial sample caps designed for test dry-runs (e.g. `--first-people 3`, `--first-projects 2`, `--first-orgs 1`, and a 5-page default cap on `co rem investigate <category>`). In live user onboarding, this left over 90% of mapped entities as empty stubs (`Unknown — not investigated yet`).

Furthermore, pages were processed serially in a single-threaded loop. For notebooks with 50+ mapped entities, serial investigation would take multiple hours, creating an unacceptable onboarding UX.

## Decision

1. **Full Cohort Default for Onboarding & Investigation**:
   - `co rem init` investigates all eligible mapped people, all mapped projects with project evidence, and all mapped organizations by default.
   - `co rem investigate` processes all pending pages in the requested category by default without a 5-page cap.
   - `--first-*` and `--limit` options remain available for opt-in small-sample dry runs during testing.

2. **10-Worker Concurrent Investigation Pool**:
   - Both `co rem investigate` and batch onboarding dispatch tasks through `concurrent.futures.ThreadPoolExecutor(max_workers=10)` (configurable via `--workers` / `-w`).
   - Results stream back with live progress reporting (`[done/total] record: accepted/refused`).
   - 50+ entities complete in ~15–25 minutes, staying comfortably under the 30-minute operational budget.

3. **Thread-Safe Mail Client Isolation**:
   - High-concurrency worker threads must not share non-thread-safe HTTP socket buffers or SDK client singletons.
   - `Gmail` encapsulates its API resource in `self._local = threading.local()`, preventing SSL read buffer corruption in C-extensions.

4. **Private Runner Task Masks**:
   - Parallel runner tasks maintain thread-isolated permissions and temporary cleanup grace periods via `private_task_mask()` to prevent race conditions during artifact review and promotion.

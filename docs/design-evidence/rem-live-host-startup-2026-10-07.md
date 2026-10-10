# Live REM starts its Host — issue #2307

## Reported experience

The owner ran `co rem open --live`; the command opened a static snapshot and instructed them to run `co ai` separately. The owner explicitly requested automatic startup.

## Change

The default notebook's explicit live open now reuses an online Host or starts the existing `co ai` in a detached process. It forwards an explicitly selected environment, disables channel listeners and the extra chat tab, and waits up to 20 seconds after the startup lock for readiness. Default/local snapshot opens and custom-root opens keep their existing behavior. `--no-launch` prints the resulting URL without opening a browser.

Startup is serialized using the existing owner lock. Operational state stores the identity, PID and command; current-user command verification prevents PID reuse from blocking later opens. Early exit, timeout, invalid state or launch errors produce a labelled snapshot fallback and a nonzero CLI exit. Invalid state is preserved. A new child is terminated and reaped if readiness or state persistence fails. The local startup log lives in the selected identity directory as `rem-live-host.log`.

## Independent review

A separate AI reviewer inspected startup/reuse/failure states, identity forwarding, listener effects and browser effects. It identified stale-PID reuse and corrupt-state fallback issues; both were fixed with regressions. Its final recheck found no major blocker. The additional state-write cleanup concern was also addressed.

## Verification and limits

Isolated regression coverage includes online reuse, an already-starting managed process, successful startup, early exit, timeout, PID reuse, corrupt state, selected environment forwarding, state-write failure and suppressed browser launch. Existing REM CLI and co ai tests are included in the verification command:

```sh
python -m pytest tests/unit/test_rem_live_host.py tests/unit/test_co_ai_agent_main.py tests/unit/test_cli_commands_ai_trust.py tests/e2e/cli/test_rem_commands.py -q
```

No real-data init, model calls, mailbox scans or live Host trial were run on this computer. There is no rendered-page change and no new screenshot evidence. This is a lifecycle fix, not evidence of overall REM product maturity. The process check targets macOS/Linux, consistent with REM's current filesystem locking.

## CI follow-up — 8 October (Sydney)

The initial full CI failed two existing CLI forwarding assertions on all four Python versions: the expected kwargs omitted the new default `launch=True`. The expectations now include that default, and a CLI regression checks that a managed background invocation forwards `launch=False` and `listen=[]`. No provider or real notebook was contacted. Fresh CI is required; this follow-up is not release approval.

## Main-branch integration — 9 October (Sydney)

The corrected PR passed its full CI matrix, then main advanced and added `MAP_DAYS` to the reader imports. The integration conflict keeps both `MAP_DAYS` and this fix's `RemError` import. All other changed files merged automatically onto main commit `229d4382d358338924d9d35bc6bcbd58b5217626`. This merge requires fresh CI before approval or publication; no real notebook or model trial was run.

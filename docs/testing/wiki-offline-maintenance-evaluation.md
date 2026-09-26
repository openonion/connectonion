# Offline Wiki maintenance evaluation (2026-09-26)

The 2026-09-25 unattended maintenance run returned a natural model response but
changed no page. The response said local files could not be read because the
task prompt prohibited shell commands. The service recorded the batch as
completed. This evaluation tests that failure at the actual Wiki runner
boundary; `co benchmark` exercises a normal agent and would not compose this
runner's task files, sandbox flags and page promotion path.

Run the frozen five-case fixture with:

```sh
python -m pytest tests/unit/test_wiki_runner.py::test_offline_maintenance_benchmark -q
```

| Case | Expected classification | Result |
|---|---|---|
| Natural reply, no edits, no review receipt | Failed; source progress remains pending | Passed |
| No-change receipt names the wrong source | Failed | Passed |
| Receipt says the task was blocked | Failed | Passed |
| Source read, explicit reviewed no-change receipt | Completed without page edits | Passed |
| Source read and page updated in disposable copy | Completed with promoted page | Passed |

The fixture uses only synthetic source IDs and text. It checks the composed
prompt and files passed through `run_stage`; the simulated model process does
not evaluate summary quality.

One separate live Codex Luna smoke run used a synthetic one-off arithmetic
request and a synthetic existing note. Luna read the task files and wrote a
valid `completion.json` recording that no durable information warranted a
page. The runner returned success with no changed pages in 23.3 seconds. Its
reported usage was 144,414 input tokens (120,576 cached) and 566 output tokens.
The 44,978-character instruction bundle dominates this tiny task; reducing
that cost is future work and the smoke run is not a quality benchmark for
substantial Wiki summaries. No personal notebook or live mail was sent for
this smoke run.

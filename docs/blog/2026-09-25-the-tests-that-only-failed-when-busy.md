# The tests that only failed when the machine was busy

Two browser tests kept going red in full parallel runs and green when rerun
alone. Nobody could make them fail on purpose, so each red run was waved
through as "flaky", which is what people say when they have stopped looking.

This time we made the machine busy on purpose: the whole suite under
`pytest -n auto`, with one `yes > /dev/null` per core running alongside it.
Everything that had failed now and then started failing reliably, and the
reasons were not the same.

The first was a limit in the kernel, not in the timing. The test sends forty
stuck commands to the browser daemon to prove that `status` and `close` still
get an answer. The daemon listens with a backlog of 32. On Linux, a connect
to a full backlog waits. On macOS it is refused on the spot. On an idle
machine the daemon accepts connections faster than the test opens them, so
the backlog never fills. On a busy machine the daemon's loop falls behind,
the 33rd connect is refused, and the test fails before it has checked
anything. The real client already retries a refused connect for about two
seconds for exactly this reason. The test's stand-in for a stuck client did
not. It retries now, and the test pauses the daemon's loop while the forty
arrive, so the backlog overflows on every run instead of on unlucky ones.
It used to fail about one run in ten under load. Before the retry, it now
fails every time; with the retry, it passes every time.

The second was a budget. The real-Chromium acceptance test takes about 36
seconds on an idle Mac, mostly the product's own pauses: a second after each
humanized click, and the scroll fallback. The suite gives every test 60
seconds. Beside other Chromium tests on a busy machine it took 60 to 90, and
pytest-timeout killed it partway through and then reported the waiter thread
it had left behind. The 128 MiB sealed-dashboard test had the same problem
for a different reason: sealing and opening that much data is pure CPU. Both
now declare their real budget with `@pytest.mark.timeout`, which is what the
suite's rules say to do. The short deadlines inside them, the ones that
prove tab B keeps working while tab A is busy, did not change. Even ten of
these tests run side by side under load still passed those checks.

While looking we found a third problem: shared state nobody had asked for.
The suite runs from the repository root, so any Agent that logs by default
wrote into the checkout's own `.co/`. A full run left `evals/hi.yaml`,
`admins.txt`, `contacts.txt`, a replay database and a session log behind.
About ninety tests in seventeen files did it, and every xdist worker wrote
to the same directory at once. That is the kind of state behind #1653's
flake. `tests/conftest.py` now installs an audit hook that sees every write
in the process, whoever makes it. A test that writes under the repository's
`.co/` fails, and the failure names the paths. Because the hook runs per
process, it blames the test that did the writing and not the one that
happened to run next to it. Those seventeen files now run from a tmp
project through a shared `own_project` fixture.

The lesson is to stop calling it flaky and make the busy machine happen on
purpose. A test that fails one run in ten is telling you what it depends on,
and here that was a kernel limit, a wall clock and a shared directory.

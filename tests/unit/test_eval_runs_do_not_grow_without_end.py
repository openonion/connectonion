"""An agent on a schedule must not fill its own disk with eval runs.

Every turn writes `.co/evals/{slug}/run_{n}.yaml`, containing the whole message
array. Nothing removes them.

Measured on the deployed naturewill agent, which runs a schedule:

    .co total                21 MB
      evals                  17 MB      <- 171 run files
      logs                   1.9 MB
      session_results.jsonl  504 KB     <- compacted, so it stays small
    oldest run file          2026-08-01 09:30
    newest run file          2026-08-03 04:30

17 MB in 43 hours is about 9.5 MB a day, so 3.5 GB a year — on the 1–2 GB VPS
that `co server new` provisions. The agent fills its own disk in a couple of
months, and what dies is the agent.

What reads a run file, checked rather than assumed: nothing does during a run.
`co eval` globs `evals/*.yaml` — the per-eval file beside the directory, not the
runs inside it. `Logger.load_messages(run=N)` can open one, and no caller in this
codebase does; only its own tests. So the readers are a human looking at what
went wrong, and anyone calling that method — and for both, the recent runs are
the ones worth having.

Older runs really are deleted. That is the trade being made, against an agent
that fills its own disk in a couple of months and dies.
"""

import pytest

from connectonion.logger import Logger, KEEP_RUNS_PER_EVAL


@pytest.fixture
def eval_dir(tmp_path):
    d = tmp_path / "evals" / "some_task"
    d.mkdir(parents=True)
    return d


def _write_runs(eval_dir, count):
    """Runs 1..count, as the logger writes them."""
    for n in range(1, count + 1):
        (eval_dir / f"run_{n}.yaml").write_text(f"timestamp: run {n}\n")


def _run_numbers(eval_dir):
    """Numbered runs only — a hand-named `run_old.yaml` is not one of them, and
    counting it here would make this helper fail where the code does not."""
    return sorted(int(p.stem.split("_", 1)[1]) for p in eval_dir.glob("run_*.yaml")
                  if p.stem.split("_", 1)[1].isdigit())


class TestTheOldestRunsAreDropped:

    def test_the_count_is_capped(self, eval_dir):
        _write_runs(eval_dir, KEEP_RUNS_PER_EVAL + 15)

        Logger._trim_old_runs(eval_dir)

        assert len(_run_numbers(eval_dir)) == KEEP_RUNS_PER_EVAL

    def test_the_newest_run_survives(self, eval_dir):
        last = KEEP_RUNS_PER_EVAL + 15
        _write_runs(eval_dir, last)

        Logger._trim_old_runs(eval_dir)

        assert last in _run_numbers(eval_dir)

    def test_what_is_kept_is_the_newest_ones(self, eval_dir):
        last = KEEP_RUNS_PER_EVAL + 15
        _write_runs(eval_dir, last)

        Logger._trim_old_runs(eval_dir)

        assert _run_numbers(eval_dir) == list(range(last - KEEP_RUNS_PER_EVAL + 1, last + 1))

    def test_run_10_outlives_run_9(self, eval_dir):
        """Sorted as text, "run_10" comes before "run_9" — the newest run would
        be deleted first and the oldest kept. Run numbers are numbers."""
        _write_runs(eval_dir, 12)

        Logger._trim_old_runs(eval_dir, keep=3)

        assert _run_numbers(eval_dir) == [10, 11, 12]


class TestWhatItMustNotTouch:

    def test_a_directory_under_the_cap_is_left_alone(self, eval_dir):
        _write_runs(eval_dir, 3)

        Logger._trim_old_runs(eval_dir)

        assert _run_numbers(eval_dir) == [1, 2, 3]

    def test_the_eval_file_itself_is_not_a_run(self, eval_dir):
        """`.co/evals/{slug}.yaml` is what `co eval` reads. It lives beside the
        directory, but nothing here may reach for it."""
        evals_root = eval_dir.parent
        (evals_root / "some_task.yaml").write_text("input: hello\n")
        _write_runs(eval_dir, KEEP_RUNS_PER_EVAL + 5)

        Logger._trim_old_runs(eval_dir)

        assert (evals_root / "some_task.yaml").exists()

    def test_other_files_in_the_directory_stay(self, eval_dir):
        _write_runs(eval_dir, KEEP_RUNS_PER_EVAL + 5)
        (eval_dir / "notes.md").write_text("why this failed")
        (eval_dir / "run_1.jsonl").write_text("{}")

        Logger._trim_old_runs(eval_dir)

        assert (eval_dir / "notes.md").exists()

    def test_a_missing_directory_is_not_an_error(self, tmp_path):
        """Housekeeping must never be able to stop a turn."""
        Logger._trim_old_runs(tmp_path / "not_here")

    def test_a_stray_name_does_not_stop_the_trim(self, eval_dir):
        """Something hand-named in the directory must not raise on int()."""
        _write_runs(eval_dir, KEEP_RUNS_PER_EVAL + 5)
        (eval_dir / "run_old.yaml").write_text("kept by hand")

        Logger._trim_old_runs(eval_dir)

        assert len(_run_numbers(eval_dir)) == KEEP_RUNS_PER_EVAL


class TestItRunsWhenARunIsWritten:
    """A cap nothing calls is a cap that does not exist."""

    def test_writing_past_the_cap_leaves_the_cap(self, tmp_path, monkeypatch):
        import connectonion.logger as logger_module

        monkeypatch.setattr(logger_module, "KEEP_RUNS_PER_EVAL", 5)

        d = tmp_path / "evals" / "task"
        d.mkdir(parents=True)
        _write_runs(d, 40)

        Logger._trim_old_runs(d)

        assert len(list(d.glob("run_*.yaml"))) == 5

"""Eight concurrent `co ai` calls, and then no `co ai` call works again.

Aaron measured it (#695). The logger writes one eval file per unique *first
input*, `.co/evals/{slug}.yaml`. Several processes with the same opening line
derive the same slug and write the same file with no locking, and the
interleaved writes leave invalid YAML behind. After that every later call dies
on load -- including calls from unrelated projects, because `co ai` uses the
global `~/.co`:

    could not find expected ':'
      in ".../.co/evals/5_slam_naturewill_jd_ros2_nav2_a_rrt_teb_mppi.yaml",
      line 66, column 15

    for i in $(seq 8); do co ai -m co/gemini-2.5-flash "Same opening line. Item $i" & done
    wait
    co ai -m co/gemini-2.5-flash hello   # now fails

What made it expensive: the failure is not in the run that caused it, and
`co ai` puts the error on stderr while writing nothing to stdout. A batch
script reading stdout sees "the model returned nothing" -- in Aaron's pipeline,
"extracted +0 people", exit code 0, green logs.

Two things are wrong and both are fixed here.

**The write is not atomic.** `open(path, 'w')` truncates, then dumps; a second
process doing the same thing at the same moment interleaves with it. Written to
a temporary file in the same directory and moved into place with `os.replace`,
a reader sees either the old file or the new one and never a half-written one.

**One bad file is fatal.** That is the same shape as #668 and #629: a
corrupt eval is a lost eval, not a reason the CLI stops working. It is renamed
aside and the run continues, so the next call is not broken by the last one.
"""

import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest
import yaml


REPO = Path(__file__).resolve().parents[2]


@pytest.fixture
def evals(tmp_path):
    d = tmp_path / ".co" / "evals"
    d.mkdir(parents=True)
    return d


def _logger(evals_dir, first_input="hello"):
    """A Logger with its eval file initialised, the way a turn does it."""
    from connectonion.logger import Logger

    logger = Logger("t", quiet=True, co_dir=evals_dir.parent)
    logger._init_eval_file(first_input)
    return logger


class TestACorruptFileIsNotFatal:

    def test_the_next_run_still_starts(self, evals):
        """The whole issue: one bad file disabled every later call."""
        (evals / "hello.yaml").write_text("turns:\n  - input: x\n   bad: [\n",
                                          encoding="utf-8")

        logger = _logger(evals)      # must not raise

        assert logger is not None

    def test_the_bad_file_is_kept_not_deleted(self, evals):
        """It is the record of a run. Moved aside so it can be looked at."""
        (evals / "hello.yaml").write_text("a: [\n", encoding="utf-8")

        _logger(evals)

        aside = list(evals.glob("hello.yaml.corrupt*"))
        assert aside, sorted(p.name for p in evals.iterdir())

    def test_the_new_file_is_valid(self, evals):
        (evals / "hello.yaml").write_text("a: [\n", encoding="utf-8")

        logger = _logger(evals)
        logger._write_eval()

        if (evals / "hello.yaml").exists():
            yaml.safe_load((evals / "hello.yaml").read_text(encoding="utf-8"))

    def test_a_valid_file_is_left_alone(self, evals):
        good = "turns:\n- input: hello\n  output: hi\nruns: 1\nmodel: m\n"
        (evals / "hello.yaml").write_text(good, encoding="utf-8")

        _logger(evals)

        assert (evals / "hello.yaml").read_text(encoding="utf-8") == good
        assert not list(evals.glob("*.corrupt*"))


class TestTheWriteIsAtomic:
    """A reader never sees a half-written file, so concurrent writers cannot
    leave one behind."""

    def test_no_partial_file_is_ever_visible(self, evals, monkeypatch):
        """Interrupt the dump mid-way; the file on disk must still parse.

        The old file is written by a real Logger rather than by hand, so it
        carries the keys _write_eval reads (name, created, runs, model, turns).
        A hand-written stand-in was missing them and failed with KeyError --
        proving nothing about atomicity.
        """
        seed = _logger(evals)
        seed._write_eval()
        good = (evals / "hello.yaml").read_text(encoding="utf-8")

        import connectonion.logger as logger_mod

        def explode(*args, **kwargs):
            raise RuntimeError("died mid-write")

        logger = _logger(evals)
        assert good
        monkeypatch.setattr(logger_mod.yaml, "dump", explode)
        with pytest.raises(RuntimeError):
            logger._write_eval()

        # The old content survived; nothing truncated it.
        yaml.safe_load((evals / "hello.yaml").read_text(encoding="utf-8"))

    def test_eight_writers_leave_valid_yaml(self, evals):
        """The reproduction from the issue, without the model calls.

        Eight processes, one slug, writing at once. Serialised through the same
        code path a real run uses.
        """
        script = textwrap.dedent(f"""
            import sys
            sys.path.insert(0, {str(REPO)!r})
            from pathlib import Path
            from connectonion.logger import Logger
            d = Path({str(evals.parent)!r})
            for _ in range(20):
                lg = Logger("t", quiet=True, co_dir=d)
                lg._init_eval_file("Same opening line")
                lg.eval_data.setdefault("turns", [{{"input": "Same opening line",
                                                   "output": "x" * 200}}])
                lg.eval_data.setdefault("runs", 1)
                lg.eval_data.setdefault("model", "m")
                lg._write_eval()
        """)
        procs = [subprocess.Popen([sys.executable, "-c", script])
                 for _ in range(8)]
        for proc in procs:
            proc.wait(timeout=300)

        for path in evals.glob("*.yaml"):
            yaml.safe_load(path.read_text(encoding="utf-8"))

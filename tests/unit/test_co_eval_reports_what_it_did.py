"""`co eval` complains about files it wrote itself, then exits 0.

`.co/evals/` is two things at once: the eval **suite** you author, and the run
**log** the framework writes. `co eval` scans the directory, so it reports on
both. Measured on main, in a project where an agent had run a few turns:

    $ co eval
    No agent specified for say_a
    Add 'agent: agent.py' to the YAML or use --agent flag
    … 8 of these …

    9 no expected
    $ echo $?
    0

    project where an agent ran :   8 files, 0 authored, 8 written by the logger
    ~/.co/evals (co ai's home) : 487 files, 0 authored, 487 written by the logger

Every file it complained about is one `logger.py` put there — its own header
says so: "writes YAML evals to `.co/evals/` … one file per unique first input".

Two separate things, both fixed here.

**A record is not a test.** `docs/debug/eval.md` documents an authored eval as
requiring `agent:` and `expected:`; the auto-written records have neither, and
were never meant to be runnable. So a file with no `agent:` **and** no
`expected:` is a run record and is skipped without complaint. A file with one
of them is a half-written test and still says so — that is a real mistake and
staying quiet about it would be the opposite bug.

**Nothing ran, and it said success.** Eight could not run, nine had no
expectation, none executed, exit 0. Anything gating on `co eval` in CI reads
that as "evals passed". Same family as #535's second half, settled for the
schedule display: `done` must not imply the work succeeded.
"""

import pytest

from connectonion.cli.commands.eval_commands import is_run_record


RECORD = {
    "name": "say hello",
    "created": "2026-08-05",
    "runs": 3,
    "model": "co/gemini-2.5-flash",
    "turns": [{"input": "say hello", "output": "Hello!"}],
}

AUTHORED = {
    "agent": "agent.py",
    "input": "say hello",
    "expected": "a greeting",
}


class TestWhatIsATestAndWhatIsALog:

    def test_a_logger_record_is_not_a_test(self):
        assert is_run_record(RECORD) is True

    def test_an_authored_eval_is(self):
        assert is_run_record(AUTHORED) is False

    def test_expected_alone_is_a_test(self):
        """Half-written, and worth complaining about — `--agent` supplies the
        other half, so this is runnable."""
        assert is_run_record({"input": "x", "expected": "y"}) is False

    def test_agent_alone_is_a_test(self):
        """Also half-written: it names an agent but nothing to check."""
        assert is_run_record({"agent": "agent.py", "input": "x"}) is False

    def test_an_empty_file_is_not_a_test(self):
        assert is_run_record({}) is True
        assert is_run_record(None) is True

    def test_the_shape_the_logger_actually_writes(self):
        """Against the real writer, not a guess at its output."""
        import tempfile
        from pathlib import Path

        import yaml

        from connectonion.logger import Logger

        co_dir = Path(tempfile.mkdtemp()) / ".co"
        (co_dir / "evals").mkdir(parents=True)
        logger = Logger("t", quiet=True, co_dir=co_dir)
        logger._init_eval_file("say hello")
        logger._write_eval()

        written = list((co_dir / "evals").glob("*.yaml"))
        assert written, "the logger wrote no eval file"
        assert is_run_record(yaml.safe_load(written[0].read_text(encoding="utf-8")))


class TestTheExitCodeMeansSomething:

    def _run(self, tmp_path, monkeypatch, **files):
        """`co eval` in a project holding these files, returning its exit code."""
        import yaml
        from connectonion.cli.commands import eval_commands

        evals = tmp_path / ".co" / "evals"
        evals.mkdir(parents=True)
        for stem, data in files.items():
            (evals / f"{stem}.yaml").write_text(yaml.safe_dump(data), encoding="utf-8")
        monkeypatch.chdir(tmp_path)

        return eval_commands.handle_eval()

    def test_nothing_to_run_is_not_success(self, tmp_path, monkeypatch):
        """The measured case: only logger records, nothing executed, exit 0."""
        code = self._run(tmp_path, monkeypatch, say_a=RECORD, say_b=RECORD)

        assert code != 0, "a run where nothing executed reported success"

    def test_an_empty_directory_is_not_success(self, tmp_path, monkeypatch):
        code = self._run(tmp_path, monkeypatch)

        assert code != 0

    def test_a_half_written_eval_is_not_success(self, tmp_path, monkeypatch):
        code = self._run(tmp_path, monkeypatch, half={"input": "x", "expected": "y",
                                                      "agent": "missing.py"})

        assert code != 0


class TestTheNoiseIsGone:

    def test_a_logger_record_draws_no_complaint(self, tmp_path, monkeypatch, capsys):
        import yaml
        from connectonion.cli.commands import eval_commands

        evals = tmp_path / ".co" / "evals"
        evals.mkdir(parents=True)
        (evals / "say_a.yaml").write_text(yaml.safe_dump(RECORD), encoding="utf-8")
        monkeypatch.chdir(tmp_path)

        eval_commands.handle_eval()
        out = capsys.readouterr()

        assert "No agent specified" not in (out.out + out.err), out.out

    def test_a_half_written_eval_still_complains(self, tmp_path, monkeypatch, capsys):
        """The opposite bug would be silence about a real mistake."""
        import yaml
        from connectonion.cli.commands import eval_commands

        evals = tmp_path / ".co" / "evals"
        evals.mkdir(parents=True)
        (evals / "half.yaml").write_text(
            yaml.safe_dump({"input": "x", "expected": "y"}), encoding="utf-8")
        monkeypatch.chdir(tmp_path)

        eval_commands.handle_eval()
        out = capsys.readouterr()

        assert "No agent specified" in (out.out + out.err), out.out


class TestTheShellSeesIt:
    """The exit code has to survive the CLI layer, or the fix is unreachable
    from the place that reads it."""

    def _co_eval(self, tmp_path, files):
        import subprocess
        import sys

        import yaml

        evals = tmp_path / ".co" / "evals"
        evals.mkdir(parents=True)
        for stem, data in files.items():
            (evals / f"{stem}.yaml").write_text(yaml.safe_dump(data), encoding="utf-8")

        return subprocess.run(
            [sys.executable, "-m", "connectonion.cli.main", "eval"],
            cwd=tmp_path, capture_output=True, text=True, timeout=300,
            env={**__import__("os").environ,
                 "PYTHONPATH": str(__import__("pathlib").Path(__file__).resolve().parents[2])},
        )

    def test_only_run_records_exits_non_zero(self, tmp_path):
        result = self._co_eval(tmp_path, {"say_a": RECORD, "say_b": RECORD})

        assert result.returncode != 0, result.stdout[-400:]

    def test_it_says_they_were_skipped_rather_than_broken(self, tmp_path):
        result = self._co_eval(tmp_path, {"say_a": RECORD})

        assert "No agent specified" not in result.stdout
        assert "run record" in result.stdout, result.stdout[-300:]

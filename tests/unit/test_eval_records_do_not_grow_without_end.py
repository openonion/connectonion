"""Generated session records are useful history, not permanent storage.

`co ai` wrote one YAML file and one run directory for every distinct first
prompt. A developer measured 2,311 records using 281 MB after six months. The
eval plugin did not create these files; Logger did, even without the plugin.

Retention therefore belongs at the logger boundary. It removes only records
whose shape identifies them as generated, preserves authored `co eval` tests,
and removes the full-message directory paired with an expired record.
"""

import os

import yaml

from connectonion.logger import Logger


def _generated(evals_dir, name, modified):
    path = evals_dir / f"{name}.yaml"
    path.write_text(
        yaml.safe_dump({
            "name": name,
            "created": "2026-01-01 00:00:00",
            "runs": 1,
            "model": "test",
            "turns": [],
        }),
        encoding="utf-8",
    )
    run_dir = evals_dir / name
    run_dir.mkdir()
    (run_dir / "run_1.yaml").write_text("messages: '[]'\n", encoding="utf-8")
    os.utime(path, (modified, modified))
    return path, run_dir


def test_old_generated_records_and_their_runs_are_removed(tmp_path):
    evals_dir = tmp_path / "evals"
    evals_dir.mkdir()
    oldest, oldest_runs = _generated(evals_dir, "oldest", 1)
    middle, _ = _generated(evals_dir, "middle", 2)
    newest, _ = _generated(evals_dir, "newest", 3)

    Logger._trim_old_evals(evals_dir, keep=2)

    assert not oldest.exists()
    assert not oldest_runs.exists()
    assert middle.exists()
    assert newest.exists()


def test_authored_evals_never_count_toward_retention(tmp_path):
    evals_dir = tmp_path / "evals"
    evals_dir.mkdir()
    authored = evals_dir / "acceptance.yaml"
    authored.write_text(
        yaml.safe_dump({
            "name": "acceptance",
            "agent": "agent.py",
            "turns": [{"input": "hello", "expected": "a greeting"}],
        }),
        encoding="utf-8",
    )
    old, _ = _generated(evals_dir, "old", 1)
    recent, _ = _generated(evals_dir, "recent", 2)

    Logger._trim_old_evals(evals_dir, keep=1)

    assert authored.exists()
    assert not old.exists()
    assert recent.exists()


def test_writing_a_new_record_enforces_the_cap(tmp_path, monkeypatch):
    import connectonion.logger as logger_module

    monkeypatch.setattr(logger_module, "KEEP_EVAL_RECORDS", 2)
    logger = Logger("test", quiet=True, co_dir=tmp_path / ".co")

    for index in range(3):
        logger.start_session()
        logger.log_turn(
            f"unique prompt {index}",
            "done",
            1,
            {"trace": [], "turn": 1, "messages": []},
            "test",
        )

    assert len(list((tmp_path / ".co" / "evals").glob("*.yaml"))) == 2

"""A turn that died with its process is not running.

From a deployed agent's Home, all four rows rendered as `running`:

    检查新合同 ×2                        running · 12m ago
    /contract-ledger 检查云盘…            running · 43m ago
    /contract-ledger 检查云盘…            running · 59m ago
    /contract-ledger 检查云盘…            running · 1h ago

None were. The process had been restarted three times mid-turn. `running`
sessions are also exempt from TTL expiry, so these do not age out — they are
permanent.
"""

import json
import time

from connectonion.network.host.session.storage import Session, SessionStorage


def write(storage, session_id, status, created=None):
    storage.save(Session(
        session_id=session_id, status=status, prompt="go",
        created=created if created is not None else time.time(),
        expires=time.time() + 86400,
    ))


def test_a_session_left_running_is_marked_interrupted(tmp_path):
    storage = SessionStorage(str(tmp_path / "s.jsonl"))
    write(storage, "dead", "running")

    storage.reconcile_interrupted()

    assert storage.get("dead").status == "interrupted"


def test_a_finished_session_is_untouched(tmp_path):
    storage = SessionStorage(str(tmp_path / "s.jsonl"))
    write(storage, "ok", "running")
    write(storage, "ok", "done")

    storage.reconcile_interrupted()

    assert storage.get("ok").status == "done"


def test_it_keeps_what_the_session_was(tmp_path):
    """The row still has to render: prompt and timing survive."""
    storage = SessionStorage(str(tmp_path / "s.jsonl"))
    created = time.time() - 600
    storage.save(Session(session_id="dead", status="running",
                         prompt="/contract-ledger 检查云盘", created=created,
                         expires=time.time() + 86400))

    storage.reconcile_interrupted()

    s = storage.get("dead")
    assert s.prompt == "/contract-ledger 检查云盘"
    assert s.created == created


def test_it_is_append_only(tmp_path):
    """History is not rewritten — the running record stays, a new one lands."""
    path = tmp_path / "s.jsonl"
    storage = SessionStorage(str(path))
    write(storage, "dead", "running")

    storage.reconcile_interrupted()

    rows = [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines()]
    assert [r["status"] for r in rows] == ["running", "interrupted"]


def test_no_file_is_not_an_error(tmp_path):
    SessionStorage(str(tmp_path / "missing.jsonl")).reconcile_interrupted()


def test_it_does_not_rewrite_on_every_boot(tmp_path):
    """Twice in a row must not append a second interrupted record."""
    path = tmp_path / "s.jsonl"
    storage = SessionStorage(str(path))
    write(storage, "dead", "running")

    storage.reconcile_interrupted()
    storage.reconcile_interrupted()

    rows = [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines()]
    assert [r["status"] for r in rows] == ["running", "interrupted"]


def test_an_interrupted_session_expires_like_any_other(tmp_path):
    """The reason phantoms were permanent: `running` is exempt from TTL."""
    storage = SessionStorage(str(tmp_path / "s.jsonl"))
    storage.save(Session(session_id="old", status="running", prompt="go",
                         created=time.time() - 90000,
                         expires=time.time() - 10))     # already past TTL

    storage.reconcile_interrupted()

    assert storage.get("old") is None
    assert [s.session_id for s in storage.list()] == []


def test_a_session_waiting_for_an_answer_is_also_reconciled(tmp_path):
    """A question nobody can answer any more is as dead as a run nobody finished.

    `waiting_approval` means a turn stopped and asked. After a restart the thread
    that would receive the answer is gone, so the question cannot be answered by
    anyone — but it kept claiming to be waiting. Measured on a deployed agent
    nine hours after the reconcile shipped: five such sessions, the oldest 52
    hours old, three of them still inside their TTL and still rendering as
    waiting for a decision nobody could make.
    """
    storage = SessionStorage(str(tmp_path / "s.jsonl"))
    write(storage, "asked", "waiting_approval")

    storage.reconcile_interrupted()

    assert storage.get("asked").status == "interrupted"


def test_an_answered_question_is_untouched(tmp_path):
    storage = SessionStorage(str(tmp_path / "s.jsonl"))
    write(storage, "asked", "waiting_approval")
    write(storage, "asked", "done")

    storage.reconcile_interrupted()

    assert storage.get("asked").status == "done"


class TestATornLineIsNotFatal:
    """An append-only file can be torn. Booting over it is not optional.

    `.co/session_results.jsonl` is appended from more than one thread, and a
    crash, a full disk, or an interleaved write leaves a partial line. The
    schedule's own state file decided this years ago — "Refusing to boot over it
    costs the agent, so a truncated write or a hand edit is not allowed to be
    fatal" — and this file never got the same treatment.

    It became a boot failure rather than a display bug when reconcile started
    running at startup.
    """

    def torn(self, tmp_path, body):
        path = tmp_path / "s.jsonl"
        path.write_text(body, encoding="utf-8")
        return SessionStorage(str(path))

    def test_reconcile_survives_a_torn_line(self, tmp_path):
        storage = self.torn(tmp_path, '{"session_id": "a", "status": "runni')
        storage.reconcile_interrupted()          # must not raise

    def test_list_survives_a_torn_line(self, tmp_path):
        storage = self.torn(tmp_path, 'not json at all\n')
        assert storage.list() == []

    def test_get_survives_a_torn_line(self, tmp_path):
        storage = self.torn(tmp_path, 'not json at all\n')
        assert storage.get("a") is None

    def test_the_good_lines_around_it_still_count(self, tmp_path):
        """A torn line costs that one record, not the file."""
        good = json.dumps({"session_id": "b", "status": "running", "prompt": "go",
                           "created": time.time(), "expires": time.time() + 86400})
        storage = self.torn(tmp_path, f'{{"broken\n{good}\n')

        storage.reconcile_interrupted()

        assert storage.get("b").status == "interrupted"

    def test_a_blank_line_is_not_a_record(self, tmp_path):
        storage = self.torn(tmp_path, '\n\n')
        assert storage.list() == []

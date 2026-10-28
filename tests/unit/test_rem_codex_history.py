"""A history repair must archive internal traces without claiming personal chats."""

import importlib
import json
import sqlite3

import pytest

from connectonion.rem.codex_history import archive_history, internal_threads

native = importlib.import_module("connectonion.useful_tools.codex")


@pytest.fixture
def history(tmp_path, monkeypatch):
    root, home = tmp_path / "notebook", tmp_path / "codex"
    root.mkdir()
    home.mkdir()
    database = home / "state_5.sqlite"
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE threads(id TEXT, cwd TEXT, archived INTEGER, "
                           "originator TEXT, is_pinned INTEGER, updated_at INTEGER)")

    def add(thread_id, *, cwd=None, archived=0, originator="connectonion", pinned=0, updated=0):
        with sqlite3.connect(database) as connection:
            connection.execute("INSERT INTO threads VALUES(?,?,?,?,?,?)",
                               (thread_id, str(cwd or root / ".state/tasks"), archived, originator, pinned, updated))
    return root, home, database, add


def test_inventory_keeps_personal_pinned_recent_archived_and_neighboring_chats(history):
    import time
    root, home, _, add = history
    add("internal")
    add("nested", cwd=root / ".state/tasks/sessions-summary-1")
    add("personal", cwd=root)
    add("neighbor", cwd=root / ".state/tasks-personal")
    add("different-client", originator="Codex Desktop")
    add("pinned", pinned=1)
    add("archived", archived=1)
    add("recent", updated=int(time.time()))
    assert {row["id"] for row in internal_threads(root, home=home)} == {"internal", "nested"}


def test_missing_index_does_not_start_a_provider(tmp_path, monkeypatch):
    monkeypatch.setattr(native, "CodexAppServer", lambda **kwargs: pytest.fail("No history needs a provider"))
    assert archive_history(tmp_path, home=tmp_path) == {"archived": 0, "kept": 0}


def fake_provider(history, monkeypatch, states=None, fail=False):
    root, home, database, _ = history
    calls = []

    class Server:
        def __init__(self, **kwargs):
            assert kwargs["env"]["CODEX_HOME"] == str(home)

        def start(self):
            calls.append("start")

        def initialize(self, **kwargs):
            calls.append("initialize")

        def close(self):
            calls.append("close")

        def request(self, method, params, **kwargs):
            assert method in ("thread/read", "thread/archive"), "No model turn or thread resume"
            thread_id = params["threadId"]
            if method == "thread/read":
                return {"thread": {"id": thread_id, "cwd": str(root / ".state/tasks"),
                                   "status": {"type": "notLoaded"}, "updatedAt": 0,
                                   **(states or {}).get(thread_id, {})}}
            if fail:
                raise RuntimeError("archive unavailable")
            with sqlite3.connect(database) as connection:
                connection.execute("UPDATE threads SET archived=1 WHERE id=?", (thread_id,))
            calls.append(thread_id)
            return {}

    monkeypatch.setattr(native, "CodexAppServer", Server)
    monkeypatch.setattr(native, "_base_command", lambda: ["fixture"])
    return calls


def test_repair_archives_through_native_rpc_keeps_a_receipt_and_is_idempotent(history, monkeypatch):
    root, home, _, add = history
    add("one")
    add("two")
    calls = fake_provider(history, monkeypatch)
    assert archive_history(root, home=home) == {"archived": 2, "kept": 0}
    assert calls[-1] == "close"
    receipt = json.loads((root / ".state/codex-history.json").read_text())
    assert set(receipt["archived"]) == {"one", "two"}
    assert archive_history(root, home=home) == {"archived": 0, "kept": 0}


@pytest.mark.parametrize("change", [{"status": {"type": "active"}}, {"isPinned": True},
                                     {"cwd": "/another/notebook"}, {"id": "another-thread"}])
def test_live_metadata_is_rechecked_before_archiving(history, monkeypatch, change):
    root, home, _, add = history
    add("keep")
    calls = fake_provider(history, monkeypatch, {"keep": change})
    assert archive_history(root, home=home) == {"archived": 0, "kept": 1}
    assert "keep" not in calls


def test_native_failure_surfaces_and_closes_the_client(history, monkeypatch):
    root, home, _, add = history
    add("one")
    calls = fake_provider(history, monkeypatch, fail=True)
    with pytest.raises(RuntimeError, match="archive unavailable"):
        archive_history(root, home=home)
    assert calls[-1] == "close"
    receipt = json.loads((root / ".state/codex-history.json").read_text())
    assert receipt["archived"] == [] and receipt["requested"] == ["one"]


@pytest.mark.parametrize("field,value", [("is_pinned", 1), ("updated_at", 9_999_999_999)])
def test_database_pin_and_recency_are_rechecked_even_when_rpc_omits_pin(history, monkeypatch, field, value):
    import connectonion.rem.codex_history as module
    root, home, database, add = history
    add("changed")
    fake_provider(history, monkeypatch)
    scan = module.internal_threads

    def inventory(*args, **kwargs):
        rows = scan(*args, **kwargs)
        with sqlite3.connect(database) as connection:
            connection.execute(f"UPDATE threads SET {field}=? WHERE id='changed'", (value,))
        return rows

    monkeypatch.setattr(module, "internal_threads", inventory)
    assert archive_history(root, home=home) == {"archived": 0, "kept": 1}


@pytest.mark.parametrize("updated", [None, 9_999_999_999])
def test_unknown_or_new_live_recency_is_kept(history, monkeypatch, updated):
    root, home, _, add = history
    add("keep")
    fake_provider(history, monkeypatch, {"keep": {"updatedAt": updated}})
    assert archive_history(root, home=home) == {"archived": 0, "kept": 1}


def test_receipt_records_successful_siblings_when_one_worker_fails(history, monkeypatch):
    root, home, _, add = history
    for name in ("bad", "one", "two"):
        add(name)
    fake_provider(history, monkeypatch)
    import connectonion.rem.codex_history as module
    archive = module._archive_thread

    def request(client, row, workspace, codex_home):
        if row["id"] == "bad":
            raise RuntimeError("native failure")
        return archive(client, row, workspace, codex_home)

    monkeypatch.setattr(module, "_archive_thread", request)
    with pytest.raises(RuntimeError, match="native failure"):
        archive_history(root, home=home)
    receipt = json.loads((root / ".state/codex-history.json").read_text())
    assert set(receipt["archived"]) == {"one", "two"}
    assert receipt["failed"] == [{"id": "bad", "error": "RuntimeError"}]


def test_client_closes_even_when_final_receipt_cannot_be_written(history, monkeypatch):
    root, home, _, add = history
    add("one")
    calls = fake_provider(history, monkeypatch)
    import connectonion.rem.codex_history as module
    real_write, count = module.write_json, 0

    def write(path, value):
        nonlocal count
        count += 1
        if count > 1:
            raise OSError("receipt unavailable")
        real_write(path, value)

    monkeypatch.setattr(module, "write_json", write)
    with pytest.raises(OSError, match="receipt unavailable"):
        archive_history(root, home=home)
    assert calls[-1] == "close"


def test_a_native_error_is_reconciled_only_when_the_scoped_record_is_already_archived(history, monkeypatch):
    root, home, database, add = history
    add("one")
    fake_provider(history, monkeypatch)
    import connectonion.rem.codex_history as module

    def completed_elsewhere(client, row, workspace, codex_home):
        with sqlite3.connect(database) as connection:
            connection.execute("UPDATE threads SET archived=1 WHERE id=?", (row["id"],))
        raise RuntimeError("no rollout found after another archive completed")

    monkeypatch.setattr(module, "_archive_thread", completed_elsewhere)
    assert archive_history(root, home=home) == {"archived": 1, "kept": 0}
    receipt = json.loads((root / ".state/codex-history.json").read_text())
    assert receipt["failed"] == [] and receipt["reconciled"] == ["one"]

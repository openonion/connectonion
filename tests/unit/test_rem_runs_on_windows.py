"""co rem on a Windows PC: found on the first real run, on a Windows 11 box."""

import importlib
import sys
import types

config = importlib.import_module("connectonion.rem.config")


def test_windows_reads_its_timezone_from_the_registry_through_tzlocal(monkeypatch):
    # Windows has no /etc/localtime: co rem init stopped at "Set schedule.timezone
    # to a valid IANA timezone" on every Windows PC.
    monkeypatch.delenv("TZ", raising=False)
    monkeypatch.setattr(config, "os", types.SimpleNamespace(name="nt", environ={}))
    monkeypatch.setitem(sys.modules, "tzlocal",
                        types.SimpleNamespace(get_localzone_name=lambda: "Pacific/Chatham"))
    assert config.local_timezone() == "Pacific/Chatham"


def test_tz_still_wins_on_windows(monkeypatch):
    monkeypatch.setattr(config, "os", types.SimpleNamespace(name="nt", environ={"TZ": "Europe/Oslo"}))
    assert config.local_timezone() == "Europe/Oslo"


def test_an_index_without_its_schema_is_closed_before_it_is_deleted(tmp_path, monkeypatch):
    # Windows refuses to delete an open file (WinError 32): a new notebook's
    # first index was skipped with "store skipped: PermissionError".
    import sqlite3
    store = importlib.import_module("connectonion.rem.store")

    file = tmp_path / "rem.db"
    sqlite3.connect(file).execute("create table other (x)").connection.close()
    opened = []
    connect = store._connect
    monkeypatch.setattr(store, "_connect", lambda path: opened.append(connect(path)) or opened[-1])
    removed = store._remove

    def windows_remove(path):
        for db in opened:
            try:
                db.execute("select 1")
            except sqlite3.ProgrammingError:
                continue  # closed
            raise PermissionError(32, "being used by another process", str(path))
        removed(path)

    monkeypatch.setattr(store, "_remove", windows_remove)
    db, fresh = store._open_for_build(file)
    assert fresh is True
    db.close()

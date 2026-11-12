"""The cross-process maintenance lock refuses a second holder on every OS."""

import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from connectonion.rem.files import RemError, _file_lock, maintenance_lock


def test_file_lock_refuses_a_second_holder(tmp_path):
    root = tmp_path / "rem"
    with _file_lock(root, wait=0):
        with pytest.raises(RemError):
            with _file_lock(root, wait=0):
                pass


def test_file_lock_without_o_nofollow(tmp_path, monkeypatch):
    monkeypatch.delattr(os, "O_NOFOLLOW", raising=False)
    root = tmp_path / "rem"
    with _file_lock(root, wait=0):
        with pytest.raises(RemError):
            with _file_lock(root, wait=0):
                pass


@pytest.mark.parametrize("operation", ["next", "submit"])
def test_native_wait_is_bounded_and_prints_progress(tmp_path, capsys, operation):
    with _file_lock(tmp_path, wait=0, operation=operation):
        with pytest.raises(RemError, match="busy.*retry co rem next"):
            with maintenance_lock(tmp_path, wait=0.01, operation="next", wait_for_native=True):
                pytest.fail("the other native command still holds the lock")
    assert capsys.readouterr().err.count("Waiting for another co rem next") == 1


@pytest.mark.parametrize("phase", ["publication", "removal"])
def test_native_wait_handles_owner_metadata_windows(tmp_path, monkeypatch, phase):
    from connectonion.rem import files
    entered, proceed = threading.Event(), threading.Event()
    write = files.write_json

    def publish(path, value):
        if path.name == "maintenance-owner.json" and phase == "publication" and not entered.is_set():
            entered.set()
            assert proceed.wait(2)
        write(path, value)
        if path.name == "maintenance-owner.json" and not value and phase == "removal" and not entered.is_set():
            entered.set()
            assert proceed.wait(2)

    def holder():
        with _file_lock(tmp_path, wait=0, operation="next"):
            pass

    monkeypatch.setattr(files, "write_json", publish)
    with ThreadPoolExecutor(max_workers=1) as pool:
        first = pool.submit(holder)
        assert entered.wait(2)
        release = threading.Timer(0.05, proceed.set)
        release.start()
        # The holder lets go 0.05 s in; the bound only has to outlast that on
        # a busy runner (0.2 s ran out on a four-worker CI shard, run 42658773686).
        with maintenance_lock(tmp_path, wait=2, operation="next", wait_for_native=True):
            pass
        release.join()
        first.result()


def test_owner_metadata_stays_readable_when_holder_releases(tmp_path, monkeypatch):
    from connectonion.rem import files
    lock = _file_lock(tmp_path, wait=0, operation="next")
    lock.__enter__()
    owner, exists = files.state_path(tmp_path, "maintenance-owner.json"), Path.exists

    def release_after_exists(path):
        present = exists(path)
        if path == owner:
            lock.__exit__(None, None, None)
        return present

    monkeypatch.setattr(Path, "exists", release_after_exists)
    assert files.read_json(owner, None) == {}


def test_thread_wait_rechecks_a_holder_that_publishes_sync_metadata(tmp_path, monkeypatch):
    from connectonion.rem import files
    entered, proceed = threading.Event(), threading.Event()
    write = files.write_json

    def publish(path, value):
        if path.name == "maintenance-owner.json":
            entered.set()
            assert proceed.wait(2)
        write(path, value)

    def sync():
        with maintenance_lock(tmp_path):
            time.sleep(1.5)

    monkeypatch.setattr(files, "write_json", publish)
    with ThreadPoolExecutor(max_workers=1) as pool:
        first = pool.submit(sync)
        assert entered.wait(2)
        release = threading.Timer(0.05, proceed.set)
        release.start()
        with pytest.raises(RemError, match="busy.*retry co rem next"):
            with maintenance_lock(tmp_path, wait=3, operation="next", wait_for_native=True):
                pytest.fail("a sync holder must be refused before it releases the lock")
        release.join()
        first.result()

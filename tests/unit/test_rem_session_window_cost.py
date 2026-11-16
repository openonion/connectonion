"""A person's page reads each coding-session log once, not the whole store again (1.9.6rc18).

11-16: `co rem next` spent its ten minutes "preparing" one person's page three
times in one turn. Stack dumps put it in the session window, re-reading and
re-hashing Codex rollouts: 6.7 GB on that machine. The window is one cache for
every page, and it was thrown away whenever a rollout it had read was no longer
a plain file, which is what Codex does when it compresses an old session. The
rollouts here are generated, mostly tool output like real ones.
"""

import io
import json
from datetime import datetime, timedelta, timezone

import pytest
import zstandard

from connectonion.rem import investigate as inv, source

NOW = datetime.now(timezone.utc)
MEGABYTES = 12
TOOL_OUTPUT = json.dumps({"timestamp": NOW.isoformat(), "type": "response_item",
                          "payload": {"type": "function_call_output", "output": "x" * 4000}}) + "\n"


def typed(text):
    return json.dumps({"timestamp": (NOW - timedelta(days=1)).isoformat(), "type": "response_item", "payload": {
        "type": "message", "role": "user", "content": [{"type": "input_text", "text": text}]}}) + "\n"


def rollout(path, megabytes=MEGABYTES):
    path.parent.mkdir(parents=True, exist_ok=True)
    meta = {"type": "session_meta", "payload": {"id": path.stem, "cwd": "/work/demo", "originator": "codex-tui",
                                                "source": "cli", "cli_version": "0.1"}}
    with path.open("w") as out:
        out.write(json.dumps(meta) + "\n")
        for part in range(megabytes):
            out.write(TOOL_OUTPUT * 250)  # about a megabyte nobody typed
            out.write(typed(f"Ask Rowan about {path.stem} part {part}." if part % 2 else
                            f"Tell Briar about {path.stem} part {part}."))


class Counted(io.BufferedReader):
    """Every byte a reader takes from a rollout, and every time one is opened."""
    read_bytes, opened = 0, []

    def read(self, *args):
        data = super().read(*args)
        Counted.read_bytes += len(data)
        return data

    def readline(self, *args):
        data = super().readline(*args)
        Counted.read_bytes += len(data)
        return data


@pytest.fixture
def store(tmp_path, monkeypatch):
    sessions = tmp_path / "sessions"
    for name in ("a", "b", "c"):
        rollout(sessions / f"rollout-{name}.jsonl")
    real = source.open_session

    def counted(path):
        Counted.opened.append(path.name)
        return Counted(real(path).detach(), 1 << 20)

    monkeypatch.setattr(source, "open_session", counted)
    monkeypatch.setattr(inv, "_WINDOWS", {})
    return sessions, tmp_path / "rem"


def new_process(monkeypatch):
    """Each `co rem next` is its own process: nothing is remembered but the notebook's files."""
    monkeypatch.setattr(inv, "_WINDOWS", {})
    Counted.read_bytes, Counted.opened = 0, []


def person(store, name, monkeypatch):
    sessions, root = store
    new_process(monkeypatch)
    items, _ = inv.gather(name.title(), [name], days=14, clients={}, record=f"people/{name}.md", archive_root=root,
                          subscriptions={"codex": {"kind": "codex", "root": str(sessions)}})
    return [item["text"] for item in items]


def window(store, monkeypatch):
    sessions, root = store
    new_process(monkeypatch)
    items, _ = inv._session_window({"kind": "codex", "root": str(sessions), "enabled": True, "consented": True,
                                    "since": (NOW - timedelta(days=14)).isoformat()}, "sessions", None, root)
    return items


def test_two_person_pages_in_a_row_read_each_unchanged_rollout_once(store, monkeypatch):
    size = sum(path.stat().st_size for path in store[0].iterdir())
    rowan = person(store, "rowan", monkeypatch)
    assert len(rowan) == 3 * MEGABYTES // 2 and all("Rowan" in text for text in rowan)
    assert sorted(Counted.opened) == ["rollout-a.jsonl", "rollout-b.jsonl", "rollout-c.jsonl"]
    assert Counted.read_bytes <= size + 3_000_000  # each rollout once, plus its first line again
    briar = person(store, "briar", monkeypatch)
    assert len(briar) == 3 * MEGABYTES // 2 and all("Briar" in text for text in briar)
    assert Counted.opened == [] and Counted.read_bytes == 0


def test_a_rollout_codex_compressed_is_the_only_one_read_again_and_only_once(store, monkeypatch):
    sessions = store[0]
    before = window(store, monkeypatch)
    plain = sessions / "rollout-b.jsonl"
    packed = sessions / "rollout-b.jsonl.zst"
    packed.write_bytes(zstandard.ZstdCompressor().compress(plain.read_bytes()))
    plain.unlink()
    after = window(store, monkeypatch)
    assert Counted.opened == ["rollout-b.jsonl.zst"]
    assert Counted.read_bytes <= MEGABYTES * 1_100_000  # its plain bytes once: no second or third decompression
    assert [item["text"] for item in after] == [item["text"] for item in before]
    assert [item["source"] for item in after] == [item["source"] for item in before]
    # What a page cites must be a file that exists.
    assert {item["reference"] for item in after if "rollout-b" in item["reference"]} == {packed.as_uri()}
    window(store, monkeypatch)
    assert Counted.opened == [] and Counted.read_bytes == 0


def test_a_deleted_rollout_takes_only_its_own_messages_with_it(store, monkeypatch):
    sessions = store[0]
    before = window(store, monkeypatch)
    (sessions / "rollout-a.jsonl").unlink()
    after = window(store, monkeypatch)
    assert Counted.opened == [] and Counted.read_bytes == 0
    assert [item["text"] for item in after] == [item["text"] for item in before if "rollout-a" not in item["text"]]


def test_a_window_build_that_is_killed_resumes_where_it_was_saved(store, monkeypatch):
    """The ten-minute deadline ends the process: what was read before it must not be read again."""
    sessions = store[0]
    monkeypatch.setattr(inv, "WINDOW_SCAN_BYTES", MEGABYTES * 1_000_000)  # about one rollout between saves
    real, calls = inv.collect, []

    def killed_on_the_third_batch(*args, **kwargs):
        calls.append(1)
        if len(calls) == 3:
            raise KeyboardInterrupt
        return real(*args, **kwargs)

    monkeypatch.setattr(inv, "collect", killed_on_the_third_batch)
    with pytest.raises(KeyboardInterrupt):
        window(store, monkeypatch)
    first = list(Counted.opened)
    assert len(first) == 2
    monkeypatch.setattr(inv, "collect", real)
    items = window(store, monkeypatch)
    assert len(items) == 3 * MEGABYTES
    assert len(Counted.opened) == 1 and Counted.opened[0] not in first

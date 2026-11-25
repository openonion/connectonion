"""Codex sessions that Codex has compressed (rollout-*.jsonl.zst) are read (#2943).

Codex CLI compresses older sessions in place. On one machine about 22,000 of
22,800 Codex session files were .zst and REM's glob saw none of them, so a
first map saw a few weeks of history and skill counts dropped on the next map.
Every rollout here is invented; each compressed one must read exactly as its
plain twin.
"""

import json
import os
import shutil
from datetime import timedelta

import zstandard

from connectonion.rem import project_material, scan, session_pass, sessions, skill_usage, source
from connectonion.rem.config import prepare
from connectonion.rem.tidy import _typed_line
from test_rem_project_workspace import NOW, codex_session, exec_command, ws  # noqa: F401
from test_rem_source import rollout, subscription


def compress(path):
    """What Codex does: the same bytes as .jsonl.zst, the plain file gone, the time kept."""
    packed = path.with_name(path.name + ".zst")
    packed.write_bytes(zstandard.ZstdCompressor().compress(path.read_bytes()))
    stat = path.stat()
    os.utime(packed, ns=(stat.st_atime_ns, stat.st_mtime_ns))
    path.unlink()
    return packed


def plain(value):
    """A result with every compressed file's name read as its plain twin's."""
    return json.loads(json.dumps(value, default=str).replace(".jsonl.zst", ".jsonl"))


def everything(tmp_path):
    return source.collect(subscription(tmp_path), {}, 20, 10000)


def test_a_compressed_rollout_reads_like_its_plain_twin(tmp_path):
    rollout(tmp_path / "2026/09/07/rollout-fernhill.jsonl", [("user", "Move the Fernhill pilot to Friday"),
                                                             ("user", "and tell Wren")])
    expected = everything(tmp_path)
    compress(tmp_path / "2026/09/07/rollout-fernhill.jsonl")
    batch = everything(tmp_path)
    assert [item["text"] for item in batch.items] == ["Move the Fernhill pilot to Friday", "and tell Wren"]
    assert plain(batch.items) == plain(expected.items)
    assert batch.progress.keys() == expected.progress.keys()
    assert {key: entry["offset"] for key, entry in batch.progress.items()} == \
        {key: entry["offset"] for key, entry in expected.progress.items()}


def test_a_session_compressed_after_it_was_read_is_not_read_again_or_reopened(tmp_path):
    path = tmp_path / "rollout-fernhill.jsonl"
    rollout(path, [("user", "Move the Fernhill pilot to Friday")])
    read = everything(tmp_path)
    compress(path)
    again = source.collect(subscription(tmp_path), read.progress, 20, 10000)
    assert again.items == [] and not again.changed_files, again
    assert source.pending_metadata(subscription(tmp_path), again.progress)["candidate_files"] == 0


def test_a_session_present_in_both_forms_is_one_session(tmp_path):
    path = tmp_path / "rollout-fernhill.jsonl"
    rollout(path, [("user", "Move the Fernhill pilot to Friday")])
    shutil.copy(path, tmp_path / "copy.jsonl")
    compress(tmp_path / "copy.jsonl").rename(tmp_path / "rollout-fernhill.jsonl.zst")
    assert source.source_files(subscription(tmp_path)) == [path]
    assert [item["text"] for item in everything(tmp_path).items] == ["Move the Fernhill pilot to Friday"]


def test_a_compressed_session_read_in_parts_continues_where_it_stopped(tmp_path):
    rollout(tmp_path / "rollout-a.jsonl", [("user", str(n)) for n in range(5)])
    compress(tmp_path / "rollout-a.jsonl")
    first = source.collect(subscription(tmp_path), {}, 2, 10000)
    second = source.collect(subscription(tmp_path), first.progress, 2, 10000)
    third = source.collect(subscription(tmp_path), second.progress, 2, 10000)
    assert [item["text"] for item in first.items + second.items + third.items] == ["0", "1", "2", "3", "4"]


def test_the_cited_line_of_a_compressed_session_is_found_by_its_offset(tmp_path):
    rollout(tmp_path / "rollout-a.jsonl", [("user", "Ask Rowan about the placement")])
    item = everything(tmp_path).items[0]
    packed = compress(tmp_path / "rollout-a.jsonl")
    kind, session, offset = source.parse_session_source(item["source"])
    assert _typed_line(packed, kind, session, offset, item["source"]) is True


def consumers(ws):
    """What every reader of coding sessions makes of the store, read file by file."""
    since = NOW - timedelta(days=180)
    return {"skills": skill_usage.usage(ws.subs, ["example"], root=ws.root, now=NOW),
            "messages": project_material.session_messages(ws.subs, since=since, rem_root=ws.root,
                                                          folders=project_material.page_folders(ws.notebook)),
            "imported": sessions.import_sessions(ws.root, now=NOW, consented_only=True),
            "projects": scan.scan_projects(ws.subs, 180, ws.root)}


def fresh(ws):
    shutil.rmtree(ws.root)
    prepare(ws.root)


def test_every_reader_reads_a_compressed_store_as_the_plain_one(invented):
    ws = invented
    expected = consumers(ws)
    pass_expected = session_pass.read_sessions(ws.root, ws.subs, now=NOW, days=180)
    fresh(ws)
    for path in list(ws.codex.glob("*.jsonl")):
        compress(path)
    assert plain(consumers(ws)) == plain(expected)
    assert expected["skills"]["counts"]["example"]["count"] == 3
    fresh(ws)
    shared = session_pass.read_sessions(ws.root, ws.subs, now=NOW, days=180)
    assert plain(shared.imports) == plain(pass_expected.imports)
    assert plain(shared.skills).keys() == plain(pass_expected.skills).keys()
    assert plain({key: entry["events"] for key, entry in shared.skills.items()}) == \
        plain({key: entry["events"] for key, entry in pass_expected.skills.items()})


def test_a_skill_sample_reads_a_compressed_session(invented):
    ws = invented
    skill_usage.usage(ws.subs, ["example"], root=ws.root, now=NOW)
    expected = skill_usage.session_samples(ws.root, "example")
    for path in list(ws.codex.glob("*.jsonl")):
        compress(path)
    skill_usage.usage(ws.subs, ["example"], root=ws.root, now=NOW)
    samples = skill_usage.session_samples(ws.root, "example")
    assert any(item["source"].startswith("skill-session:codex:") for item in samples["items"]), samples
    assert plain(samples) == plain(expected)


from test_rem_session_pass import invented  # noqa: E402,F401

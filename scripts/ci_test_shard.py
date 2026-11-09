"""Split the test files into CI shards, balanced by how long each file takes.

    python scripts/ci_test_shard.py 3 6          # the files shard 3 of 6 runs
    python scripts/ci_test_shard.py --record junit/*.xml

Files, not single tests, are split: each shard collects only its own files
(collecting the whole suite costs every shard ~40s), and `--dist loadfile`
keeps a file's tests on one worker as before. The longest file goes to the
least-loaded shard first. Weights come from tests/ci_durations.json; a file
that is not in it yet weighs the median. Refresh the weights from the
`junit-*` artifacts of any CI run with --record.
"""

import json
import statistics
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DURATIONS = ROOT / "tests/ci_durations.json"


def test_files():
    return sorted(str(p.relative_to(ROOT)) for p in (ROOT / "tests").rglob("test_*.py"))


def shard(group, splits):
    known = json.loads(DURATIONS.read_text())
    default = statistics.median(known.values() or [1.0])
    weight = {name: known.get(name, default) for name in test_files()}
    loads = [0.0] * splits
    shards = [[] for _ in range(splits)]
    for name in sorted(weight, key=lambda name: (-weight[name], name)):
        lightest = loads.index(min(loads))
        loads[lightest] += weight[name]
        shards[lightest].append(name)
    return sorted(shards[group - 1])


def record(junit_paths):
    seconds = dict.fromkeys(test_files(), 0.0)
    for path in junit_paths:
        for case in ET.parse(path).iter("testcase"):
            seconds[case.get("file")] = seconds.get(case.get("file"), 0.0) + float(case.get("time"))
    rounded = {name: round(value, 2) for name, value in sorted(seconds.items())}
    DURATIONS.write_text(json.dumps(rounded, indent=0) + "\n")


if __name__ == "__main__":
    if sys.argv[1] == "--record":
        record(sys.argv[2:])
    else:
        print("\n".join(shard(int(sys.argv[1]), int(sys.argv[2]))))

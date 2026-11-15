"""Split the test files into CI shards, balanced by how long each file takes.

    python scripts/ci_test_shard.py 3 6          # the pytest arguments shard 3 of 6 runs
    python scripts/ci_test_shard.py --record junit-*/junit-*.xml

Files, not single tests, are split: each shard collects only its own files
(collecting the whole suite costs every shard ~40s). CI asks for four times
as many shards as it has jobs and runs four of them at once in each job. The longest file goes to
the least-loaded shard first. Weights come from tests/ci_durations.json; a
file with no time recorded there weighs the median. Refresh the weights from the
`junit-*` artifacts of any CI run with --record.

One file may weigh more than a whole shard should (test_rem_next_submit.py
was 222 s of a 1772 s suite), and then no number of shards makes its shard
shorter. Such a file is cut into parts of at most half an even share: every
shard that holds a part lists the file and `--file-part=FILE:i/k`, and
tests/conftest.py keeps every k-th test of that file, starting at the i-th.
"""

import json
import math
import statistics
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DURATIONS = ROOT / "tests/ci_durations.json"


def test_files():
    return sorted(str(p.relative_to(ROOT)) for p in (ROOT / "tests").rglob("test_*.py"))


def parts(weight, splits):
    """{file: k} for each file to cut into k parts so no part outweighs half an even share."""
    limit = sum(weight.values()) / splits / 2
    return {name: math.ceil(seconds / limit) for name, seconds in weight.items() if limit and seconds > limit}


def shard(group, splits):
    known = json.loads(DURATIONS.read_text())
    default = statistics.median(known.values() or [1.0])
    # No recorded time (new, or only slow tests) is not free: the file is still collected.
    weight = {name: known.get(name) or default for name in test_files()}
    cut = parts(weight, splits)
    units = {(name, part): weight[name] / cut.get(name, 1)
             for name in weight for part in range(1, cut.get(name, 1) + 1)}
    loads = [0.0] * splits
    shards = [[] for _ in range(splits)]
    for unit in sorted(units, key=lambda unit: (-units[unit], unit)):
        lightest = loads.index(min(loads))
        loads[lightest] += units[unit]
        shards[lightest].append(unit)
    mine = sorted(shards[group - 1])
    return (sorted({name for name, _ in mine})
            + [f"--file-part={name}:{part}/{cut[name]}" for name, part in mine if name in cut])


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

"""Prepare a repeatable before/after quality review; never infer quality from cost."""

import argparse
import hashlib
import json
from pathlib import Path


def compare(baseline: Path, candidate: Path) -> str:
    """Read retained task artifacts and produce a review worksheet, not a grade."""
    rows = []
    fingerprints = []
    for directory in (baseline, candidate):
        material = json.loads((directory / 'material.json').read_text())
        canonical = json.dumps(material, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
        fingerprints.append(hashlib.sha256(canonical.encode()).hexdigest())
        result = json.loads((directory / 'result.json').read_text())
        usage = result.get('usage') or {}
        rows.append({
            'Instructions (characters)': len((directory / 'instructions.md').read_text()),
            'Material (characters)': len((directory / 'material.json').read_text()),
            'Model': result.get('model', 'not recorded'),
            'Elapsed seconds': result.get('duration_seconds', 'not recorded'),
            'Input tokens (cumulative)': usage.get('input_tokens', 'not recorded'),
            'Cached input tokens (included in input)': usage.get('cached_input_tokens', 'not recorded'),
            'Output tokens': usage.get('output_tokens', 'not recorded'),
            'Execution/review status': result.get('status', 'not recorded'),
        })
    same = fingerprints[0] == fingerprints[1]
    lines = ['# Wiki output comparison', '',
             f'Identical supplied material: {same}.',
             f'Baseline SHA-256: {fingerprints[0]}',
             f'Candidate SHA-256: {fingerprints[1]}', '',
             'Different inputs cannot establish the effect of a code/prompt change alone. Also verify referenced external files and harness settings are unchanged; a material hash does not snapshot them.', '',
             '| Measurement | Baseline | Candidate |', '| --- | --- | --- |']
    lines += [f'| {key} | {rows[0][key]} | {rows[1][key]} |' for key in rows[0]]
    lines += ['', f'Baseline output: {baseline / "candidate.md"}',
              f'Candidate output: {candidate / "candidate.md"}', '',
              '## Quality review — pending', '',
              'Read both pages and original evidence. Structural validation and lower token counts do not establish quality.', '',
              '| Criterion | Baseline finding | Candidate finding | Evidence / follow-up |',
              '| --- | --- | --- | --- |']
    for criterion in ('Factual support and contradictions', 'Intent versus completed work',
                      'Important omissions', 'Citation traceability', 'Uncertainty and temporal scope',
                      'Usefulness and readability'):
        lines.append(f'| {criterion} | Not assessed | Not assessed | Required |')
    lines += ['', '## Decision — pending', '',
              'Record accept/revise/insufficient evidence with concrete reasons. For each defect, identify collection, '
              'extraction, synthesis, or rendering as the suspected cause; distinguish diagnosis from a hypothesis. '
              'Name the follow-up test, change and next comparison. Preserve both outputs. '
              'Do not automatically replace executable skills or claim a global success rate from this sample.', '']
    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('baseline', type=Path)
    parser.add_argument('candidate', type=Path)
    args = parser.parse_args()
    print(compare(args.baseline.resolve(), args.candidate.resolve()))


if __name__ == '__main__':
    main()

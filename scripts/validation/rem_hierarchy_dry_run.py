"""Read-only hierarchy census. Print names only when explicitly requested for a report."""
import argparse
import hashlib
import json
from pathlib import Path

from connectonion.rem.files import Notebook
from connectonion.rem.org_inference import infer, subject_evidence
from connectonion.rem.mail_archive import mail_metadata


def census(root, *, names=False):
    book = Notebook(root)
    before = {path: hashlib.sha256(book.read(path).encode()).hexdigest() for path in book.list()}
    metadata = mail_metadata(root)
    plans = [infer(book, path, subject_evidence(book, path, metadata)) for path in book.list('people')]
    units = {unit['path']: unit for plan in plans for unit in plan['units']}
    placed = [plan['record'] for plan in plans if plan['memberships']]
    questions = {row['question'] for plan in plans for row in plan['reviews']}
    by_kind = {kind: sum(unit['kind'] == kind for unit in units.values()) for kind in sorted({u['kind'] for u in units.values()})}
    after = {path: hashlib.sha256(book.read(path).encode()).hexdigest() for path in book.list()}
    result = {'units': len(units), 'new_units': sum(not book.path(path).exists() for path in units),
              'by_kind': by_kind, 'people_placed': len(placed),
              'memberships': sum(len(plan['memberships']) for plan in plans),
              'review_questions': len(questions), 'pages_unchanged': before == after,
              'scope': 'cited page identities and authored subject metadata; no new source investigation'}
    if names:
        title = lambda path: book.read(path).split('\n')[0].lstrip('# ').strip()
        result['people'] = [title(path) for path in placed]
        result['unit_names'] = [unit['name'] for unit in units.values()]
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=Path)
    parser.add_argument('--names', action='store_true')
    args = parser.parse_args()
    print(json.dumps(census(args.root.resolve(), names=args.names), ensure_ascii=False, indent=2))

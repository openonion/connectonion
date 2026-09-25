"""Evidence-linked questions and connections with explicit human decisions."""

import uuid
from datetime import datetime, timezone
from pathlib import Path

from .files import Notebook, WikiError, maintenance_lock, read_json, state_path, write_json


def listing(root: Path) -> list[dict]:
    return read_json(state_path(root, "reviews.json"), [])


def propose(root: Path, kind: str, subjects: list[str], question: str, basis: str) -> dict:
    if kind not in ("question", "link") or not question.strip() or not basis.strip():
        raise WikiError("Review requires question/link, a question and evidence basis")
    if len(set(subjects)) != (2 if kind == "link" else 1):
        raise WikiError("Link needs two different subjects; question needs one")
    for subject in subjects:
        if not Notebook(root).path(subject).is_file():
            raise WikiError("Review subjects must be existing pages")
    with maintenance_lock(root):
        rows = listing(root)
        # A rejected exact proposal must not repeatedly demand attention.
        for row in rows:
            if row['kind'] == kind and set(row['subjects']) == set(subjects) and row['question'] == question:
                return row
        row = dict(id=uuid.uuid4().hex, kind=kind, subjects=subjects, question=question,
                   basis=basis, status="pending", created_at=datetime.now(timezone.utc).isoformat())
        rows.append(row)
        write_json(state_path(root, "reviews.json"), rows)
    return row


def decide(root: Path, review_id: str, verdict: str, *, author: str, response: str = "") -> dict:
    if verdict not in ("yes", "no", "answer") or not author.strip():
        raise WikiError("Review decision requires yes/no/answer and an author")
    with maintenance_lock(root):
        rows = listing(root)
        row = next((r for r in rows if r['id'] == review_id), None)
        if not row or row['status'] != 'pending':
            raise WikiError("Review does not exist or has already been decided")
        if row['kind'] == 'question' and (verdict != 'answer' or not response.strip()):
            raise WikiError("A question requires an answer with response text")
        if row['kind'] == 'link' and verdict == 'answer':
            raise WikiError("A link requires yes or no")
        row.update(status={"yes": "accepted", "no": "rejected", "answer": "answered"}[verdict],
                   author=author, response=response, decided_at=datetime.now(timezone.utc).isoformat())
        write_json(state_path(root, "reviews.json"), rows)
    return row


def context(root: Path, subject: str = "") -> list[dict]:
    return [{"role": "review", "source": f"review:{r['id']}",
             "timestamp": r.get('decided_at', r['created_at']), "text": str(r)}
            for r in listing(root) if r['status'] != 'pending' and (not subject or subject in r['subjects'])]


def _problem(root: Path, candidate) -> str:
    """Why a proposed review cannot be kept, or '' when it can."""
    if not isinstance(candidate, dict) or set(candidate) != {'kind', 'subjects', 'question', 'basis'}:
        return 'Invalid review candidate fields'
    kind, subjects = candidate['kind'], candidate['subjects']
    if kind not in ('question', 'link') or not isinstance(subjects, list) or any(not isinstance(s, str) for s in subjects):
        return 'Invalid review candidate type or subjects'
    if len(subjects) != (2 if kind == 'link' else 1) or len(subjects) != len(set(subjects)):
        return 'Invalid number of review subjects'
    if any(not isinstance(candidate[k], str) or not candidate[k].strip() for k in ('question', 'basis')):
        return 'Candidate needs a question and evidence basis'
    if any(not Notebook(root).path(subject).is_file() for subject in subjects):
        return 'Candidate points to a missing notebook page'
    return ''


def ingest(root: Path, candidates: list[dict]) -> list[dict]:
    """Caller holds maintenance lock. Keep the valid proposals; drop the rest, saying why.

    A proposed question is an optional by-product of a pass. On a real notebook
    one malformed proposal -- a link with one subject -- failed a maintenance
    batch whose pages had already been written, and a failed batch does not
    advance, so the same material would be worked again on every run. Each
    proposal is checked exactly as before; only a bad one is dropped.
    """
    if not isinstance(candidates, list):
        candidates = []
    rows = listing(root)
    created, dropped = [], []
    for candidate in candidates[:2]:
        problem = _problem(root, candidate)
        if problem:
            dropped.append({'candidate': candidate, 'reason': problem})
            continue
        kind, subjects = candidate['kind'], candidate['subjects']
        if any(r['kind'] == kind and set(r['subjects']) == set(subjects) and r['question'] == candidate['question'] for r in rows):
            continue
        row = dict(candidate, id=uuid.uuid4().hex, status='pending', created_at=datetime.now(timezone.utc).isoformat())
        rows.append(row)
        created.append(row)
    if created:
        write_json(state_path(root, 'reviews.json'), rows)
    if dropped:
        write_json(state_path(root, 'reviews-dropped.json'), read_json(state_path(root, 'reviews-dropped.json'), []) + dropped)
    return created

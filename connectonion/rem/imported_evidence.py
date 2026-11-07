"""Shared full-record material and limits for imported candidate handoffs."""

import json

from .files import RemError

MAX_RECORDS = 20
MAX_EVIDENCE_CHARS = 80_000


def evidence_material(records: list[dict]) -> list[str]:
    """Serialize exactly what the draft agent reads, using a character budget."""
    if not 1 <= len(records) <= MAX_RECORDS:
        raise RemError(f"Candidate needs 1–{MAX_RECORDS} distinct record_refs")
    material = [json.dumps(record, ensure_ascii=False, indent=2) for record in records]
    if sum(map(len, material)) > MAX_EVIDENCE_CHARS:
        raise RemError("Selected evidence is too long (over 80,000 JSON characters); "
                       "narrow the candidate's record_refs")
    return material

"""Fast local transcript capture; no model, network, or maintenance lock."""

import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path

from .files import WikiError, read_json, state_path, write_json
from .source import KINDS, SKIPPED, UNFAMILIAR, _verify_prefix


def capture(root: Path, transcript: Path, kind: str, *, seconds: float = .5) -> dict:
    if kind not in KINDS or transcript.is_symlink() or not transcript.is_file():
        raise WikiError("Capture requires a regular Codex or Claude Code transcript")
    key = hashlib.sha256(str(transcript.resolve()).encode()).hexdigest()
    cursor_path = state_path(root, f"capture-cursors/{key}.json")
    cursor = read_json(cursor_path, {})
    offset = cursor.get('offset', 0)
    if transcript.stat().st_size < offset:
        raise WikiError("Capture transcript was truncated; retained queue is unchanged")
    deadline, count, skipped = time.monotonic() + seconds, 0, 0
    with transcript.open('rb') as source:
        first = json.loads(source.readline())
        meta = KINDS[kind]['meta'](first)
        if meta.get('skip'):
            return {'captured': 0, 'skipped': True}
        source.seek(0)
        digest = _verify_prefix(source, offset, cursor.get("digest"))
        while time.monotonic() < deadline:
            start = source.tell()
            line = source.readline()
            if not line or not line.endswith(b'\n'):
                break
            try:
                row = json.loads(line)
                item = KINDS[kind]['message'](row, datetime.min.replace(tzinfo=timezone.utc))
            except (ValueError, TypeError, AttributeError) as error:
                raise WikiError("Malformed transcript; already captured records remain available") from error
            if item is SKIPPED or item is UNFAMILIAR:
                skipped += 1
            elif item:
                session = item.pop('session', None) or meta.get('id') or transcript.name
                project = item.pop('cwd', None) or meta.get('cwd', '')
                item.update(source=f'{kind}:{session}:{start}', project=project, reference=transcript.as_uri())
                identity = hashlib.sha256(item['source'].encode()).hexdigest()
                path = state_path(root, f'capture-queue/{identity}.json')
                if not path.exists():
                    write_json(path, item)
                    count += 1
            digest.update(line)
            offset = source.tell()
    write_json(cursor_path, {'offset': offset, 'digest': digest.hexdigest()})
    return {'captured': count, 'skipped': skipped, 'offset': offset,
            'remaining_bytes': transcript.stat().st_size - offset}


def pending(root: Path, processed: list[str], max_items: int, max_chars: int) -> list[dict]:
    result, used = [], 0
    rows = [read_json(state_path(root, f'capture-queue/{path.name}'), {})
            for path in state_path(root, 'capture-queue').glob('*.json')]
    for row in sorted(rows, key=lambda r: (r['timestamp'], r['source'])):
        if row['source'] in processed:
            continue
        size = len(json.dumps(row, ensure_ascii=False))
        if len(result) >= max_items or used + size > max_chars:
            break
        result.append(row)
        used += size
    return result

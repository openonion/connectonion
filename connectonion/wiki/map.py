"""Build a deterministic, resumable entity map before any investigation."""

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from .files import Notebook, atomic_write
from .scan import scan_people, scan_projects
from .skill_map import map_skills


def _record(category: str, name: str, identity: str) -> str:
    slug = re.sub(r'[^\w-]+', '-', name.lower()).strip('-')[:70] or 'entry'
    return f'{category}/{slug}-{hashlib.sha256(identity.encode()).hexdigest()[:10]}.md'


def _mail_rows(clients: dict, days: int, mine, coverage: list) -> list[dict]:
    own, available, merged = set(mine), {}, {}
    for kind, client in clients.items():
        try:
            own.update(client.my_addresses())
            available[kind] = client
        except Exception as error:  # Provider failures must not block other maps.
            coverage.append(f'{kind}: unavailable ({type(error).__name__}); not searched')
    for kind, client in available.items():
        try:
            rows = scan_people({kind: client}, days, own)
        except Exception as error:
            coverage.append(f'{kind}: metadata scan failed ({type(error).__name__}); incomplete')
            continue
        coverage.append(f'{kind}: metadata only, {days} days, at most 200 messages per seven-day window')
        for row in rows:
            old = merged.get(row['address'])
            if old:
                for key in ('mails', 'sent', 'received'):
                    row[key] += old[key]
                row['first'], row['last'] = min(old['first'], row['first']), max(old['last'], row['last'])
                row['boxes'] = sorted(set(old['boxes'] + row['boxes']))
                row['subjects'] = list(dict.fromkeys(old['subjects'] + row['subjects']))[:3]
                row['name'] = row['name'] or old['name']
                row['one_way'] = row['sent'] == 0 or row['received'] == 0
            merged[row['address']] = row
    return sorted(merged.values(), key=lambda row: (-row['mails'], row['address']))


def build_map(root: Path, subscriptions: dict, clients: dict, *, days: int = 150,
              skill_directories=None, mine=()) -> dict:
    """Map observed identities; correspondent classification remains unassessed."""
    notebook = Notebook(root)
    report = {'phase': 'mapping', 'started': datetime.now(timezone.utc).isoformat(),
              'days': days, 'coverage': [], 'people': [], 'projects': [], 'created': []}
    state = root / '.state' / 'map.json'
    state.parent.mkdir(parents=True, exist_ok=True)
    def save():
        atomic_write(state, json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    save()
    report['skills'] = map_skills(notebook, skill_directories)
    save()
    people = _mail_rows(clients, days, mine, report['coverage'])
    roster = notebook.people()
    for row in people:
        existing = next((p['path'] for p in roster if row['address'].casefold() in p['emails']), None)
        record = existing or _record('people', row['name'] or row['address'], row['address'])
        made = notebook.stub_person(record, row['name'] or row['address'], [row['address']], email=row['address'])
        report['people'].append({**row, 'record': record, 'classification': 'unassessed'})
        if made:
            notebook.write(record, notebook.read(record).replace('## Uncertainties\n', '## Uncertainties\n- Correspondent classification unassessed; mapping does not establish a person or employer.\n'))
            page = notebook.read(record)
            details = f"Observed mail count: {row.get('mails', 0)}; first: {row.get('first', 'unknown')}; last: {row.get('last', 'unknown')}; mailboxes: {', '.join(row.get('boxes', [])) or 'unknown'}. [1]"
            page = page.replace('## History\n- Unknown — not investigated yet', '## History\n- ' + details)
            page = page.replace('- (none yet)', '- [1] Enumeration metadata, observed ' + report['started'] + ' — .state/map.json; window-limited, not lifetime totals')
            notebook.write(record, page)
            report['created'].append(record)
    report['coverage'] += [f'{kind}: not configured or disabled; not searched' for kind in ('gmail', 'outlook') if kind not in clients]
    save()
    groups = {}
    for row in scan_projects(subscriptions, days):
        identity = row['origin'] or row['repo'] or row['path']
        group = groups.setdefault(identity, {'name': Path(row['repo'] or row['path']).name,
                                            'paths': [], 'sessions': 0, 'first': row['first'], 'last': row['last']})
        group['paths'].append(row['path'])
        group['sessions'] += row['sessions']
        group['first'] = min(group['first'], row['first'])
        group['last'] = max(group['last'], row['last'])
    for identity, row in groups.items():
        record = _record('projects', row['name'], identity)
        existing = next((r for r in notebook.list('projects')
                         if any(path in notebook.read(r).splitlines() or f'- {path}' in notebook.read(r).splitlines()
                                for path in row['paths'])), None)
        record = existing or record
        if notebook.stub_project(record, row['name'], row['paths'], sessions=row['sessions'],
                                 first_seen=row['first'], last_seen=row['last']):
            report['created'].append(record)
        report['projects'].append({**row, 'record': record})
    report['coverage'] += [f'{name}: {sub.get("root", "")} — ' +
                           ('scanned' if sub.get('enabled', True) and Path(sub.get('root', '')).is_dir() else 'unavailable or disabled')
                           for name, sub in subscriptions.items()]
    report.update(phase='mapped', finished=datetime.now(timezone.utc).isoformat(),
                  investigation='not started', classification='unassessed; no correspondents filtered')
    save()
    for category in ('people', 'projects'):
        lines = [f'# {category.capitalize()} map', '', 'Generated enumeration; not an investigation or importance ranking.', '']
        lines += [f'- [{Path(row["record"]).stem}](../{row["record"]})' for row in report[category]]
        notebook.write(f'notes/{category}-map.md', '\n'.join(lines) + '\n')
    return report

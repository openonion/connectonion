"""GitHub repository activity as a durable inbox, using the owner's gh login.

Polling reads issues/PR snapshots, comments and every PR's published reviews.
Checkpoints commit only after delivery. No GitHub writes and no copied tokens.
"""
import hashlib
import json
import re
import shutil
import subprocess
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .store import Inbox, Message, default_home, iso_utc


def read_config() -> dict:
    path = default_home('github') / 'config.json'
    return json.loads(path.read_text()) if path.exists() else {
        'host': 'github.com', 'repos': [], 'interval': 60, 'since': None}


def _save(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    staged = path.with_suffix('.partial')
    staged.write_text(json.dumps(value), encoding='utf-8')
    staged.replace(path)


def configure(repo: str, *, remove: bool = False, host: str = None,
              interval: int = None, since: str = None) -> dict:
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repo) or '..' in repo:
        raise ValueError('Repository must be OWNER/REPO, for example openonion/connectonion')
    config = read_config()
    if host and not re.fullmatch(r'[A-Za-z0-9.-]+', host):
        raise ValueError('Host must be a hostname, for example github.com')
    if host and host != config['host'] and config['repos']:
        raise ValueError('Unwatch existing repositories before changing the GitHub host')
    if interval is not None and interval < 60:
        raise ValueError('Polling interval must be at least 60 seconds')
    if since:
        parsed = datetime.fromisoformat(since.replace('Z', '+00:00'))
        if parsed.tzinfo is None:
            raise ValueError('--since needs a timezone, for example 2026-10-02T00:00:00Z')
        since = parsed.astimezone(timezone.utc).isoformat().replace('+00:00', 'Z')
    repo = repo.lower()
    config['repos'] = [r for r in config['repos'] if r != repo]
    if not remove:
        config['repos'].append(repo)
    for key, value in [('host', host), ('interval', interval)]:
        if value is not None:
            config[key] = value
    # A backfill applies to this repository, including one already watched.
    if since:
        config.setdefault('backfill', {})[repo] = since
    _save(default_home('github') / 'config.json', config)
    return config


class GitHub:
    name = 'github'
    read_only = True

    def __init__(self):
        self.config = read_config()
        self.pause_until = 0.0
        self.account = ''

    def missing(self) -> list:
        if not shutil.which('gh'):
            return ['Install GitHub CLI (https://cli.github.com). Next: gh auth login']
        if not self.config['repos']:
            return ['No repositories watched. Next: co github watch OWNER/REPO']
        return []

    def check(self) -> list:
        problems = self.missing()
        if problems:
            return problems
        self.account = self.api('user')['login']
        for repo in self.config['repos']:
            self.api(f'repos/{repo}')
            self.api(f'repos/{repo}/issues', state='all', per_page=1)
            self.api(f'repos/{repo}/pulls', state='all', per_page=1)
        return []

    def advice(self) -> list:
        return [f"Read-only on {self.config['host']} as {self.account}; {len(self.config['repos'])} watched repositories, polling every {self.config['interval']}s."]

    def api(self, path: str, **query):
        """gh owns credential resolution. Headers govern waits; errors stay visible."""
        argv = ['gh', 'api', '--hostname', self.config['host'], '--method', 'GET', '--include', path]
        for key, value in query.items():
            argv.extend(['-f', f'{key}={value}'])
        while True:
            time.sleep(max(0, self.pause_until - time.time()))
            result = subprocess.run(argv, capture_output=True, text=True, timeout=90)
            header, _, body = result.stdout.partition('\n\n')
            headers = dict((key.lower(), value.strip()) for key, value in
                           re.findall(r'^([\w-]+):\s*(.*)$', header, re.MULTILINE))
            delay = float(headers.get('retry-after', '0'))
            if headers.get('x-ratelimit-remaining') == '0':
                delay = max(delay, float(headers['x-ratelimit-reset']) - time.time() + 1)
            self.pause_until = time.time() + max(0, delay)
            if result.returncode and delay > 0:
                continue
            if result.returncode:
                raise RuntimeError(f'GitHub GET {path}: {result.stderr.strip()}. Next: co github check')
            return json.loads(body)

    def pages(self, path: str, **query) -> list:
        rows = []
        page = 1
        while True:
            batch = self.api(path, **query, per_page=100, page=page)
            rows.extend(batch)
            if len(batch) < 100:
                return rows
            page += 1

    def run(self, inbox: Inbox, *, raw: bool = False) -> None:
        self.check()
        while True:
            # watch/unwatch take effect without losing a running listener's flags.
            self.config = read_config()
            if not self.config['repos']:
                return
            inbox.record_connection('syncing', account=self.account)
            self.scan(inbox, raw=raw)
            inbox.record_connection('connected', account=self.account)
            time.sleep(self.config['interval'])

    def scan(self, inbox: Inbox, *, raw: bool = False, since: str = None,
             now: str = None) -> None:
        path = inbox.root / 'checkpoint.json'
        saved = json.loads(path.read_text()) if path.exists() else {}
        if saved.get('host', self.config['host']) != self.config['host']:
            saved = {}
        saved['host'] = self.config['host']
        baseline_path = inbox.root / 'baseline.json'
        baselines = json.loads(baseline_path.read_text()) if baseline_path.exists() else {}
        started = now or iso_utc()
        for repo in self.config['repos']:
            previous = saved.get(repo, {})
            backfill = self.config.get('backfill', {}).get(repo)
            replay = backfill and previous.get('backfill') != backfill
            key = f'{self.config["host"]}/{repo}'
            first = since or (backfill if replay else previous.get('since')) or baselines.get(key) or started
            if key not in baselines:
                baselines[key] = first
                _save(baseline_path, baselines)
            cursor = _overlap(first)
            floor = cursor if previous and not replay and not since else first
            messages = self._messages(repo, cursor, floor)
            for message in sorted(messages, key=lambda m: (m.at, m.id)):
                message.id = f"{self.config['host']}:{message.id}"
                message.event["host"] = self.config["host"]
                inbox.deliver(message, raw=raw)
            saved[repo] = {'since': started, 'backfill': backfill}
            _save(path, saved)
            inbox.log(f'{repo}: caught up through {started}; {len(messages)} observed records')

    def _messages(self, repo: str, cursor: str, baseline: str) -> list:
        prefix = f'repos/{repo}'
        messages = []
        issues = self.pages(f'{prefix}/issues', state='all', sort='updated', direction='asc', since=cursor)
        for row in issues:
            if row['updated_at'] < baseline:
                continue
            kind = 'pull_request' if 'pull_request' in row else 'issue'
            action = 'created' if row['created_at'] >= baseline else 'updated'
            if row['state'] == 'closed':
                action = 'closed'
                if kind == 'pull_request':
                    row['merged_at'] = self.api(f'{prefix}/pulls/{row["number"]}').get('merged_at')
                    if row['merged_at']:
                        action = 'merged'
            messages.append(to_message(repo, row['number'], kind, action, row))
        for endpoint, kind, parent in [('issues/comments', 'issue_comment', 'issue_url'),
                                      ('pulls/comments', 'review_comment', 'pull_request_url')]:
            for row in self.pages(f'{prefix}/{endpoint}', since=cursor, sort='updated', direction='asc'):
                if row['updated_at'] >= baseline:
                    number = int(row[parent].rsplit('/', 1)[1])
                    action = 'created' if row['created_at'] >= baseline else 'updated'
                    messages.append(to_message(repo, number, kind, action, row))
        messages.extend(self._reviews(repo, baseline))
        return messages

    def _reviews(self, repo: str, baseline: str) -> list:
        """Review submission is not inferred from issue updated_at. Read every PR.

        This is deliberately complete for small repositories; large repositories
        should use a longer interval until we add a webhook transport.
        """
        messages = []
        for pr in self.pages(f'repos/{repo}/pulls', state='all'):
            for row in self.pages(f'repos/{repo}/pulls/{pr["number"]}/reviews'):
                if row.get('submitted_at') and row['submitted_at'] >= baseline:
                    messages.append(to_message(repo, pr['number'], 'review', 'submitted', row))
        return messages


def _overlap(at: str) -> str:
    stamp = datetime.fromisoformat(at.replace('Z', '+00:00')) - timedelta(seconds=2)
    return stamp.isoformat().replace('+00:00', 'Z')


def to_message(repo: str, number: int, kind: str, action: str, row: dict) -> Message:
    # Content and resource version identify observations, not the scan time.
    # Do not put a guessed editor in sender on a resource update.
    version = {key: row.get(key) for key in ('title', 'body', 'state', 'labels', 'updated_at', 'submitted_at', 'merged_at')}
    digest = hashlib.sha256(json.dumps(version, sort_keys=True).encode()).hexdigest()[:20]
    event = {'repo': repo, 'number': number, 'kind': kind, 'action': action,
             'resource_id': row['id'], 'url': row['html_url'], 'state': row.get('state'),
             'labels': [label['name'] for label in row.get('labels', [])]}
    return Message(id=f'{repo}:{kind}:{row["id"]}:{digest}', chat=f'{repo}#{number}',
                   sender=row['user']['login'] if action in ('created', 'submitted') else '',
                   text='\n\n'.join(part for part in (row.get('title'), row.get('body')) if part),
                   at=row.get('updated_at') or row.get('submitted_at'), raw=row, event=event)
